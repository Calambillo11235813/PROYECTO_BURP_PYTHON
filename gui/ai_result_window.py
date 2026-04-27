"""
gui/ai_result_window.py
-----------------------
Ventana flotante (Tool Window) para mostrar las sugerencias de evasión de WAF
generadas por el motor de IA local (CU-13 - Módulo E).

Responsabilidades:
    - Mostrar las sugerencias en "Tarjetas" interactivas (Nombre, Payload, Razón).
    - Flotar sobre la aplicación principal sin bloquear el ciclo de eventos.
    - Proporcionar un botón en cada tarjeta para inyectar el payload (on_apply_callback).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import json
import re
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .colors import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    BG_DARK, BG_SECONDARY, BORDER,
    TEXT_MUTED, TEXT_PRIMARY,
)

_WINDOW_WIDTH  = 750
_WINDOW_HEIGHT = 600
_MIN_WIDTH     = 500
_MIN_HEIGHT    = 400


class AIResultWindow(ctk.CTkToplevel):
    """
    Ventana flotante que presenta las sugerencias de bypass WAF.
    """

    def __init__(
        self,
        parent: tk.Widget,
        result_text: str,
        request_summary: str = "",
        on_apply_callback: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_apply_callback = on_apply_callback
        self._parent = parent

        self._configure_window(parent, request_summary)
        
        self._header_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=64)
        self._header_frame.pack(fill="x", side="top")
        self._header_frame.pack_propagate(False)
        self._build_header(request_summary)

        self._scroll_frame = ctk.CTkScrollableFrame(self, fg_color=BG_DARK, corner_radius=0)
        self._scroll_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self._footer_frame = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=0, height=52)
        self._footer_frame.pack(fill="x", side="bottom")
        self._footer_frame.pack_propagate(False)
        self._build_footer()

        self.update_results(result_text, request_summary)

    def _configure_window(self, parent: tk.Widget, summary: str) -> None:
        self.title("🤖 Copiloto WAF — Sugerencias de Bypass")
        self.geometry(f"{_WINDOW_WIDTH}x{_WINDOW_HEIGHT}")
        self.minsize(_MIN_WIDTH, _MIN_HEIGHT)
        self.configure(fg_color=BG_DARK)
        self.resizable(True, True)

        # Hacer que la ventana flote por encima del padre sin bloquearlo
        self.attributes("-topmost", True)
        
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x  = px + (pw - _WINDOW_WIDTH)  // 2
        y  = py + (ph - _WINDOW_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

    def update_results(self, result_text: str, request_summary: str = "") -> None:
        """Limpia el contenido y redibuja las tarjetas con el nuevo resultado."""
        if request_summary:
            short = request_summary[:60] + ("…" if len(request_summary) > 60 else "")
            self.title(f"🤖 Bypass WAF · {short}")
            
            # Reconstruir header con nuevo summary (simplificado, limpiamos hijos)
            for widget in self._header_frame.winfo_children():
                widget.destroy()
            self._build_header(request_summary)

        # Limpiar contenido del scroll frame
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()

        # Separar el texto por técnicas o mostrar mensaje plano si hay error
        techniques = self._parse_techniques(result_text)
        
        if not techniques:
            # Fallback: renderizar como texto plano (ej. error o formato inesperado)
            self._render_plain_text(result_text)
        else:
            # Renderizar tarjetas
            for tech in techniques:
                self._render_card(tech)

    def _build_header(self, summary: str) -> None:
        title_frame = ctk.CTkFrame(self._header_frame, fg_color="transparent")
        title_frame.pack(side="left", padx=16, pady=8)

        ctk.CTkLabel(title_frame, text="🤖", font=ctk.CTkFont(size=28)).pack(side="left", padx=(0, 10))

        text_frame = ctk.CTkFrame(title_frame, fg_color="transparent")
        text_frame.pack(side="left")

        ctk.CTkLabel(
            text_frame, text="Copiloto de Evasión de WAF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        subtitle = summary[:80] if summary else "Análisis de petición bloqueada"
        ctk.CTkLabel(
            text_frame, text=subtitle,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            self._header_frame, text="⚡ IA Local",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=ACCENT_YELLOW, fg_color="#2d2a1e",
            corner_radius=4, padx=8, pady=4,
        ).pack(side="right", padx=16)

    def _build_footer(self) -> None:
        ctk.CTkLabel(
            self._footer_frame, text="⚠️  Usar solo en entornos autorizados.",
            font=ctk.CTkFont(size=10), text_color=BORDER,
        ).pack(side="left", padx=12)

        ctk.CTkButton(
            self._footer_frame, text="Cerrar",
            font=ctk.CTkFont(size=12), fg_color=BG_DARK, hover_color=BG_SECONDARY,
            text_color=TEXT_MUTED, border_color=BORDER, border_width=1,
            width=90, height=32, corner_radius=6, command=self.destroy,
        ).pack(side="right", padx=(4, 12), pady=10)

    def _parse_techniques(self, text: str) -> list[dict[str, str]]:
        """
        Intenta leer el texto como JSON con mucha tolerancia a errores comunes
        de formato y caracteres de escape generados por LLMs locales.
        """
        clean_text = text.strip()
        
        # Limpiar etiquetas markdown
        if clean_text.startswith("```"):
            lines = clean_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        # Limpiar escapes erróneos que algunos modelos introducen
        # ej. \[ {\ "tecnica1": "..." }\ ]
        clean_text = clean_text.replace('\\[', '[').replace('\\]', ']')
        clean_text = clean_text.replace('\\{', '{').replace('\\}', '}')
        clean_text = clean_text.replace('\\ "', '"')

        techniques = []
        
        def extract_technique(item: dict) -> dict | None:
            tec_name = item.get("tecnica", "")
            if not tec_name:
                for k, v in item.items():
                    if k.startswith("tecnica") and isinstance(v, str):
                        tec_name = v
                        break
            
            if tec_name or "payload" in item:
                return {
                    "name": tec_name if tec_name else "Técnica sin título",
                    "payload": str(item.get("payload", "Payload no extraído")),
                    "reason": str(item.get("explicacion", "Explicación no encontrada"))
                }
            return None

        # Intento 1: Parseo JSON directo
        try:
            data = json.loads(clean_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        tech = extract_technique(item)
                        if tech:
                            techniques.append(tech)
                if techniques:
                    return techniques
        except json.JSONDecodeError:
            pass
            
        # Intento 2: Extracción de objetos JSON aislados usando regex
        matches = re.findall(r'\{[^{}]*\}', clean_text, re.DOTALL)
        for match in matches:
            try:
                item = json.loads(match)
                if isinstance(item, dict):
                    tech = extract_technique(item)
                    if tech:
                        techniques.append(tech)
            except json.JSONDecodeError:
                continue

        return techniques

    def _render_plain_text(self, text: str) -> None:
        """
        Tarjeta de error/fallback cuando el parseo JSON falla o se recibe
        un mensaje de error contextualizado.

        Usa un fondo rojo tenue para diferenciarse visualmente de las tarjetas
        de sugerencias exitosas.
        """
        # Detectar si el contenido es un error para usar estilo rojo
        text_lo = text.lower()
        is_error = any(k in text_lo for k in (
            "error", "invalidada", "configurada", "conexión",
            "revocada", "403", "blocked",
        ))

        card_bg   = "#2d0f0f" if is_error else BG_SECONDARY
        title_txt = "❌  Error del Copiloto de IA" if is_error else "⚠️  Respuesta sin formato estándar"
        title_clr = ACCENT_RED if is_error else ACCENT_YELLOW

        card = ctk.CTkFrame(self._scroll_frame, fg_color=card_bg, corner_radius=8)
        card.pack(fill="x", padx=10, pady=6)

        # Header
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            header, text=title_txt,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=title_clr, anchor="w", justify="left",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            header, text="📋 Copiar al Portapapeles",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=ACCENT_BLUE, hover_color="#1a5fb4",
            width=155, height=26, corner_radius=4,
            command=lambda: self._copy_to_clipboard(text),
        ).pack(side="right")

        # Separador
        sep_color = "#5a1a1a" if is_error else BORDER
        tk.Frame(card, bg=sep_color, height=1).pack(fill="x", padx=10, pady=4)

        # Área de texto (sin fondo para heredar el del card)
        box = ctk.CTkTextbox(
            card,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="transparent",
            text_color="#f0a0a0" if is_error else TEXT_PRIMARY,
            wrap="word",
            height=220,
        )
        box.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        box.insert("1.0", text)
        box.configure(state="disabled")


    def _copy_to_clipboard(self, text: str) -> None:
        """Copia el texto al portapapeles del sistema."""
        self.clipboard_clear()
        self.clipboard_append(text)

    def _render_card(self, tech: dict[str, str]) -> None:
        card = ctk.CTkFrame(self._scroll_frame, fg_color=BG_SECONDARY, corner_radius=8)
        card.pack(fill="x", padx=10, pady=6)
        
        # Título
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        
        ctk.CTkLabel(
            header, text=tech["name"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=ACCENT_GREEN, anchor="w", justify="left"
        ).pack(side="left", fill="x", expand=True)
        
        # Botón Aplicar
        if self._on_apply_callback:
            ctk.CTkButton(
                header, text="⚡ Aplicar Sugerencia",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=ACCENT_BLUE, hover_color="#1a5fb4",
                width=130, height=26, corner_radius=4,
                command=lambda p=tech["payload"]: self._apply_payload(p)
            ).pack(side="right")
        
        # Separador
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=10, pady=4)
        
        # Payload (Textbox)
        payload_frame = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=6)
        payload_frame.pack(fill="x", padx=10, pady=2)
        
        ctk.CTkLabel(
            payload_frame, text="Payload:",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=TEXT_MUTED
        ).pack(anchor="w", padx=8, pady=(2, 0))
        
        # Altura dinámica basada en las líneas del payload, mínimo 40px
        payload_lines = len(tech["payload"].split("\n"))
        dynamic_height = max(40, payload_lines * 18 + 10)
        
        # Usamos Textbox para el payload para que pueda scrollear horizontalmente si es muy largo
        # o copiarse manualmente
        payload_box = ctk.CTkTextbox(
            payload_frame, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color="transparent", text_color="#00FF00", wrap="none", height=dynamic_height
        )
        payload_box.pack(fill="x", padx=6, pady=(0, 4))
        payload_box.insert("1.0", tech["payload"])
        payload_box.configure(state="disabled")
        
        # Explicación
        reason_frame = ctk.CTkFrame(card, fg_color="transparent")
        reason_frame.pack(fill="x", padx=10, pady=(2, 8))
        
        ctk.CTkLabel(
            reason_frame, text=tech["reason"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_PRIMARY, anchor="w", justify="left", wraplength=_WINDOW_WIDTH - 100
        ).pack(anchor="w", fill="x")

    def _apply_payload(self, payload: str) -> None:
        if self._on_apply_callback:
            self._on_apply_callback(payload)
