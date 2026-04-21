"""
proxy/handler.py
----------------
Procesa cada conexión cliente de forma individual.

Clases:
    PendingRequest      → CU-04: petición HTTP pausada esperando decisión.
    InterceptController → CU-04: controlador del modo intercept ON/OFF.
    ConnectionHandler   → Orquesta recv → parse → intercept? → forward → history.

Principio de Responsabilidad Única: este módulo NO gestiona el socket servidor
(bind/listen/accept). Eso es responsabilidad de server.py.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import queue
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from .host_filter import (
    FILTER_DECISION_BYPASS,
    FILTER_DECISION_DROP,
    HostFilter,
)
from .history import History, RequestRecord
from .mitm import MitmHandler
from logic.http_body import build_display_http_message
from logic.parser import ParsedRequest, parse_request, display_host

# ── Constantes de bajo nivel (solo para este módulo) ──────────────────────────
BUFFER_SIZE        = 4096   # bytes por llamada a recv()
CONNECTION_TIMEOUT = 10     # segundos antes de cerrar un socket idle
MAX_HEADER_BYTES   = 64 * 1024


# ── Colores ANSI para el log en consola ───────────────────────────────────────
class Colors:
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


# ─────────────────────────────────────────────────────────────────────────────
#  CU-04 — Intercepción en tiempo real
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PendingRequest:
    """
    Petición HTTP pausada esperando una decisión externa (GUI o CLI).

    El hilo del handler llama a wait() y se bloquea hasta que la GUI/CLI
    resuelve con forward() o drop().

    Attributes:
        id     (int)          : ID secuencial de la petición.
        raw    (bytes)        : Bytes crudos originales de la petición.
        parsed (ParsedRequest): Petición ya desglosada en campos.
    """
    id     : int
    raw    : bytes
    parsed : ParsedRequest
    display_text: str = ""
    _event : threading.Event = field(default_factory=threading.Event, repr=False)
    _decision    : str   = field(default="", init=False, repr=False)
    _modified_raw: bytes = field(default=b"", init=False, repr=False)

    def wait(self, timeout: float = 60.0) -> tuple[str, bytes]:
        """
        Bloquea el hilo del handler hasta recibir una decisión.

        Args:
            timeout (float): Segundos máximos de espera. Default 60s.

        Returns:
            tuple[str, bytes]: ("forward" | "drop" | "timeout", raw_a_usar)
        """
        fired = self._event.wait(timeout=timeout)
        if not fired:
            return "timeout", self.raw
        return self._decision, self._modified_raw or self.raw

    def forward(self, modified_raw: bytes | None = None) -> None:
        """
        Libera el hilo con decisión 'forward'.

        Args:
            modified_raw (bytes | None): Petición posiblemente editada.
                                         Si es None se usa la original.
        """
        self._decision     = "forward"
        self._modified_raw = modified_raw if modified_raw is not None else self.raw
        self._event.set()

    def drop(self) -> None:
        """Libera el hilo con decisión 'drop' (descarta la petición)."""
        self._decision = "drop"
        self._event.set()

    def should_forward_original(self, editor_text: str) -> bool:
        """True si el usuario no modificó el contenido mostrado en el editor."""
        if not self.display_text:
            return False
        return _normalize_text(editor_text) == _normalize_text(self.display_text)


class InterceptController:
    """
    CU-04: Controlador del modo de intercepción en tiempo real.

    Permite pausar peticiones HTTP antes de reenviarlas al servidor y
    esperar una decisión externa (de la GUI o de la CLI).

    Uso desde el handler (hilo de conexión):
        if intercept.intercept_enabled:
            pending = intercept.intercept(req_id, raw, parsed)
            decision, final_raw = pending.wait()

    Uso desde la GUI (hilo principal):
        pending = intercept.next_pending()
        pending.forward(modified_raw)  # ó pending.drop()
    """

    def __init__(self) -> None:
        self.intercept_enabled: bool = False
        self._queue: queue.Queue[PendingRequest] = queue.Queue()

    def enable(self) -> None:
        """Activa el modo de intercepción. Las peticiones HTTP se pausarán."""
        self.intercept_enabled = True

    def disable(self) -> None:
        """Desactiva la intercepción. Las peticiones fluyen directamente."""
        self.intercept_enabled = False

    def intercept(
        self,
        req_id: int,
        raw   : bytes,
        parsed: ParsedRequest,
        display_text: str = "",
    ) -> PendingRequest:
        """
        Crea un PendingRequest, lo encola y lo retorna para que el hilo
        del handler lo espere con pending.wait().

        Args:
            req_id (int)         : ID de la petición.
            raw    (bytes)       : Bytes crudos originales.
            parsed (ParsedRequest): Petición desglosada.

        Returns:
            PendingRequest: Objeto en espera de decisión.
        """
        pending = PendingRequest(
            id=req_id, raw=raw, parsed=parsed, display_text=display_text,
        )
        self._queue.put(pending)
        return pending

    def next_pending(self, timeout: float = 0.0) -> PendingRequest | None:
        """
        Retorna la siguiente petición pendiente (para que la GUI la procese).

        Args:
            timeout (float): Segundos de espera. 0 = no bloqueante.

        Returns:
            PendingRequest | None: Siguiente petición o None si no hay.
        """
        try:
            if timeout > 0:
                return self._queue.get(block=True, timeout=timeout)
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def pending_count(self) -> int:
        """Número de peticiones actualmente en espera de decisión."""
        return self._queue.qsize()


# ─────────────────────────────────────────────────────────────────────────────
#  Procesamiento de conexiones individuales
# ─────────────────────────────────────────────────────────────────────────────
class ConnectionHandler:
    """
    Procesa cada conexión cliente del proxy de forma independiente.

    Una única instancia de ConnectionHandler es compartida por todos los
    hilos de conexión del servidor, por lo que todos los métodos que
    acceden al contador de IDs están protegidos con un threading.Lock.

    Args:
        history   (History)            : Historial persistente (CU-03).
        intercept (InterceptController): Controlador de intercepción (CU-04).
    """

    def __init__(
        self,
        history   : History,
        intercept : InterceptController,
        certs_manager=None,     # Optional[CertsManager] — None = modo túnal
        host_filter: HostFilter | None = None,
    ) -> None:
        self.history       = history
        self.intercept     = intercept
        self.certs_manager = certs_manager  # Si es None, HTTPS no se descifra
        self.host_filter   = host_filter or HostFilter()
        self._count        = 0
        self._lock         = threading.Lock()

    # ── API pública ──────────────────────────────────────────────────────────

    def handle(
        self,
        client_socket : socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        """
        Orquesta el ciclo completo para una conexión:
            recv → parse → [intercept?] → forward/tunnel → log → history.

        Args:
            client_socket  (socket.socket)  : Socket abierto con el navegador.
            client_address (tuple[str, int]): (ip, puerto) del cliente.
        """
        client_socket.settimeout(CONNECTION_TIMEOUT)

        try:
            raw = self._receive_all(client_socket)
            if not raw:
                return

            parsed = parse_request(raw)
            if not parsed:
                return

            # Filtrado de dominio antes de interceptar o dibujar en historial.
            filter_decision = self.host_filter.decide(parsed.host, parsed.port)
            if filter_decision == FILTER_DECISION_DROP:
                self._drop_silently(client_socket)
                return
            if filter_decision == FILTER_DECISION_BYPASS:
                self._forward_silently(client_socket, parsed, raw)
                return

            req_id = self._next_id()
            self._log_request(req_id, client_address, parsed, raw)
            display_request = build_display_http_message(raw)

            response    = b""
            display_response = ""
            resp_status = ""
            t_start     = time.perf_counter()
            pending_record_created = False

            # ── CU-04: Intercepción ────────────────────────────────────
            if self.intercept.intercept_enabled and parsed.method.upper() != "CONNECT":
                # Publicar inmediatamente en historial para que la GUI muestre
                # la fila con estado temporal mientras el hilo espera Forward.
                self.history.add(RequestRecord(
                    id=req_id, timestamp=datetime.now(),
                    method=parsed.method,
                    host=display_host(parsed.host, parsed.port),
                    port=parsed.port, path=parsed.path,
                    headers=parsed.headers, body=parsed.body,
                    raw_request=raw,
                    response_status="PENDIENTE",
                    response_raw=b"",
                    display_request=display_request,
                    display_response="",
                    duration_ms=0.0,
                    client_ip=client_address[0],
                ))
                pending_record_created = True

                pending = self.intercept.intercept(
                    req_id, raw, parsed, display_text=display_request,
                )
                print(
                    f"{Colors.YELLOW}[INTERCEPT #{req_id}] Petición pausada. "
                    f"Esperando decisión...{Colors.RESET}"
                )
                decision, raw = pending.wait(timeout=60.0)

                if decision == "drop":
                    print(f"{Colors.RED}[INTERCEPT #{req_id}] Descartada.{Colors.RESET}")
                    client_socket.sendall(
                        b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"
                    )
                    self.history.update(
                        req_id,
                        response_status="HTTP/1.1 403 Forbidden",
                        response_raw=b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n",
                        duration_ms=(time.perf_counter() - t_start) * 1000,
                    )
                    return

                if decision == "timeout":
                    print(f"{Colors.YELLOW}[INTERCEPT #{req_id}] Timeout → original.{Colors.RESET}")
                else:
                    print(f"{Colors.GREEN}[INTERCEPT #{req_id}] Reenviando.{Colors.RESET}")

            # ── Reenvío / MITM ──────────────────────────────────────────
            if parsed.method.upper() == "CONNECT":
                if self.certs_manager is not None:
                    # MITM: descifra TLS y pasa las peticiones por el pipeline
                    # completo (historial e intercepción gestionados internamente).
                    mitm_ok = MitmHandler(
                        host      = parsed.host,
                        port      = parsed.port,
                        req_id    = req_id,
                        certs     = self.certs_manager,
                        history   = self.history,
                        intercept = self.intercept,
                        next_id   = self._next_id,
                        client_ip = client_address[0],
                    ).handle(client_socket)
                    if mitm_ok:
                        return  # MitmHandler ya guardó cada request en el historial
                    print(
                        f"{Colors.YELLOW}[MITM #{req_id}] Falló MITM; "
                        f"fallback a túnel CONNECT.{Colors.RESET}"
                    )
                # Sin MITM: túnal ciego (comportamiento original)
                self._handle_https_tunnel(
                    client_socket, parsed.host, parsed.port, req_id,
                )
                resp_status = "TUNNEL"
            else:
                response = self._forward_request(parsed.host, parsed.port, raw) or b""
                if response:
                    display_response = build_display_http_message(response)
                    self._log_response(req_id, response)
                    client_socket.sendall(response)
                    try:
                        resp_status = (
                            response.split(b"\r\n")[0]
                            .decode("utf-8", errors="replace")
                        )
                    except Exception:
                        resp_status = ""

            duration_ms = (time.perf_counter() - t_start) * 1000

            # CU-03: Guardar en historial — display_host() produce el string
            # limpio de host para la GUI (ej. 'api.x.com:443', no 'api.x.com').
            # Este procesamiento ocurre aqui, en el hilo del proxy, para que
            # la interfaz grafica no tenga que construir strings en cada ciclo.
            if pending_record_created:
                self.history.update(
                    req_id,
                    raw_request=raw,
                    response_status=resp_status,
                    response_raw=response,
                    display_request=display_request,
                    display_response=display_response,
                    duration_ms=duration_ms,
                )
            else:
                self.history.add(RequestRecord(
                    id=req_id, timestamp=datetime.now(),
                    method=parsed.method,
                    host=display_host(parsed.host, parsed.port),  # string listo para GUI
                    port=parsed.port, path=parsed.path,
                    headers=parsed.headers, body=parsed.body,
                    raw_request=raw, response_status=resp_status,
                    response_raw=response,
                    display_request=display_request,
                    display_response=display_response,
                    duration_ms=duration_ms,
                    client_ip=client_address[0],
                ))

        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Handler: {exc}{Colors.RESET}")
        finally:
            # socket puede estar ya cerrado por MitmHandler o relay threads
            try:
                client_socket.close()
            except OSError:
                pass

    # ── Helpers privados ─────────────────────────────────────────────────────

    def _next_id(self) -> int:
        """Retorna el siguiente ID de petición de forma thread-safe."""
        with self._lock:
            self._count += 1
            return self._count

    def _receive_all(self, sock: socket.socket) -> bytes:
        """
        Lee una petición HTTP completa (headers + body si aplica).

        Returns:
            bytes: Bytes completos de la petición.
        """
        return _recv_http_message(sock, is_response=False)

    def _forward_request(
        self,
        host: str,
        port: int,
        raw : bytes,
    ) -> bytes | None:
        """
        Abre un socket hacia el servidor real, envía la petición y retorna
        la respuesta completa.

        Args:
            host (str)  : Hostname del servidor destino.
            port (int)  : Puerto del servidor destino.
            raw  (bytes): Petición HTTP cruda a reenviar.

        Returns:
            bytes | None: Respuesta completa, o None si hubo un error.
        """
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.settimeout(CONNECTION_TIMEOUT)
            srv.connect((host, port))
            srv.sendall(raw)
            response = _recv_http_message(srv, is_response=True)
            srv.close()
            return response
        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Forward {host}:{port} → {exc}{Colors.RESET}")
            return None

    def _handle_https_tunnel(
        self,
        client_socket: socket.socket,
        host         : str,
        port         : int,
        req_id       : int,
        silent       : bool = False,
    ) -> None:
        """
        Establece un relay TCP bidireccional para conexiones HTTPS.

        El proxy responde '200 Connection Established' y lanza dos hilos
        que retransmiten bytes en ambas direcciones sin descifrar TLS.

        Args:
            client_socket (socket.socket): Socket del navegador.
            host          (str)          : Hostname del servidor HTTPS.
            port          (int)          : Puerto del servidor HTTPS.
            req_id        (int)          : ID de la petición para el log.
        """
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.settimeout(CONNECTION_TIMEOUT)
            srv.connect((host, port))
            client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if not silent:
                print(f"{Colors.CYAN}[#{req_id}] Túnel HTTPS → {host}:{port}{Colors.RESET}")

            def relay(src: socket.socket, dst: socket.socket) -> None:
                try:
                    while True:
                        data = src.recv(BUFFER_SIZE)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    src.close()
                    dst.close()

            t1 = threading.Thread(target=relay, args=(client_socket, srv), daemon=True)
            t2 = threading.Thread(target=relay, args=(srv, client_socket), daemon=True)
            t1.start(); t2.start()
            t1.join();  t2.join()

        except Exception as exc:
            if not silent:
                print(f"{Colors.RED}[ERROR] HTTPS Tunnel: {exc}{Colors.RESET}")

    def _forward_silently(
        self,
        client_socket: socket.socket,
        parsed: ParsedRequest,
        raw: bytes,
    ) -> None:
        """Reenvía sin tocar UI/historial cuando una regla de filtro hace bypass."""
        if parsed.method.upper() == "CONNECT":
            self._handle_https_tunnel(
                client_socket,
                parsed.host,
                parsed.port,
                req_id=0,
                silent=True,
            )
            return

        response = self._forward_request(parsed.host, parsed.port, raw) or b""
        if response:
            client_socket.sendall(response)

    @staticmethod
    def _drop_silently(client_socket: socket.socket) -> None:
        """Responde 403 local sin agregar eventos al historial/UI."""
        try:
            client_socket.sendall(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"
            )
        except OSError:
            pass

    # ── Log helpers ──────────────────────────────────────────────────────────

    def _log_request(
        self,
        req_id       : int,
        client_addr  : tuple[str, int],
        parsed       : ParsedRequest,
        raw          : bytes,
    ) -> None:
        """Imprime la petición interceptada en consola con colores ANSI."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        sep = "─" * 60
        print(f"\n{Colors.BOLD}{Colors.BLUE}{sep}{Colors.RESET}")
        print(
            f"{Colors.BOLD}[REQUEST #{req_id}]{Colors.RESET} "
            f"{Colors.YELLOW}{timestamp}{Colors.RESET} | "
            f"Cliente: {client_addr[0]}:{client_addr[1]}"
        )
        print(
            f"{Colors.GREEN}{parsed.method}{Colors.RESET} "
            f"{Colors.CYAN}{parsed.host}:{parsed.port}{parsed.path}{Colors.RESET}"
        )
        print(f"{Colors.BLUE}{sep}{Colors.RESET}")
        try:
            decoded = raw.decode("utf-8", errors="replace")
            print(decoded[:1500])
            if len(decoded) > 1500:
                print(f"{Colors.YELLOW}... [{len(raw)} bytes totales]{Colors.RESET}")
        except Exception:
            print(f"[{len(raw)} bytes]")

    def _log_response(self, req_id: int, response: bytes) -> None:
        """Imprime el status code de la respuesta del servidor."""
        try:
            first_line = response.split(b"\r\n")[0].decode("utf-8", errors="replace")
        except Exception:
            first_line = "<no parseable>"
        sep = "─" * 60
        print(f"{Colors.BOLD}[RESPONSE #{req_id}]{Colors.RESET} {Colors.GREEN}{first_line}{Colors.RESET}")
        print(f"{Colors.BLUE}{sep}{Colors.RESET}\n")


