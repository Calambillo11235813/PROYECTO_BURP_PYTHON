"""
gui/header.py
-------------
Componente Header para NetLens.
"""

import tkinter as tk
import customtkinter as ctk
from typing import Callable, Optional


class HeaderFrame(ctk.CTkFrame):
    """
    Header principal de NetLens.
    Implementa un diseño limpio con pestañas de navegación centradas 
    y el estado del proxy en formato de 'cápsula'.
    """
    def __init__(
        self, 
        master: tk.Widget, 
        proxy_host: str = "127.0.0.1", 
        proxy_port: int = 8080, 
        on_tab_select: Optional[Callable[[str], None]] = None, 
        **kwargs
    ):
        # Frame base transparente para alojar la estructura
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)
        
        self.on_tab_select = on_tab_select
        self.active_tab = "Proxy"
        self.buttons = {}
        
        # Paleta de colores solicitada
        self.c_bg_dark = "#0d1117"
        self.c_border = "#30363d"
        self.c_text_primary = "#e6edf3"
        self.c_text_muted = "#8b949e"
        self.c_accent_blue = "#1f6feb"
        self.c_accent_green = "#238636" # Tono verde suave/éxito
        self.c_hover = "#2d333b"
        
        # --- Layout Principal ---
        # Contenedor superior para el contenido del header (Fijo a 52px de altura)
        self.main_container = ctk.CTkFrame(self, fg_color=self.c_bg_dark, corner_radius=0, height=52)
        self.main_container.pack(fill="x", side="top")
        self.main_container.pack_propagate(False)
        
        # Separador para emular un borde exclusivamente inferior de 1px
        self.bottom_border = tk.Frame(self, bg=self.c_border, height=1)
        self.bottom_border.pack(fill="x", side="bottom")

        # --- IZQUIERDA: Logo ---
        self.logo_label = ctk.CTkLabel(
            self.main_container,
            text="🔍 NetLens",
            font=ctk.CTkFont(family="Inter", size=20, weight="bold"),
            text_color=self.c_text_primary
        )
        self.logo_label.pack(side="left", padx=(24, 20))
        
        # --- CENTRO: Pestañas de Navegación ---
        self.tabs_container = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tabs_container.pack(side="left", fill="y", padx=10)
        
        tabs = ["Proxy", "Repeater", "Intruder", "Reporting"]
        for tab in tabs:
            btn = ctk.CTkButton(
                self.tabs_container,
                text=tab,
                font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
                fg_color="transparent",
                hover_color=self.c_hover,
                text_color=self.c_text_muted,
                corner_radius=6,
                width=80,
                height=32,
                command=lambda t=tab: self.select_tab(t)
            )
            btn.pack(side="left", padx=4, pady=10)
            self.buttons[tab] = btn
            
        # --- EXTREMO DERECHO: Info Académica ---
        self.version_label = ctk.CTkLabel(
            self.main_container,
            text="v2.0  |  Ingeniería de Software 2",
            font=ctk.CTkFont(family="Inter", size=11),
            text_color=self.c_text_muted
        )
        self.version_label.pack(side="right", padx=(10, 24))
        
        # --- DERECHA: Cápsula de Estado Proxy ---
        self.status_capsule = ctk.CTkFrame(
            self.main_container,
            fg_color="transparent",
            border_color=self.c_border,
            border_width=1,
            corner_radius=20,
            height=30
        )
        # Lo empacamos a la derecha, aparecerá antes de la "Info académica" (por el orden de pack)
        self.status_capsule.pack(side="right", padx=10, pady=11)
        
        # Acomodar el texto dentro de la cápsula
        self.status_indicator = ctk.CTkLabel(
            self.status_capsule,
            text="●",
            font=ctk.CTkFont(size=12),
            text_color=self.c_accent_green
        )
        self.status_indicator.pack(side="left", padx=(12, 6))
        
        self.status_text = ctk.CTkLabel(
            self.status_capsule,
            text=f"Proxy Activo: {proxy_host}:{proxy_port}",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=self.c_text_primary
        )
        self.status_text.pack(side="left", padx=(0, 12))
        
        # Setear estado inicial
        self.select_tab(self.active_tab)

    def select_tab(self, tab_name: str) -> None:
        """Cambia el estilo del botón activo y dispara el callback de navegación."""
        self.active_tab = tab_name
        
        for name, btn in self.buttons.items():
            if name == tab_name:
                # Tab activa: Texto resaltado y fondo sutil
                btn.configure(
                    text_color=self.c_accent_blue,
                    fg_color=self.c_hover
                )
            else:
                # Tab inactiva: Texto apagado y fondo transparente
                btn.configure(
                    text_color=self.c_text_muted,
                    fg_color="transparent"
                )
                
        if self.on_tab_select:
            self.on_tab_select(tab_name)
