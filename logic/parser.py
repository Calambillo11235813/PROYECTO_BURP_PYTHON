"""
logic/parser.py
---------------
Principio de Responsabilidad Única: este módulo SOLO parsea bytes HTTP.
No abre sockets, no gestiona hilos, no imprime en consola.

Expone:
    ParsedRequest  → dataclass con los campos extraídos de una petición.
    parse_request  → función principal que convierte bytes → ParsedRequest.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────
#  Dataclass de resultado
# ─────────────────────────────────────────────
@dataclass
class ParsedRequest:
    """
    Resultado del parseo de una petición HTTP cruda.

    Attributes:
        method  (str)  : Verbo HTTP (GET, POST, CONNECT, …).
        host    (str)  : Nombre de host destino.
        port    (int)  : Puerto destino (80 por defecto, 443 para HTTPS).
        path    (str)  : Path de la URL (ej. "/api/users").
        headers (dict) : Cabeceras HTTP como diccionario clave→valor.
        body    (bytes): Cuerpo de la petición (puede ser vacío).
    """
    method  : str
    host    : str
    port    : int
    path    : str
    headers : dict  = field(default_factory=dict)
    body    : bytes = b""


# ─────────────────────────────────────────────
#  Función principal de parseo
# ─────────────────────────────────────────────
def parse_request(raw: bytes) -> ParsedRequest | None:
    """
    Descompone una petición HTTP cruda en sus partes componentes.

    Soporta tres formatos de Request-Line:
        - URL absoluta : GET http://example.com/path HTTP/1.1
        - URL relativa : POST /api/login HTTP/1.1  (host en cabecera Host:)
        - CONNECT      : CONNECT github.com:443 HTTP/1.1  (tunnel HTTPS)

    Args:
        raw (bytes): Bytes crudos recibidos del socket del navegador.

    Returns:
        ParsedRequest | None: Campos parseados, o None si la petición
                              está vacía o malformada.
    """
    if not raw:
        return None

    try:
        # ── 1. Separar cabeceras del body ──────────────────────────────
        if b"\r\n\r\n" in raw:
            header_section, body = raw.split(b"\r\n\r\n", 1)
        else:
            header_section, body = raw, b""

        lines = header_section.decode("utf-8", errors="replace").split("\r\n")
        if not lines or not lines[0]:
            return None

        # ── 2. Parsear la Request-Line ─────────────────────────────────
        parts = lines[0].split(" ")
        if len(parts) < 2:
            return None

        method = parts[0]
        url    = parts[1]

        # ── 3. Extraer host, puerto y path ─────────────────────────────
        host, port, path = _extract_host_port_path(method, url, lines[1:])

        # ── 4. Parsear cabeceras como diccionario ──────────────────────
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key.strip()] = value.strip()

        return ParsedRequest(
            method=method,
            host=host,
            port=port,
            path=path,
            headers=headers,
            body=body,
        )

    except Exception:
        return None


# ─────────────────────────────────────────────
#  Helpers privados de parseo
# ─────────────────────────────────────────────
def _extract_host_port_path(
    method: str,
    url: str,
    header_lines: list[str],
) -> tuple[str, int, str]:
    """
    Determina (host, port, path) según el tipo de petición.

    Args:
        method       (str)      : Verbo HTTP.
        url          (str)      : Segunda parte de la Request-Line.
        header_lines (list[str]): Líneas de cabecera sin la Request-Line.

    Returns:
        tuple[str, int, str]: (host, puerto, path)
    """
    if method.upper() == "CONNECT":
        # CONNECT host:443 HTTP/1.1
        parts = url.split(":")
        host  = parts[0]
        port  = int(parts[1]) if len(parts) > 1 else 443
        return host, port, url

    if url.startswith("http://"):
        return _parse_absolute_url(url)

    # URL relativa → host en cabecera Host:
    return _host_from_headers(url, header_lines)


def _parse_absolute_url(url: str) -> tuple[str, int, str]:
    """
    Parsea una URL absoluta tipo 'http://host[:port]/path'.

    Args:
        url (str): URL incluyendo el scheme 'http://'.

    Returns:
        tuple[str, int, str]: (host, puerto, path)
    """
    stripped  = url[7:]   # quitar "http://"
    if "/" in stripped:
        host_part, rest = stripped.split("/", 1)
        path = "/" + rest
    else:
        host_part = stripped
        path      = "/"

    if ":" in host_part:
        host, port_str = host_part.split(":", 1)
        return host, int(port_str), path

    return host_part, 80, path


def _host_from_headers(
    path: str,
    header_lines: list[str],
) -> tuple[str, int, str]:
    """
    Extrae host y puerto desde la cabecera 'Host:' cuando la URL es relativa.

    Args:
        path         (str)      : Path de la petición (ya conocido).
        header_lines (list[str]): Líneas de cabeceras sin la Request-Line.

    Returns:
        tuple[str, int, str]: (host, puerto, path)
    """
    for line in header_lines:
        if line.lower().startswith("host:"):
            host_value = line.split(":", 1)[1].strip()
            if ":" in host_value:
                host, port_str = host_value.split(":", 1)
                return host, int(port_str), path
            return host_value, 80, path

    return "", 80, path
