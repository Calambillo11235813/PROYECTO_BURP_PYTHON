"""
main.py
-------
Punto de entrada de Mini-Burp Suite.

Flujo de arranque:
    1. Parsear argumentos de línea de comandos (host, puerto).
    2. Crear ProxyServer y arrancarlo en un hilo daemon.
    3. Inicializar CustomTkinter (tema oscuro).
    4. Lanzar la ventana principal App y entrar en el bucle de eventos.

Uso:
    python main.py              → GUI + proxy en 127.0.0.1:8080
    python main.py 9090         → GUI + proxy en 127.0.0.1:9090
    python main.py 0.0.0.0 8080 → GUI + proxy en todas las interfaces

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

import sys
import threading

import customtkinter as ctk

from proxy.server import ProxyServer
from gui.app import App


def main() -> None:
    """Inicializa el proxy y la interfaz gráfica."""

    # ── 1. Parsear argumentos ──────────────────────────────────────────────────
    host = "127.0.0.1"
    port = 8080
    args = sys.argv[1:]
    if len(args) == 1:
        port = int(args[0])
    elif len(args) >= 2:
        host = args[0]
        port = int(args[1])

    # ── 2. Crear e iniciar el ProxyServer en un hilo daemon ───────────────────
    proxy = ProxyServer(host=host, port=port)
    proxy_thread = threading.Thread(target=proxy.start, daemon=True, name="ProxyServer")
    proxy_thread.start()

    # ── 3. Configurar CustomTkinter ────────────────────────────────────────────
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # ── 4. Lanzar la GUI ───────────────────────────────────────────────────────
    app = App(proxy=proxy)
    app.mainloop()


if __name__ == "__main__":
    main()
