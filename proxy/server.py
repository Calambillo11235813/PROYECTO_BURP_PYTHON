"""
proxy/server.py
---------------
Lógica de bajo nivel del socket servidor TCP.

Responsabilidades (y SOLO estas):
    - Crear el socket, hacer bind y listen.
    - Aceptar conexiones en un bucle bloqueante.
    - Lanzar un hilo de ConnectionHandler por cada conexión aceptada.
    - Detener el servidor de forma limpia.

Principio de Responsabilidad Única: este módulo NO parsea bytes HTTP ni
procesa el contenido de las peticiones. Eso es responsabilidad de handler.py.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import socket
import threading

from .handler import ConnectionHandler, InterceptController
from .history import History

# ── Constantes del servidor ────────────────────────────────────────────────────
PROXY_HOST      = "127.0.0.1"
PROXY_PORT      = 8080
MAX_CONNECTIONS = 10  # backlog del socket (conexiones pendientes en cola)

# ── Códigos de color ANSI (mínimos para el banner) ────────────────────────────
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"


class ProxyServer:
    """
    Servidor proxy HTTP de intercepción.

    Crea el socket TCP, acepta conexiones del navegador y delega el
    procesamiento de cada una a un ConnectionHandler ejecutado en su
    propio hilo daemon.

    Attributes:
        host      (str)                : IP de escucha.
        port      (int)                : Puerto de escucha.
        history   (History)            : Historial persistente de peticiones (CU-03).
        intercept (InterceptController): Controlador de intercepción (CU-04).

    Args:
        host (str): IP local. Por defecto '127.0.0.1'.
        port (int): Puerto local. Por defecto 8080.

    Ejemplo:
        proxy = ProxyServer()
        proxy.intercept.enable()   # activar intercepción antes de iniciar
        proxy.start()              # bloqueante hasta Ctrl+C
    """

    def __init__(
        self,
        host: str = PROXY_HOST,
        port: int = PROXY_PORT,
    ) -> None:
        self.host      = host
        self.port      = port
        self.history   = History()
        self.intercept = InterceptController()
        self._handler  = ConnectionHandler(self.history, self.intercept)
        self._server_socket: socket.socket | None = None
        self._running  = False

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Inicializa el socket servidor y entra en el bucle de accept().

        Bloquea hasta que se llame a stop() o el usuario presione Ctrl+C.
        Cada conexión aceptada lanza un hilo daemon con ConnectionHandler.handle().

        Raises:
            OSError: Si el puerto ya está en uso y SO_REUSEADDR no es suficiente.
        """
        # AF_INET = IPv4 | SOCK_STREAM = TCP orientado a conexión
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SO_REUSEADDR: reutilizar el puerto tras un reinicio rápido
        # sin esperar el tiempo de TIME_WAIT del sistema operativo
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(MAX_CONNECTIONS)
        self._running = True

        self._print_banner()
        print(f"{_GREEN}[+] Proxy escuchando en {self.host}:{self.port}{_RESET}\n")

        try:
            while self._running:
                try:
                    # Bloquea hasta que llega una nueva conexión TCP
                    client_socket, client_address = self._server_socket.accept()

                    # Lanzar un hilo por conexión → múltiples clientes simultáneos
                    thread = threading.Thread(
                        target=self._handler.handle,
                        args=(client_socket, client_address),
                        daemon=True,  # muere automáticamente al cerrar el proceso
                    )
                    thread.start()

                except OSError:
                    # El socket fue cerrado desde otro hilo (stop() o Ctrl+C)
                    break

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """
        Detiene el servidor y libera el socket de forma limpia.

        Las conexiones activas (hilos daemon) finalizan naturalmente.
        """
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        print(f"\n{_YELLOW}[!] Proxy detenido.{_RESET}")

    # ── Propiedad de compatibilidad ──────────────────────────────────────────

    @property
    def _request_count(self) -> int:
        """Número de peticiones procesadas (delegado al handler)."""
        return self._handler._count

    # ── Banner ───────────────────────────────────────────────────────────────

    def _print_banner(self) -> None:
        """Imprime el banner de bienvenida con el estado actual del proxy."""
        intercept_state = f"{_RED}ON{_RESET}" if self.intercept.intercept_enabled else "OFF"
        banner = (
            f"\n{_BOLD}{_CYAN}"
            f"╔══════════════════════════════════════════════════════════╗\n"
            f"║      HTTP PROXY INTERCEPTOR  v2.0                       ║\n"
            f"║      Ingeniería de Software 2 — Pentesting Tool         ║\n"
            f"║      Inspirado en Burp Suite                            ║\n"
            f"╚══════════════════════════════════════════════════════════╝"
            f"{_RESET}\n\n"
            f"  Host: {_YELLOW}{self.host}{_RESET}   "
            f"Puerto: {_YELLOW}{self.port}{_RESET}   "
            f"Intercept: {intercept_state}\n"
            f"  Presiona {_RED}Ctrl+C{_RESET} para detener.\n"
        )
        print(banner)
