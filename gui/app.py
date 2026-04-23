"""
gui/app.py
----------
Ventana principal de Mini-Burp Suite.

Estructura:
    - Header: logo, estado del proxy, créditos.
    - CTkTabview: pestañas Proxy, Repeater, Intruder, Reportings.
    - Status bar: contador de peticiones y estado del intercept.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from proxy.server import ProxyServer
from .proxy_tab import ProxyTab
from .repeater_tab import RepeaterTab
from .intruder_tab import IntruderTab
from .reporting_tab import ReportingTab
from .header import HeaderFrame
from .colors import (
    BG_DARK, BG_SECONDARY, ACCENT_BLUE, ACCENT_GREEN,
    ACCENT_RED, TEXT_PRIMARY, TEXT_MUTED, BORDER,
)

# ── Constantes de la ventana ───────────────────────────────────────────────────
WINDOW_TITLE  = "Mini-Burp Suite  v2.0  —  Ingeniería de Software 2"
WINDOW_WIDTH  = 1260
WINDOW_HEIGHT = 800
MIN_WIDTH     = 960
MIN_HEIGHT    = 620


class App(ctk.CTk):
    """
    Ventana raíz de la aplicación.

    Hereda de ctk.CTk (en lugar de tk.Tk) para usar el sistema de temas
    y widgets de CustomTkinter.

    Args:
        proxy (ProxyServer): Instancia del proxy ya iniciado en hilo daemon.
    """

    def __init__(self, proxy: ProxyServer) -> None:
        super().__init__()
        self.proxy = proxy
     
        self._configure_window()
        self._build_header()
        self._build_tabs()
        self._build_status_bar()

    # ── Configuración de la ventana ────────────────────────────────────────────

    def _configure_window(self) -> None:
        """Tamaño, título, color de fondo y posicionamiento centrado."""
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.configure(fg_color=BG_DARK)

        # Centrar la ventana en la pantalla
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - WINDOW_WIDTH)  // 2
        y = (self.winfo_screenheight() - WINDOW_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        """Barra superior con logo, estado del proxy y navegación."""
        self._header = HeaderFrame(
            self,
            proxy_host=self.proxy.host,
            proxy_port=self.proxy.port,
            on_tab_select=self._on_tab_select
        )
        self._header.pack(fill="x", side="top")

    def _on_tab_select(self, tab_name: str) -> None:
        """Callback al hacer clic en las pestañas del Header."""
        if hasattr(self, "_tab_view"):
            self._tab_view.set(f"  {tab_name}  ")

    # ── Tab View ───────────────────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        """CTkTabview principal con las pestañas Proxy, Repeater e Intruder."""
        self._tab_view = ctk.CTkTabview(
            self,
            fg_color=BG_SECONDARY,
            segmented_button_fg_color=BG_DARK,
            segmented_button_selected_color=ACCENT_BLUE,
            segmented_button_selected_hover_color="#1a5fb4",
            segmented_button_unselected_color=BG_SECONDARY,
            segmented_button_unselected_hover_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            corner_radius=8,
        )
        self._tab_view.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        # ── Pestaña Proxy ────────────────────────────────────────────────────
        self._tab_view.add("  Proxy  ")
        self._proxy_tab = ProxyTab(
            master=self._tab_view.tab("  Proxy  "),
            proxy=self.proxy,
            on_send_to_repeater=self.switch_to_repeater,
        )
        self._proxy_tab.pack(fill="both", expand=True)

        # ── Pestaña Repeater ──────────────────────────────────────────
        self._tab_view.add("  Repeater  ")
        self._repeater_tab = RepeaterTab(
            master=self._tab_view.tab("  Repeater  "),
        )
        self._repeater_tab.pack(fill="both", expand=True)

        # ── Pestaña Intruder ──────────────────────────────────────────────────
        self._tab_view.add("  Intruder  ")
        self._intruder_tab = IntruderTab(
            master=self._tab_view.tab("  Intruder  "),
        )
        self._intruder_tab.pack(fill="both", expand=True)

        # ── Pestaña Reporting ──────────────────────────────────────────────────
        self._tab_view.add("  Reporting  ")
        self._reporting_tab = ReportingTab(
            master=self._tab_view.tab("  Reporting  "),
        )
        self._reporting_tab.pack(fill="both", expand=True)

        # Enlazar el botón de escaneo pasivo con el historial actual
        self._reporting_tab.btn_scan.configure(
            command=lambda: self._reporting_tab.run_analysis(self.proxy.history.all())
        )

        # Ocultar los botones nativos DESPUÉS de añadir todas las pestañas
        self._tab_view._segmented_button.grid_remove()

    # ── API pública de navegación entre pestañas ────────────────────────

    def switch_to_repeater(self, raw_request: str) -> None:
        """
        Carga una petición en el Repeater y cambia el foco a esa pestaña (CU-05).

        Llamado desde ProxyTab cuando el usuario hace clic en 'Send to Repeater'.

        Args:
            raw_request (str): Texto completo de la petición HTTP.
        """
        self._repeater_tab.load_request(raw_request)
        self._tab_view.set("  Repeater  ")
        self._header.select_tab("Repeater")

    def switch_to_intruder(self, raw_request: str) -> None:
        """
        Carga una petición en el Intruder y cambia el foco a esa pestaña.

        Args:
            raw_request (str): Texto completo de la petición HTTP.
        """
        self._intruder_tab.load_request(raw_request)
        self._tab_view.set("  Intruder  ")
        self._header.select_tab("Intruder")

    # ── Placeholder (módulos futuros) ────────────────────────────────────────

    def _build_placeholder(
        self,
        parent  : tk.Widget,
        icon    : str,
        title   : str,
        subtitle: str,
        detail  : str,
    ) -> None:
        """
        Panel de placeholder para módulos aún no implementados.

        Args:
            parent   : Widget padre del tab.
            icon     : Emoji o ícono para mostrar.
            title    : Nombre del módulo.
            subtitle : Descripción breve.
            detail   : Explicación más detallada (multilínea).
        """
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame, text=icon,
            font=ctk.CTkFont(size=56),
        ).pack(expand=False, pady=(100, 4))

        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            frame, text=subtitle,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=ACCENT_BLUE,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            frame, text=detail,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            justify="center",
        ).pack()

        ctk.CTkLabel(
            frame, text="— Próximamente —",
            font=ctk.CTkFont(size=11),
            text_color=BORDER,
        ).pack(pady=16)

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        """Barra inferior con info de intercept y atajo de teclado."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar,
            text="Configura tu navegador:  Proxy → 127.0.0.1 : 8080",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=12)

        ctk.CTkLabel(
            bar, text="Ctrl+C en consola para detener el proxy",
            font=ctk.CTkFont(size=10), text_color=BORDER,
        ).pack(side="right", padx=12)
