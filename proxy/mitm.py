"""
proxy/mitm.py
-------------
Interceptación SSL/TLS completa (MITM) para tráfico HTTPS.

Flujo para cada CONNECT recibido por el proxy:
    1. Conectar al servidor real (TCP).
    2. Responder 200 Connection Established al navegador.
    3. Generar cert de dominio (CertsManager, cacheado tras la primera vez).
    4. SSL handshake con el servidor real  (proxy actúa como cliente TLS).
    5. SSL handshake con el navegador      (proxy actúa como servidor TLS).
    6. Loop: leer petición HTTP plana → parsear → intercept? → forward →
             leer respuesta → guardar en historial → repetir (keep-alive).

El resultado es que la GUI ve peticiones HTTPS exactamente igual que HTTP:
la tabla de historial muestra método, host y path en texto claro, y el
área de edición del interceptador muestra el raw HTTP completo.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import socket
import ssl
import time
import re
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from logic.http_body import build_display_http_message
from logic.parser import parse_request, display_host
from .history import History, RequestRecord

if TYPE_CHECKING:
    from core.certs_manager import CertsManager
    from .handler import InterceptController

# ── Constantes ────────────────────────────────────────────────────────────────
BUFFER_SIZE        = 4096
CONNECTION_TIMEOUT = 10    # segundos
INTERCEPT_TIMEOUT  = 60.0  # tiempo máximo esperando decisión del usuario
MAX_HEADER_BYTES   = 64 * 1024


class MitmHandler:
    """
    Realiza la interceptación SSL/TLS completa de una sola conexión HTTPS.

    Instanciado por ConnectionHandler cada vez que llega un CONNECT.
    No comparte estado entre conexiones (thread-safe por diseño).

    Args:
        host      : Hostname destino (del CONNECT original).
        port      : Puerto destino (del CONNECT original).
        req_id    : ID del CONNECT; los sub-requests usan IDs nuevos.
        certs     : Gestor de certificados (CertsManager).
        history   : Historial compartido (History).
        intercept : Controlador de intercepción (InterceptController).
        next_id   : Callable que retorna el siguiente ID de petición.
        client_ip : IP del navegador (para el historial).
    """

    def __init__(
        self,
        host      : str,
        port      : int,
        req_id    : int,
        certs     : "CertsManager",
        history   : History,
        intercept : "InterceptController",
        next_id   : Callable[[], int],
        client_ip : str,
    ) -> None:
        self._host      = host
        self._port      = port
        self._req_id    = req_id
        self._certs     = certs
        self._history   = history
        self._intercept = intercept
        self._next_id   = next_id
        self._client_ip = client_ip

    # ── Punto de entrada ──────────────────────────────────────────────────────

    def handle(self, client_socket: socket.socket) -> bool:
        """
        Orquesta el MITM completo para una conexión CONNECT.

        El caller ya leyó el CONNECT del socket pero NO envió aún el 200.
        Este método envía el 200, hace los handshakes SSL y procesa las
        peticiones HTTP resultantes hasta que la conexión se cierre.

        Args:
            client_socket: Socket TCP del navegador.

        Returns:
            bool: True si la sesión MITM se estableció y procesó correctamente.
                  False si falló el handshake/setup y el caller debe hacer fallback.
        """
        # 1. Conectar al servidor real ANTES de responder al navegador
        try:
            raw_server = socket.create_connection(
                (self._host, self._port), timeout=CONNECTION_TIMEOUT,
            )
        except (OSError, socket.timeout) as exc:
            print(f"[MITM] No se pudo conectar a {self._host}:{self._port}: {exc}")
            return False

        # 2. Confirmar al navegador que puede iniciar TLS
        try:
            client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        except OSError:
            raw_server.close()
            return False

        # 3. Envolver ambos sockets en TLS
        try:
            ssl_client, ssl_server = self._wrap_both(client_socket, raw_server)
        except ssl.SSLError as exc:
            print(f"[MITM] Handshake SSL fallido ({self._host}): {exc}")
            raw_server.close()
            return False
        except OSError as exc:
            print(f"[MITM] Error de red durante SSL setup ({self._host}): {exc}")
            raw_server.close()
            return False

        # 4. Loop de peticiones HTTP sobre el canal TLS establecido
        try:
            self._request_loop(ssl_client, ssl_server)
        finally:
            _close_safe(ssl_client)
            _close_safe(ssl_server)
        return True

    # ── SSL: setup de contextos y wrapping ────────────────────────────────────

    def _wrap_both(
        self,
        client_raw: socket.socket,
        server_raw: socket.socket,
    ) -> tuple[ssl.SSLSocket, ssl.SSLSocket]:
        """
        Realiza los dos handshakes TLS del MITM.

        Orden: primero servidor (para verificar que es alcanzable bajo TLS),
        luego cliente (el navegador ya espera TLS desde que recibió el 200).

        Returns:
            (ssl_client, ssl_server): Sockets TLS listos para I/O.
        """
        cert_path, key_path = self._certs.get_domain_cert(self._host)

        # Contexto servidor (proxy ← navegador): usamos nuestro cert firmado por CA
        ctx_srv = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx_srv.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

        # Contexto cliente (proxy → servidor real): no verificar cert (herramienta pentesting)
        ctx_cli = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx_cli.check_hostname = False
        ctx_cli.verify_mode    = ssl.CERT_NONE

        # Handshake con el servidor real primero
        ssl_server = ctx_cli.wrap_socket(server_raw, server_hostname=self._host)
        # Luego aceptar la conexión TLS del navegador
        ssl_client = ctx_srv.wrap_socket(client_raw, server_side=True)
        return ssl_client, ssl_server

    # ── Loop de peticiones HTTP descifradas ───────────────────────────────────

    def _request_loop(
        self,
        ssl_client: ssl.SSLSocket,
        ssl_server: ssl.SSLSocket,
    ) -> None:
        """
        Lee peticiones HTTP del navegador (ya descifradas), las procesa y
        reenvía al servidor. Soporta HTTP/1.1 keep-alive (múltiples request
        por conexión TLS).

        Args:
            ssl_client: Lado navegador (lectura de requests).
            ssl_server: Lado servidor real (reenvío y lectura de responses).
        """
        ssl_client.settimeout(CONNECTION_TIMEOUT)
        ssl_server.settimeout(CONNECTION_TIMEOUT)

        while True:
            raw = _recv_http_message(ssl_client, is_response=False)
            if not raw:
                break

            parsed = parse_request(raw)
            if not parsed:
                break

            # El host y puerto reales los conocemos del CONNECT original
            parsed.host = self._host
            parsed.port = self._port

            req_id  = self._next_id()
            t_start = time.perf_counter()
            display_request = build_display_http_message(raw)
            pending_record_created = False

            # ── CU-04: Intercepción (igual que en HTTP) ──────────────────
            final_raw = raw
            if self._intercept.intercept_enabled:
                self._history.add(RequestRecord(
                    id=req_id,
                    timestamp=datetime.now(),
                    method=parsed.method,
                    host=display_host(self._host, self._port),
                    port=self._port,
                    path=parsed.path,
                    headers=parsed.headers,
                    body=parsed.body,
                    raw_request=raw,
                    response_status="PENDIENTE",
                    response_raw=b"",
                    response_headers={},
                    response_body=b"",
                    display_request=display_request,
                    display_response="",
                    duration_ms=0.0,
                    client_ip=self._client_ip,
                ))
                pending_record_created = True

                pending = self._intercept.intercept(
                    req_id, raw, parsed, display_text=display_request,
                )
                decision, final_raw   = pending.wait(timeout=INTERCEPT_TIMEOUT)
                if decision == "drop":
                    _send_safe(
                        ssl_client,
                        b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n",
                    )
                    self._history.update(
                        req_id,
                        response_status="HTTP/1.1 403 Forbidden",
                        response_raw=b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n",
                        response_headers={"Content-Length": "0"},
                        response_body=b"",
                        duration_ms=(time.perf_counter() - t_start) * 1000,
                    )
                    continue

            # ── Reenvío al servidor real ─────────────────────────────────
            if not _send_safe(ssl_server, final_raw):
                break
            response = _recv_http_message(ssl_server, is_response=True)
            display_response = build_display_http_message(response) if response else ""
            response_headers, response_body = _split_http_response(response or b"")

            # ── Devolver respuesta al navegador ──────────────────────────
            if response:
                _send_safe(ssl_client, response)

            duration_ms = (time.perf_counter() - t_start) * 1000
            resp_status = _extract_status(response)

            # ── CU-03: Guardar en historial ──────────────────────────────
            if pending_record_created:
                self._history.update(
                    req_id,
                    raw_request=final_raw,
                    response_status=resp_status,
                    response_raw=response or b"",
                    response_headers=response_headers,
                    response_body=response_body,
                    display_request=display_request,
                    display_response=display_response,
                    duration_ms=duration_ms,
                )
            else:
                self._history.add(RequestRecord(
                    id=req_id,
                    timestamp=datetime.now(),
                    method=parsed.method,
                    host=display_host(self._host, self._port),
                    port=self._port,
                    path=parsed.path,
                    headers=parsed.headers,
                    body=parsed.body,
                    raw_request=final_raw,
                    response_status=resp_status,
                    response_raw=response or b"",
                    response_headers=response_headers,
                    response_body=response_body,
                    display_request=display_request,
                    display_response=display_response,
                    duration_ms=duration_ms,
                    client_ip=self._client_ip,
                ))

            # Respetar Connection: close (no mantener keep-alive)
            if response and b"connection: close" in response[:512].lower():
                break


# ── Helpers de módulo (sin estado) ────────────────────────────────────────────

def _recv_all(sock: ssl.SSLSocket | socket.socket) -> bytes:
    """
    Lee todos los bytes disponibles del socket hasta timeout o cierre.

    Args:
        sock: Socket SSL o TCP del que leer.

    Returns:
        bytes: Datos acumulados; b"" si el socket fue cerrado.
    """
    data = b""
    while True:
        try:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            data += chunk
            if len(chunk) < BUFFER_SIZE:
                break
        except (socket.timeout, ssl.SSLWantReadError, ssl.SSLZeroReturnError):
            break
        except OSError:
            break
    return data


def _recv_http_message(sock: ssl.SSLSocket | socket.socket, is_response: bool) -> bytes:
    """
    Lee un mensaje HTTP completo sobre socket SSL/TCP.
    """
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = _recv_safe(sock)
        if not chunk:
            return data
        data += chunk
        if len(data) > MAX_HEADER_BYTES:
            return data

    header_end = data.find(b"\r\n\r\n")
    header_bytes = data[:header_end]
    body = data[header_end + 4:]
    headers_text = header_bytes.decode("iso-8859-1", errors="replace")

    if _has_chunked_encoding(headers_text):
        body = _read_chunked_body(sock, body)
        return header_bytes + b"\r\n\r\n" + body

    content_length = _content_length(headers_text)
    if content_length is not None:
        while len(body) < content_length:
            chunk = _recv_safe(sock)
            if not chunk:
                break
            body += chunk
        return header_bytes + b"\r\n\r\n" + body[:content_length]

    if not is_response:
        return header_bytes + b"\r\n\r\n" + body

    extra = _read_until_timeout(sock)
    return header_bytes + b"\r\n\r\n" + body + extra


def _recv_safe(sock: ssl.SSLSocket | socket.socket) -> bytes:
    try:
        return sock.recv(BUFFER_SIZE)
    except (socket.timeout, ssl.SSLWantReadError, ssl.SSLZeroReturnError):
        return b""
    except OSError:
        return b""


def _read_until_timeout(sock: ssl.SSLSocket | socket.socket) -> bytes:
    out = b""
    while True:
        chunk = _recv_safe(sock)
        if not chunk:
            break
        out += chunk
    return out


def _has_chunked_encoding(headers_text: str) -> bool:
    match = re.search(r"^transfer-encoding\s*:\s*(.+)$", headers_text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return False
    return "chunked" in match.group(1).lower()


def _content_length(headers_text: str) -> int | None:
    match = re.search(r"^content-length\s*:\s*(\d+)\s*$", headers_text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _read_chunked_body(sock: ssl.SSLSocket | socket.socket, initial: bytes) -> bytes:
    data = initial
    while b"\r\n0\r\n\r\n" not in data:
        chunk = _recv_safe(sock)
        if not chunk:
            break
        data += chunk
    return data


def _send_safe(sock: ssl.SSLSocket | socket.socket, data: bytes) -> bool:
    """
    Envía datos ignorando errores de socket roto.

    Returns:
        True si el envío tuvo éxito, False en caso de error.
    """
    try:
        sock.sendall(data)
        return True
    except (OSError, ssl.SSLError):
        return False


def _close_safe(sock: ssl.SSLSocket | socket.socket | None) -> None:
    """Cierra el socket sin propagar errores si ya estaba cerrado."""
    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass


def _extract_status(response: bytes | None) -> str:
    """
    Extrae la primera línea de la respuesta HTTP como string de status.

    Args:
        response: Bytes crudos de la respuesta HTTP.

    Returns:
        str: Ej. 'HTTP/1.1 200 OK'; cadena vacía si no hay respuesta.
    """
    if not response:
        return ""
    try:
        return response.split(b"\r\n")[0].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _split_http_response(raw_response: bytes) -> tuple[dict[str, str], bytes]:
    """Separa cabeceras y body de una respuesta HTTP cruda."""
    if not raw_response:
        return {}, b""

    separator = b"\r\n\r\n"
    idx = raw_response.find(separator)
    if idx == -1:
        return {}, b""

    header_blob = raw_response[:idx].decode("iso-8859-1", errors="replace")
    body = raw_response[idx + len(separator):]
    headers: dict[str, str] = {}

    for line in header_blob.split("\r\n")[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()

    return headers, body