def _normalize_text(value: str) -> str:
    """Normaliza saltos de línea para comparar contenido mostrado/actual."""
    return value.replace("\r\n", "\n").strip()


def _recv_http_message(sock: socket.socket, is_response: bool) -> bytes:
    """
    Lee un mensaje HTTP completo evitando truncados por límites de chunk TCP.
    """
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = _recv_chunk(sock)
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
            chunk = _recv_chunk(sock)
            if not chunk:
                break
            body += chunk
        return header_bytes + b"\r\n\r\n" + body[:content_length]

    # Sin framing explícito: para requests normalmente no hay body.
    # Para responses sin Content-Length ni chunked, la delimitación real es cierre de conexión.
    if not is_response:
        return header_bytes + b"\r\n\r\n" + body

    extra = _read_until_timeout(sock)
    return header_bytes + b"\r\n\r\n" + body + extra


def _recv_chunk(sock: socket.socket) -> bytes:
    try:
        return sock.recv(BUFFER_SIZE)
    except socket.timeout:
        return b""
    except OSError:
        return b""


def _read_until_timeout(sock: socket.socket) -> bytes:
    out = b""
    while True:
        chunk = _recv_chunk(sock)
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


def _read_chunked_body(sock: socket.socket, initial: bytes) -> bytes:
    data = initial
    while b"\r\n0\r\n\r\n" not in data:
        chunk = _recv_chunk(sock)
        if not chunk:
            break
        data += chunk
    return data
