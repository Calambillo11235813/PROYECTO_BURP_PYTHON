"""
gui/repeater_tab.py
-------------------
Pestaña 'Repeater' de Mini-Burp Suite (CU-05 y CU-06).

Responsabilidades:
    - Mostrar un panel de dos columnas: Request (editable) | Response (solo lectura).
    - Botón 'Send' que ejecuta Repeater.send() en un hilo background para
      no congelar la interfaz mientras espera la respuesta del servidor.
    - load_request(raw): método público llamado desde ProxyTab cuando
      el usuario hace clic en "Send to Repeater" (CU-05).

Patrón de threading:
    El envío HTTP se realiza en un Thread daemon para que la GUI no quede
    bloqueada. El resultado se publica de vuelta al hilo principal usando
    widget.after(0, callback), siguiendo el patrón estándar de Tkinter.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from logic.http_body import build_display_http_message
from repeater import Repeater, RepeaterResponse
from .utils import apply_syntax_highlighting
from .colors import (
    BG_DARK, BG_SECONDARY, BG_HOVER,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    TEXT_PRIMARY, TEXT_MUTED, BORDER,
)

# ── Constantes de layout ───────────────────────────────────────────────────────
EDITOR_FONT    = ("Consolas", 11)
LABEL_FONT_SZ  = 11
BTN_SEND_WIDTH = 110
BTN_SEND_H     = 36


class RepeaterTab(ctk.CTkFrame):
    """
    Panel de la pestaña 'Repeater'.

    Expone el método público `load_request(raw: str)` para que la pestaña
    Proxy pueda inyectar una petición seleccionada directamente (CU-05).

    Args:
        master: Widget padre (tab del CTkTabview).
    """

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, fg_color="transparent")
        self._repeater   = Repeater()
        self._sending    = False   # evita envíos dobles simultáneos

        self._build_toolbar()
        self._build_panels()

    # ── API pública ────────────────────────────────────────────────────────────

    def load_request(self, raw: str) -> None:
        """
        Carga una petición en el panel Request (CU-05: Clonación).

        Llamado desde ProxyTab cuando el usuario hace clic en
        'Send to Repeater'. Limpia el panel Response para que el
        usuario sepa que aún no ha enviado nada.

        Args:
            raw (str): Texto completo de la petición HTTP (headers + body).
        """
        self._set_request_text(raw)
        self._set_response_text("")
        self._status_lbl.configure(
            text="Petición cargada. Edítala y pulsa Send.",
            text_color=TEXT_MUTED,
        )

    # ── Construcción de la UI ──────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        """Barra superior: botón Send, selector de timeout y label de estado."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        # Botón Send (prominente)
        self._btn_send = ctk.CTkButton(
            bar,
            text="▶  Send",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT_BLUE,
            hover_color="#1a5fb4",
            text_color="#ffffff",
            width=BTN_SEND_WIDTH,
            height=BTN_SEND_H,
            corner_radius=6,
            command=self._on_send,
        )
        self._btn_send.pack(side="left", padx=12, pady=9)

        # Separador
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # Selector de timeout
        ctk.CTkLabel(
            bar, text="Timeout (s):",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 4))

        self._timeout_var = tk.StringVar(value="15")
        ctk.CTkEntry(
            bar,
            textvariable=self._timeout_var,
            width=48, height=28,
            fg_color=BG_DARK,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="center",
        ).pack(side="left", pady=9)

        # Label de estado (derecha)
        self._status_lbl = ctk.CTkLabel(
            bar,
            text="Listo.",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        )
        self._status_lbl.pack(side="right", padx=16)

    def _build_panels(self) -> None:
        """
        Panel dual Request / Response con layout grid correcto (estilo IDE).
        Idéntico al panel inferior de ProxyTab.
        """
        container = tk.Frame(self, bg=BG_SECONDARY)
        container.pack(fill="both", expand=True)

        container.grid_rowconfigure(0, weight=0)
        container.grid_rowconfigure(1, weight=1)
        # Dos columnas iguales al 50/50
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)

        # ── Encabezado izquierdo (Request) ──
        header_left = tk.Frame(container, bg=BG_SECONDARY, height=28)
        header_left.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=(4, 2))
        header_left.pack_propagate(False)

        tk.Label(
            header_left,
            text="📤  Request",
            font=("Consolas", 10, "bold"),
            fg=TEXT_MUTED,
            bg=BG_SECONDARY,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # ── Encabezado derecho (Response) ──
        header_right = tk.Frame(container, bg=BG_SECONDARY, height=28)
        header_right.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(4, 2))
        header_right.pack_propagate(False)

        tk.Label(
            header_right,
            text="📥  Response",
            font=("Consolas", 10, "bold"),
            fg=TEXT_MUTED,
            bg=BG_SECONDARY,
            anchor="w",
        ).pack(side="left")

        # ── Textbox Request (editable) ──
        req_frame = tk.Frame(container, bg=BORDER)
        req_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 3), pady=(0, 6))
        req_frame.grid_rowconfigure(0, weight=1)
        req_frame.grid_columnconfigure(0, weight=1)

        self._request_box = tk.Text(
            req_frame,
            font=("Consolas", 11),
            bg=BG_DARK, fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            selectbackground=ACCENT_BLUE,
            relief="flat", borderwidth=0,
            wrap="none", undo=True,
        )
        # Resaltado al editar
        self._request_box.bind("<KeyRelease>", self._on_request_edit)
        
        vsb_req = ttk.Scrollbar(req_frame, orient="vertical",   command=self._request_box.yview)
        hsb_req = ttk.Scrollbar(req_frame, orient="horizontal", command=self._request_box.xview)
        self._request_box.configure(yscrollcommand=vsb_req.set, xscrollcommand=hsb_req.set)
        vsb_req.grid(row=0, column=1, sticky="ns")
        hsb_req.grid(row=1, column=0, sticky="ew")
        self._request_box.grid(row=0, column=0, sticky="nsew")

        # ── Textbox Response (solo lectura) ──
        resp_frame = tk.Frame(container, bg=BORDER)
        resp_frame.grid(row=1, column=1, sticky="nsew", padx=(3, 8), pady=(0, 6))
        resp_frame.grid_rowconfigure(0, weight=1)
        resp_frame.grid_columnconfigure(0, weight=1)

        self._response_box = tk.Text(
            resp_frame,
            font=("Consolas", 11),
            bg=BG_DARK, fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            selectbackground=ACCENT_BLUE,
            relief="flat", borderwidth=0,
            wrap="none", state="disabled",
        )
        vsb_resp = ttk.Scrollbar(resp_frame, orient="vertical",   command=self._response_box.yview)
        hsb_resp = ttk.Scrollbar(resp_frame, orient="horizontal", command=self._response_box.xview)
        self._response_box.configure(yscrollcommand=vsb_resp.set, xscrollcommand=hsb_resp.set)
        vsb_resp.grid(row=0, column=1, sticky="ns")
        hsb_resp.grid(row=1, column=0, sticky="ew")
        self._response_box.grid(row=0, column=0, sticky="nsew")

    # ── Lógica de envío ────────────────────────────────────────────────────────

    def _on_send(self) -> None:
        """
        Lanza el envío HTTP en un hilo daemon para no bloquear la GUI.
        Deshabilita el botón Send mientras la petición está en vuelo.
        """
        if self._sending:
            return

        raw = self._request_box.get("1.0", "end-1c").strip()
        if not raw:
            self._status_lbl.configure(
                text="⚠  El panel Request está vacío.", text_color=ACCENT_YELLOW,
            )
            return

        timeout = self._parse_timeout()
        self._sending = True
        self._btn_send.configure(state="disabled", text="⏳  Enviando…")
        self._status_lbl.configure(text="Enviando petición…", text_color=TEXT_MUTED)
        self._set_response_text("")

        threading.Thread(
            target=self._send_in_background,
            args=(raw, timeout),
            daemon=True,
            name="RepeaterSend",
        ).start()

    def _send_in_background(self, raw: str, timeout: int) -> None:
        """
        Ejecuta Repeater.send() fuera del hilo principal.
        Publica el resultado de vuelta a Tkinter con after(0, ...).

        Args:
            raw     (str): Texto crudo de la petición a enviar.
            timeout (int): Segundos de timeout para requests.
        """
        response = self._repeater.send(raw, timeout=timeout)
        # Publicar resultado en el hilo de la GUI (thread-safe)
        self.after(0, lambda: self._on_send_complete(response))

    def _on_send_complete(self, response: RepeaterResponse) -> None:
        """
        Callback que corre en el hilo principal una vez terminado el envío.
        Actualiza la UI con el resultado de la petición.

        Args:
            response (RepeaterResponse): Resultado del envío.
        """
        self._sending = False
        self._btn_send.configure(state="normal", text="▶  Send")

        if response.success:
            self._set_response_text(response.as_raw_text())
            color = ACCENT_GREEN if response.status_code < 400 else ACCENT_RED
            self._status_lbl.configure(
                text=(
                    f"✓  {response.status_code}  │  "
                    f"{response.duration_ms:.0f} ms  │  "
                    f"{len(response.body)} bytes"
                ),
                text_color=color,
            )
        else:
            self._set_response_text(response.as_raw_text())
            self._status_lbl.configure(
                text=f"✗  Error: {response.error}",
                text_color=ACCENT_RED,
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _on_request_edit(self, _event: tk.Event) -> None:
        """Aplica colores en tiempo real mientras el usuario escribe."""
        apply_syntax_highlighting(self._request_box)

    def _set_request_text(self, text: str) -> None:
        """Reemplaza el contenido del panel Request."""
        self._request_box.delete("1.0", "end")
        if text:
            self._request_box.insert("1.0", text)
            apply_syntax_highlighting(self._request_box)

    def _set_response_text(self, text: str) -> None:
        """Reemplaza el contenido del panel Response (momentáneamente editable)."""
        self._response_box.configure(state="normal")
        self._response_box.delete("1.0", "end")
        if text:
            display = build_display_http_message(text.encode("utf-8", errors="replace"))
            self._response_box.insert("1.0", display)
            apply_syntax_highlighting(self._response_box)
        self._response_box.configure(state="disabled")

    def _parse_timeout(self) -> int:
        """
        Lee el campo timeout. Si el valor no es un entero válido,
        retorna el valor por defecto de 15s.

        Returns:
            Entero con los segundos de timeout.
        """
        try:
            value = int(self._timeout_var.get())
            return max(1, min(value, 120))  # clamp [1, 120]
        except ValueError:
            return 15
