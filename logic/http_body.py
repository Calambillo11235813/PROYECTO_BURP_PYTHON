"""
logic/http_body.py
------------------
Utilidades para descompresión y render legible de mensajes HTTP crudos.

Objetivo:
    - Detectar Content-Encoding (gzip/deflate/br).
    - Descomprimir cuerpo para visualización en GUI/historial.
    - Evitar mojibake cuando el contenido es texto comprimido.
    - Proteger la aplicación ante cuerpos binarios (imágenes/protobuf/etc.).

Este módulo es de solo lectura/visualización: no modifica los bytes crudos
que se reenvían al servidor.
"""

from __future__ import annotations

import gzip
import re
import zlib

try:
    import brotli as _brotli
    _BROTLI_AVAILABLE = True
except ImportError:
    _BROTLI_AVAILABLE = False

_BINARY_PLACEHOLDER = "[Cuerpo Binario / No legible]"

_TEXT_MIME_HINTS = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/javascript",
    "application/x-javascript",
    "application/x-www-form-urlencoded",
    "application/graphql",
)


def build_display_http_message(raw: bytes) -> str:
    """
    Convierte un mensaje HTTP crudo en una representación legible para UI.

    Reglas:
        1. Si hay Content-Encoding soportado, intenta descomprimir.
        2. Si el cuerpo resultante es textual, lo decodifica respetando charset.
        3. Si parece binario o no es decodificable, muestra un placeholder.

    Args:
        raw: Mensaje HTTP completo (request o response) en bytes.

    Returns:
        str: Mensaje HTTP apto para mostrarse en editor/historial.
    """
    if not raw:
        return ""

    header_part, body = _split_http_message(raw)
    header_text = header_part.decode("iso-8859-1", errors="replace")
    headers = _parse_headers(header_text)

    if not body:
        return header_text

    # De-chunking: debe ejecutarse ANTES de la descompresión.
    # Si Transfer-Encoding: chunked, el body llega con tamaños hex intercalados.
    # gzip.decompress fallará si recibe ese formato sin limpiar primero.
    transfer_encoding = headers.get("transfer-encoding", "")
    if "chunked" in transfer_encoding.lower():
        body = _dechunk_body(body)

    encoding_value = _resolve_encoding(headers)
    decoded_body, decoded_ok = _decode_content(body, encoding_value)

    content_type = headers.get("content-type", "")
    if _looks_binary(decoded_body, content_type):
        body_text = _BINARY_PLACEHOLDER
    else:
        body_text = _decode_text(decoded_body, _extract_charset(content_type))
        if body_text is None:
            if decoded_ok:
                body_text = _BINARY_PLACEHOLDER
            else:
                # Mantener salida resiliente sin romper flujo de la app.
                body_text = _safe_ascii_preview(body)

    return f"{header_text}\r\n\r\n{body_text}"


def _split_http_message(raw: bytes) -> tuple[bytes, bytes]:
    if b"\r\n\r\n" in raw:
        return raw.split(b"\r\n\r\n", 1)
    if b"\n\n" in raw:
        return raw.split(b"\n\n", 1)
    return raw, b""


def _dechunk_body(data: bytes) -> bytes:
    """
    Decodifica un cuerpo HTTP con Transfer-Encoding: chunked (RFC 7230 §4.1).

    Cada bloque tiene el formato::

        <hex_size>\r\n
        <data_bytes>\r\n
        ...
        0\r\n
        \r\n   (terminador de bloques, opcionalmente trailers)

    Args:
        data: Bytes crudos del cuerpo chunked (sin las cabeceras HTTP).

    Returns:
        bytes: Cuerpo reensamblado sin los metadatos de chunking.
                Si el formato es inesperado, devuelve `data` intacto como
                degradación segura para no romper la UI.
    """
    result = bytearray()
    pos = 0
    try:
        while pos < len(data):
            # Buscar el final de la línea de tamaño (puede incluir extensiones)
            line_end = data.find(b"\r\n", pos)
            if line_end == -1:
                break

            size_line = data[pos:line_end].split(b";")[0].strip()
            if not size_line:
                break

            chunk_size = int(size_line, 16)
            if chunk_size == 0:
                break  # Chunk final: fin del cuerpo

            chunk_start = line_end + 2
            chunk_end   = chunk_start + chunk_size
            result.extend(data[chunk_start:chunk_end])
            pos = chunk_end + 2  # Saltar el \r\n al final del chunk
    except (ValueError, IndexError):
        # Si el formato es inválido, devuelve los datos sin modificar.
        return data

    return bytes(result) if result else data


def _parse_headers(header_text: str) -> dict[str, str]:
    lines = header_text.replace("\r\n", "\n").split("\n")
    result: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip().lower()] = value.strip()
    return result


def _decode_content(body: bytes, content_encoding: str | None) -> tuple[bytes, bool]:
    if not content_encoding:
        return body, True

    encodings = [e.strip().lower() for e in content_encoding.split(",") if e.strip()]
    if not encodings:
        return body, True

    current = body
    for enc in reversed(encodings):
        try:
            if enc == "gzip":
                current = gzip.decompress(current)
            elif enc == "deflate":
                current = _decompress_deflate(current)
            elif enc == "br":
                if _BROTLI_AVAILABLE:
                    current = _brotli.decompress(current)
                else:
                    return body, False
            elif enc == "identity":
                continue
            else:
                return body, False
        except Exception:
            return body, False

    return current, True


def _resolve_encoding(headers: dict[str, str]) -> str | None:
    """
    Prioriza Content-Encoding; si no existe, usa Accept-Encoding como fallback.

    Nota: en HTTP estándar la codificación real del cuerpo la define
    Content-Encoding. Accept-Encoding se considera aquí solo como señal
    auxiliar para casos no estándar.
    """
    content_encoding = headers.get("content-encoding")
    if content_encoding:
        return content_encoding
    return headers.get("accept-encoding")


def _decompress_deflate(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except zlib.error:
        return zlib.decompress(data, -zlib.MAX_WBITS)


def _extract_charset(content_type: str) -> str | None:
    match = re.search(r"charset\s*=\s*([^;]+)", content_type, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().strip('"').strip("'")


def _decode_text(data: bytes, charset: str | None) -> str | None:
    candidates = []
    if charset:
        candidates.append(charset)
    candidates.extend(["utf-8", "latin-1"])

    for enc in candidates:
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return None


def _looks_binary(data: bytes, content_type: str) -> bool:
    if not data:
        return False

    ct = content_type.lower()
    if any(ct.startswith(prefix) for prefix in _TEXT_MIME_HINTS):
        return False
    if "json" in ct or "xml" in ct or "javascript" in ct or "html" in ct:
        return False

    if b"\x00" in data:
        return True

    sample = data[:2048]
    non_printable = sum(
        1
        for b in sample
        if b not in (9, 10, 13) and not (32 <= b <= 126)
    )
    ratio = non_printable / max(1, len(sample))
    return ratio > 0.30


def _safe_ascii_preview(data: bytes) -> str:
    """Fallback ultra-seguro para evitar texto corrupto en UI."""
    return data.decode("ascii", errors="replace")
