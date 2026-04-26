"""
gui/settings_dialog.py
-----------------------
Ventana modal de Ajustes de NetLens.

Permite al usuario introducir y guardar su API Key de Google Gemini
sin tocar archivos de configuracion manualmente.

La clave se almacena en ~/.netlens/config.json via ConfigManager.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingenieria de Software 2
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from logic.config_manager import ConfigManager
from .colors import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    BG_DARK, BG_SECONDARY, BORDER,
    TEXT_MUTED, TEXT_PRIMARY,
)

_WINDOW_W = 520
_WINDOW_H = 390


class SettingsDialog(ctk.CTkToplevel):
    """
    Ventana modal de configuracion de NetLens.

    Muestra los ajustes actuales y permite guardar la API Key de Gemini.
    Se abre sobre la ventana principal sin bloquearla.

    Usage::

        dialog = SettingsDialog(parent=self)
    """

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self._cfg = ConfigManager.instance()
        self._configure_window(parent)
        self._build_ui()
        self._load_current_values()

    # ── Configuracion de ventana ───────────────────────────────────────────────

    def _configure_window(self, parent: tk.Widget) -> None:
        self.title("NetLens  —  Ajustes")
        self.geometry(f"{_WINDOW_W}x{_WINDOW_H}")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.attributes("-topmost", True)
        self.grab_set()   # bloquea la ventana principal hasta cerrar

        # Centrar sobre el padre
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x  = px + (pw - _WINDOW_W) // 2
        y  = py + (ph - _WINDOW_H) // 2
        self.geometry(f"+{x}+{y}")

    # ── Construccion de la UI ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construye todos los widgets de la ventana de ajustes."""

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="⚙️  Ajustes de NetLens",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=20, pady=16)

        ctk.CTkLabel(
            header, text="v2.0",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="right", padx=16)

        # ── Footer: botones ── (debe packearse ANTES que el body expand=True)
        footer = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=56)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="Cancelar",
            command=self.destroy,
            height=32, width=100, corner_radius=6,
            fg_color="transparent", hover_color=BG_DARK,
            border_color=BORDER, border_width=1,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=(6, 16), pady=12)

        ctk.CTkButton(
            footer, text="💾  Guardar",
            command=self._on_save,
            height=32, width=120, corner_radius=6,
            fg_color=ACCENT_BLUE, hover_color="#1a5fb4",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="right", padx=(0, 6), pady=12)

        ctk.CTkButton(
            footer, text="🗑  Borrar clave",
            command=self._on_clear,
            height=32, width=120, corner_radius=6,
            fg_color="transparent", hover_color="#2d0f0f",
            border_color=ACCENT_RED, border_width=1,
            text_color=ACCENT_RED,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=16, pady=12)

        # ── Cuerpo ── (expand=True, va DESPUES del footer)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # Sección API Key
        ctk.CTkLabel(
            body,
            text="🔑  API Key de Google Gemini",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT_BLUE,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            body,
            text=(
                "Obtén tu clave gratuita en: aistudio.google.com  "
                "(pestaña 'Get API Key')"
            ),
            font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # Campo de entrada (con máscara de contraseña)
        self._key_var = tk.StringVar()
        self._key_entry = ctk.CTkEntry(
            body,
            textvariable=self._key_var,
            show="●",
            height=36,
            placeholder_text="AIza...",
            fg_color=BG_SECONDARY,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._key_entry.pack(fill="x", pady=(0, 6))

        # Toggle mostrar/ocultar clave
        self._show_key = False
        self._btn_toggle = ctk.CTkButton(
            body,
            text="👁  Mostrar clave",
            command=self._toggle_key_visibility,
            height=26, width=130, corner_radius=4,
            fg_color="transparent", hover_color=BG_SECONDARY,
            border_color=BORDER, border_width=1,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._btn_toggle.pack(anchor="w", pady=(0, 10))

        # Separador
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))

        # Ruta del archivo de configuracion
        ctk.CTkLabel(
            body,
            text=f"📁  Configuracion guardada en: {self._cfg.config_path}",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=BORDER,
            anchor="w",
            wraplength=_WINDOW_W - 48,
            justify="left",
        ).pack(fill="x")

        # ── Label de estado ───────────────────────────────────────────────────
        self._status_lbl = ctk.CTkLabel(
            body, text="",
            font=ctk.CTkFont(size=11), text_color=ACCENT_GREEN,
        )
        self._status_lbl.pack(pady=(8, 0))

    # ── Logica de la UI ────────────────────────────────────────────────────────

    def _load_current_values(self) -> None:
        """Rellena el campo con la clave actualmente guardada (si existe)."""
        key = self._cfg.get_api_key()
        if key:
            self._key_var.set(key)
            self._status_lbl.configure(
                text="✓  API Key cargada desde la configuracion.",
                text_color=ACCENT_GREEN,
            )

    def _toggle_key_visibility(self) -> None:
        """Alterna entre mostrar y ocultar el texto de la clave."""
        self._show_key = not self._show_key
        self._key_entry.configure(show="" if self._show_key else "●")
        self._btn_toggle.configure(
            text="🙈  Ocultar clave" if self._show_key else "👁  Mostrar clave"
        )

    def _on_save(self) -> None:
        """Valida y guarda la API Key mediante ConfigManager."""
        key = self._key_var.get().strip()

        if not key:
            self._status_lbl.configure(
                text="⚠  El campo no puede estar vacío.",
                text_color=ACCENT_YELLOW,
            )
            return

        if not key.startswith("AIza") or len(key) < 20:
            self._status_lbl.configure(
                text="⚠  La clave no parece válida (debe empezar con 'AIza').",
                text_color=ACCENT_YELLOW,
            )
            return

        self._cfg.save_api_key(key)
        self._status_lbl.configure(
            text="✓  Clave guardada correctamente.",
            text_color=ACCENT_GREEN,
        )
        # Cerrar automaticamente tras 800 ms
        self.after(800, self.destroy)

    def _on_clear(self) -> None:
        """Borra la API Key del archivo de configuracion."""
        self._cfg.save_api_key("")
        self._key_var.set("")
        self._status_lbl.configure(
            text="🗑  Clave eliminada.",
            text_color=ACCENT_RED,
        )
