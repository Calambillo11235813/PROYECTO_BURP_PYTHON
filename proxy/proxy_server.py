"""
proxy_server.py
---------------
Proxy HTTP interceptor implementado desde cero usando socket y threading.
Inspirado en herramientas de pentesting como Burp Suite.

Autor: Clase de Ingeniería de Software 2
"""

import socket
import threading
import sys
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  Constantes de configuración
# ─────────────────────────────────────────────
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
BUFFER_SIZE = 4096          # bytes por lectura de socket
MAX_CONNECTIONS = 10        # backlog del socket del servidor
CONNECTION_TIMEOUT = 10     # segundos antes de cerrar un socket idle

# Colores ANSI para la consola (mejora legibilidad del output)
class Colors:
    HEADER   = "\033[95m"
    BLUE     = "\033[94m"
    CYAN     = "\033[96m"
    GREEN    = "\033[92m"
    YELLOW   = "\033[93m"
    RED      = "\033[91m"
    BOLD     = "\033[1m"
    RESET    = "\033[0m"


# ─────────────────────────────────────────────
#  Clase principal: ProxyServer
# ─────────────────────────────────────────────
class ProxyServer:
    """
    Servidor proxy HTTP de intercepción.

    Flujo de trabajo:
        Navegador → ProxyServer.listen() → _handle_client() →
        _parse_request() → _forward_request() → respuesta al navegador
    """

    def __init__(self, host: str = PROXY_HOST, port: int = PROXY_PORT):
        self.host = host
        self.port = port
        self._server_socket: socket.socket | None = None
        self._running = False
        self._request_count = 0          # contador global (compartido entre hilos)
        self._lock = threading.Lock()    # protege el contador

    # ──────────────────────────────────────────
    #  Iniciar el servidor
    # ──────────────────────────────────────────
    def start(self) -> None:
        """Crea el socket servidor y entra en el bucle de aceptación de clientes."""

        # AF_INET  → IPv4
        # SOCK_STREAM → TCP (orientado a conexión)
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SO_REUSEADDR: permite reutilizar el puerto inmediatamente después de
        # cerrar el servidor (evita "Address already in use" en reinicios rápidos)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(MAX_CONNECTIONS)
        self._running = True

        self._print_banner()
        print(f"{Colors.GREEN}[+] Proxy escuchando en {self.host}:{self.port}{Colors.RESET}\n")

        try:
            while self._running:
                try:
                    # Bloquea hasta que llega una nueva conexión del navegador
                    client_socket, client_address = self._server_socket.accept()

                    # Cada conexión se maneja en su propio hilo para no bloquear
                    # el bucle principal → múltiples conexiones simultáneas
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True   # el hilo muere cuando muere el proceso principal
                    )
                    thread.start()

                except OSError:
                    # El socket fue cerrado (Ctrl+C) → salimos del bucle
                    break

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ──────────────────────────────────────────
    #  Detener el servidor
    # ──────────────────────────────────────────
    def stop(self) -> None:
        """Detiene el servidor y libera el socket."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        print(f"\n{Colors.YELLOW}[!] Proxy detenido.{Colors.RESET}")

    # ──────────────────────────────────────────
    #  Handler de cada cliente (ejecutado en su propio hilo)
    # ──────────────────────────────────────────
    def _handle_client(self, client_socket: socket.socket, client_address: tuple) -> None:
        """
        Recibe la petición del navegador, la intercepta (imprime en consola)
        y la reenvía al servidor destino.

        Parámetros
        ----------
        client_socket : socket del navegador/cliente
        client_address : (ip, puerto) del cliente
        """
        client_socket.settimeout(CONNECTION_TIMEOUT)

        try:
            # 1. Recibir la petición cruda del navegador
            raw_request = self._receive_all(client_socket)
            if not raw_request:
                return

            # 2. Parsear para extraer método, host, puerto y path
            parsed = self._parse_request(raw_request)
            if not parsed:
                return

            method, host, port, path, headers, body = parsed

            # 3. Incrementar contador (thread-safe con Lock)
            with self._lock:
                self._request_count += 1
                req_id = self._request_count

            # 4. Interceptar → imprimir en consola
            self._log_request(req_id, client_address, method, host, port, path, raw_request)

            # 5. Reenviar al servidor destino y obtener la respuesta
            if method.upper() == "CONNECT":
                # HTTPS tunneling
                self._handle_https_tunnel(client_socket, host, port, req_id)
            else:
                # HTTP normal
                response = self._forward_request(host, port, raw_request)
                if response:
                    self._log_response(req_id, response)
                    client_socket.sendall(response)

        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Hilo cliente: {exc}{Colors.RESET}")
        finally:
            client_socket.close()

    # ──────────────────────────────────────────
    #  Leer datos del socket hasta que no haya más
    # ──────────────────────────────────────────
    def _receive_all(self, sock: socket.socket) -> bytes:
        """
        Lee bloques de BUFFER_SIZE hasta que el socket no envía más datos.
        Retorna los bytes completos de la petición.
        """
        data = b""
        while True:
            try:
                chunk = sock.recv(BUFFER_SIZE)
                if not chunk:
                    break
                data += chunk
                # Si recibimos menos de BUFFER_SIZE, probablemente no hay más datos
                if len(chunk) < BUFFER_SIZE:
                    break
            except socket.timeout:
                break
        return data

    # ──────────────────────────────────────────
    #  Parsear la petición HTTP
    # ──────────────────────────────────────────
    def _parse_request(self, raw_request: bytes) -> tuple | None:
        """
        Descompone la petición HTTP cruda en sus partes:
            (método, host, puerto, path, headers_dict, body)

        Retorna None si la petición no es válida.
        """
        try:
            # Separar cabeceras del cuerpo
            if b"\r\n\r\n" in raw_request:
                header_section, body = raw_request.split(b"\r\n\r\n", 1)
            else:
                header_section = raw_request
                body = b""

            lines = header_section.decode("utf-8", errors="replace").split("\r\n")
            request_line = lines[0]           # ej: "GET http://example.com/ HTTP/1.1"
            parts = request_line.split(" ")

            if len(parts) < 2:
                return None

            method = parts[0]
            url    = parts[1]

            # Parsear HOST y PUERTO del URL
            host = ""
            port = 80

            if method.upper() == "CONNECT":
                # CONNECT host:443 HTTP/1.1  (HTTPS)
                host_port = url.split(":")
                host = host_port[0]
                port = int(host_port[1]) if len(host_port) > 1 else 443
                path = url
            elif url.startswith("http://"):
                url_stripped = url[7:]      # quitar "http://"
                if "/" in url_stripped:
                    host_part, path = url_stripped.split("/", 1)
                    path = "/" + path
                else:
                    host_part = url_stripped
                    path = "/"
                if ":" in host_part:
                    host, port_str = host_part.split(":", 1)
                    port = int(port_str)
                else:
                    host = host_part
            else:
                # Buscar Host en las cabeceras
                path = url
                for line in lines[1:]:
                    if line.lower().startswith("host:"):
                        host_value = line.split(":", 1)[1].strip()
                        if ":" in host_value:
                            host, port_str = host_value.split(":", 1)
                            port = int(port_str)
                        else:
                            host = host_value
                        break

            # Parsear cabeceras como diccionario
            headers = {}
            for line in lines[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key.strip()] = value.strip()

            return method, host, port, path, headers, body

        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Parseando petición: {exc}{Colors.RESET}")
            return None

    # ──────────────────────────────────────────
    #  Reenviar petición HTTP al destino
    # ──────────────────────────────────────────
    def _forward_request(self, host: str, port: int, raw_request: bytes) -> bytes | None:
        """
        Abre un socket nuevo hacia el servidor destino,
        envía la petición original y devuelve la respuesta completa.
        """
        try:
            # Resolver DNS y crear socket hacia el servidor real
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(CONNECTION_TIMEOUT)
            server_socket.connect((host, port))
            server_socket.sendall(raw_request)

            # Leer la respuesta completa
            response = b""
            while True:
                chunk = server_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                response += chunk

            server_socket.close()
            return response

        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Reenviando a {host}:{port} → {exc}{Colors.RESET}")
            return None

    # ──────────────────────────────────────────
    #  Tunnel HTTPS (método CONNECT)
    # ──────────────────────────────────────────
    def _handle_https_tunnel(
        self,
        client_socket: socket.socket,
        host: str,
        port: int,
        req_id: int
    ) -> None:
        """
        Establece un túnel TCP entre el navegador y el servidor HTTPS.

        Nota: en un proxy completo (como Burp Suite) se haría un
        SSL MITM aquí. Esta implementación hace un forward transparente
        (tunnel) sin descifrar el TLS.
        """
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(CONNECTION_TIMEOUT)
            server_socket.connect((host, port))

            # Informar al navegador que el túnel está listo
            client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            print(f"{Colors.CYAN}[#{req_id}] Túnel HTTPS establecido → {host}:{port}{Colors.RESET}")

            # Relay bidireccional de datos en dos hilos
            def relay(src, dst):
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

            t1 = threading.Thread(target=relay, args=(client_socket, server_socket), daemon=True)
            t2 = threading.Thread(target=relay, args=(server_socket, client_socket), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        except Exception as exc:
            print(f"{Colors.RED}[ERROR] Tunnel HTTPS: {exc}{Colors.RESET}")

    # ──────────────────────────────────────────
    #  Logging de peticiones (interceptación)
    # ──────────────────────────────────────────
    def _log_request(
        self,
        req_id: int,
        client_addr: tuple,
        method: str,
        host: str,
        port: int,
        path: str,
        raw: bytes
    ) -> None:
        """Imprime la petición interceptada de forma clara en la consola."""

        timestamp = datetime.now().strftime("%H:%M:%S")
        separator = "─" * 60

        print(f"\n{Colors.BOLD}{Colors.BLUE}{separator}{Colors.RESET}")
        print(
            f"{Colors.BOLD}[REQUEST #{req_id}]{Colors.RESET} "
            f"{Colors.YELLOW}{timestamp}{Colors.RESET} | "
            f"Cliente: {client_addr[0]}:{client_addr[1]}"
        )
        print(f"{Colors.GREEN}{method}{Colors.RESET} {Colors.CYAN}{host}:{port}{path}{Colors.RESET}")
        print(f"{Colors.BLUE}{separator}{Colors.RESET}")

        # Imprimir cabeceras y (si hay) cuerpo
        try:
            decoded = raw.decode("utf-8", errors="replace")
            # Mostrar solo las primeras 1500 chars para no saturar la consola
            if len(decoded) > 1500:
                print(decoded[:1500])
                print(f"{Colors.YELLOW}... [truncado, {len(raw)} bytes totales]{Colors.RESET}")
            else:
                print(decoded)
        except Exception:
            print(f"[bytes crudos: {len(raw)} bytes]")

    # ──────────────────────────────────────────
    #  Logging de respuestas
    # ──────────────────────────────────────────
    def _log_response(self, req_id: int, response: bytes) -> None:
        """Imprime el status de la respuesta del servidor."""

        try:
            first_line = response.split(b"\r\n")[0].decode("utf-8", errors="replace")
        except Exception:
            first_line = "<no parseable>"

        separator = "─" * 60
        print(f"{Colors.BOLD}[RESPONSE #{req_id}]{Colors.RESET} {Colors.GREEN}{first_line}{Colors.RESET}")
        print(f"{Colors.BLUE}{separator}{Colors.RESET}\n")

    # ──────────────────────────────────────────
    #  Banner de bienvenida
    # ──────────────────────────────────────────
    def _print_banner(self) -> None:
        banner = f"""
{Colors.BOLD}{Colors.CYAN}
╔══════════════════════════════════════════════════════════╗
║          HTTP PROXY INTERCEPTOR  v1.0                    ║
║          Ingeniería de Software 2 — Pentesting Tool      ║
║          Inspirado en Burp Suite                         ║
╚══════════════════════════════════════════════════════════╝
{Colors.RESET}
  Configura tu navegador con el proxy:
  {Colors.YELLOW}Host: {self.host}   Puerto: {self.port}{Colors.RESET}

  Presiona {Colors.RED}Ctrl+C{Colors.RESET} para detener el servidor.
"""
        print(banner)
