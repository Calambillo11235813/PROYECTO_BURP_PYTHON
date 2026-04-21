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
from pathlib import Path

from core.certs_manager import CertsManager
from .host_filter import HostFilter
from .handler import ConnectionHandler, InterceptController
from .history import History

# ── Constantes del servidor ────────────────────────────────────────────────────
PROXY_HOST      = "127.0.0.1"
PROXY_PORT      = 8080
MAX_CONNECTIONS = 10  # backlog del socket (conexiones pendientes en cola)
FILTER_CONFIG_FILE = "filter_hosts.conf"

# ── Códigos de color ANSI (mínimos para el banner) ────────────────────────────
_CYAN   = "\033[96m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

_FILTER_MODES = ("blacklist", "whitelist")


class ProxyServer:
    """
    Servidor proxy HTTP de intercepción con soporte MITM SSL/TLS.

    Crea el socket TCP, acepta conexiones del navegador y delega el
    procesamiento de cada una a un ConnectionHandler ejecutado en su
    propio hilo daemon. Con MITM activo, las conexiones HTTPS se
    descifran y se exponen como peticiones HTTP planas.

    Attributes:
        host      (str)                : IP de escucha.
        port      (int)                : Puerto de escucha.
        history   (History)            : Historial persistente (CU-03).
        intercept (InterceptController): Controlador de intercepción (CU-04).
        certs     (CertsManager)       : Gestor de CA y certs de dominio MITM.

    Args:
        host (str): IP local. Por defecto '127.0.0.1'.
        port (int): Puerto local. Por defecto 8080.
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
        self.host_filter = HostFilter()
        self._filter_rules: dict[str, list[str]] = {
            "blacklist": [],
            "whitelist": [],
        }
        self.certs     = CertsManager()   # genera la CA si no existe
        self._handler  = ConnectionHandler(
            self.history,
            self.intercept,
            certs_manager=self.certs,
            host_filter=self.host_filter,
        )
        self._server_socket: socket.socket | None = None
        self._running  = False
        self._filter_config_path = (
            Path(__file__).resolve().parent.parent / FILTER_CONFIG_FILE
        )
        self.load_filter_config()

    # ── API de filtrado de host ─────────────────────────────────────────────

    def set_filter_mode(self, mode: str) -> None:
        normalized_mode = self._normalize_mode(mode)
        if not normalized_mode:
            return
        self.host_filter.set_mode(normalized_mode)
        self._sync_active_rules_to_host_filter()

    def get_filter_mode(self) -> str:
        return self.host_filter.mode

    def add_filter_pattern(self, pattern: str) -> bool:
        normalized = self._normalize_pattern(pattern)
        if not normalized:
            return False

        mode = self.host_filter.mode
        rules = self._filter_rules[mode]
        if normalized in rules:
            return False

        rules.append(normalized)
        self._sync_active_rules_to_host_filter()
        return True

    def remove_filter_pattern(self, pattern: str) -> bool:
        normalized = self._normalize_pattern(pattern)
        if not normalized:
            return False

        mode = self.host_filter.mode
        rules = self._filter_rules[mode]
        try:
            rules.remove(normalized)
        except ValueError:
            return False

        self._sync_active_rules_to_host_filter()
        return True

    def clear_filter_patterns(self) -> None:
        self._filter_rules[self.host_filter.mode] = []
        self._sync_active_rules_to_host_filter()

    def get_filter_patterns(self) -> list[str]:
        return list(self._filter_rules[self.host_filter.mode])

    def get_filter_patterns_for_mode(self, mode: str) -> list[str]:
        normalized_mode = self._normalize_mode(mode)
        if not normalized_mode:
            return []
        return list(self._filter_rules[normalized_mode])

    def get_filter_config_path(self) -> str:
        return str(self._filter_config_path)

    def load_filter_config(self) -> None:
        """
        Carga modo y reglas del archivo externo de filtro.

        Formato soportado:
            [settings]
            mode=blacklist|whitelist

            [blacklist]
            *.dominio.com

            [whitelist]
            localhost:3000

        También acepta líneas "pattern=..." dentro de [blacklist]/[whitelist].
        """
        path = self._filter_config_path
        if not path.exists():
            self.save_filter_config()
            return

        try:
            mode = self.host_filter.mode
            rules: dict[str, list[str]] = {
                "blacklist": [],
                "whitelist": [],
            }
            section = ""

            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith(";"):
                        continue

                    if line.startswith("[") and line.endswith("]"):
                        section = line[1:-1].strip().lower()
                        continue

                    if section == "settings":
                        if "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if key == "mode":
                            maybe_mode = self._normalize_mode(value)
                            if maybe_mode:
                                mode = maybe_mode
                        continue

                    if section in _FILTER_MODES:
                        value = line
                        if "=" in line:
                            key, maybe_value = line.split("=", 1)
                            key = key.strip().lower()
                            if key == "pattern":
                                value = maybe_value
                            else:
                                continue

                        normalized_pattern = self._normalize_pattern(value)
                        if normalized_pattern and normalized_pattern not in rules[section]:
                            rules[section].append(normalized_pattern)
                        continue

            self._filter_rules = rules
            self.host_filter.set_mode(mode)
            self._sync_active_rules_to_host_filter()

        except OSError:
            # Si falla lectura, mantener configuración en memoria actual.
            return

    def save_filter_config(self) -> None:
        """Persistencia de reglas actuales de filtro en archivo editable."""
        path = self._filter_config_path
        try:
            with path.open("w", encoding="utf-8") as fh:
                fh.write("# Reglas de filtro de host para Mini-Burp\n")
                fh.write("# Formato seccionado tipo INI\n")
                fh.write("# Puedes usar wildcards, ej: *.microsoft.com\n")
                fh.write("# También host:puerto, ej: localhost:3000\n\n")

                fh.write("[settings]\n")
                fh.write(f"mode={self.host_filter.mode}\n\n")

                fh.write("[blacklist]\n")
                for pattern in self._filter_rules["blacklist"]:
                    fh.write(f"{pattern}\n")

                fh.write("\n[whitelist]\n")
                for pattern in self._filter_rules["whitelist"]:
                    fh.write(f"{pattern}\n")
        except OSError:
            return

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        return (pattern or "").strip().lower()

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = (mode or "").strip().lower()
        if normalized in _FILTER_MODES:
            return normalized
        return ""

    def _sync_active_rules_to_host_filter(self) -> None:
        """Copia al motor de filtrado solo las reglas del modo activo."""
        mode = self.host_filter.mode
        self.host_filter.clear_patterns()
        for pattern in self._filter_rules[mode]:
            self.host_filter.add_pattern(pattern)

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
