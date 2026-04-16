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
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from .history import History, RequestRecord
from logic.parser import ParsedRequest, parse_request

# ── Constantes de bajo nivel (solo para este módulo) ──────────────────────────
BUFFER_SIZE        = 4096   # bytes por llamada a recv()
CONNECTION_TIMEOUT = 10     # segundos antes de cerrar un socket idle


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
        pending = PendingRequest(id=req_id, raw=raw, parsed=parsed)
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
        history  : History,
        intercept: InterceptController,
    ) -> None:
        self.history   = history
        self.intercept = intercept
        self._count    = 0
        self._lock     = threading.Lock()

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

            req_id = self._next_id()
            self._log_request(req_id, client_address, parsed, raw)

            response    = b""
            resp_status = ""
            t_start     = time.perf_counter()

            # ── CU-04: Intercepción ────────────────────────────────────
            if self.intercept.intercept_enabled and parsed.method.upper() != "CONNECT":
                pending = self.intercept.intercept(req_id, raw, parsed)
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
                    return

                if decision == "timeout":
                    print(f"{Colors.YELLOW}[INTERCEPT #{req_id}] Timeout → original.{Colors.RESET}")
                else:
                    print(f"{Colors.GREEN}[INTERCEPT #{req_id}] Reenviando.{Colors.RESET}")

            # ── Reenvío ────────────────────────────────────────────────
            if parsed.method.upper() == "CONNECT":
                self._handle_https_tunnel(client_socket, parsed.host, parsed.port, req_id)
                resp_status = "TUNNEL"
            else:
                response = self._forward_request(parsed.host, parsed.port, raw) or b""
                if response:
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

            # ── CU-03: Guardar en historial ────────────────────────────
            self.history.add(RequestRecord(
                id=req_id, timestamp=datetime.now(),
                method=parsed.method, host=parsed.host,
                port=parsed.port, path=parsed.path,
                headers=parsed.headers, body=parsed.body,
                raw_request=raw, response_status=resp_status,
                response_raw=response, duration_ms=duration_ms,
                client_ip=client_address[0],
            ))

        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Handler: {exc}{Colors.RESET}")
        finally:
            client_socket.close()

    # ── Helpers privados ─────────────────────────────────────────────────────

    def _next_id(self) -> int:
        """Retorna el siguiente ID de petición de forma thread-safe."""
        with self._lock:
            self._count += 1
            return self._count

    def _receive_all(self, sock: socket.socket) -> bytes:
        """
        Lee el socket en bloques de BUFFER_SIZE hasta que no hay más datos.

        Returns:
            bytes: Bytes completos de la petición.
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
            except socket.timeout:
                break
        return data

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
            response = b""
            while True:
                chunk = srv.recv(BUFFER_SIZE)
                if not chunk:
                    break
                response += chunk
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
            print(f"{Colors.RED}[ERROR] HTTPS Tunnel: {exc}{Colors.RESET}")

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
