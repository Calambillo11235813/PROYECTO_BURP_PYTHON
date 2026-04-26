"""
gui/repeater_tab.py
-------------------
Pestaña 'Repeater' de Mini-Burp Suite (CU-05, CU-06 y CU-13).

Responsabilidades:
    - Mostrar un panel de dos columnas: Request (editable) | Response (solo lectura).
    - Botón 'Send' que ejecuta Repeater.send() en un hilo background para
      no congelar la interfaz mientras espera la respuesta del servidor.
    - Botón 'Ask AI (Bypass WAF)' que consulta al motor de IA local (Ollama)
      para obtener sugerencias de evasión de WAF cuando la respuesta es un
      bloqueo (403, 429, etc.) — CU-13 Módulo E.
    - load_request(raw): método público llamado desde ProxyTab cuando
      el usuario hace clic en "Send to Repeater" (CU-05).

Patrón de threading:
    Tanto el envío HTTP como la consulta a la IA se realizan en hilos
    daemon separados para no bloquear el hilo principal de Tkinter.
    Los resultados se publican de vuelta con widget.after(0, callback).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from logic.http_body import build_display_http_message
from logic.gemini_engine import GeminiEngine, GeminiEngineError, GeminiConnectionError, GeminiConfigError
from repeater import Repeater, RepeaterResponse
from .ai_result_window import AIResultWindow
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
        self._repeater          = Repeater()
        self._ai_engine         = GeminiEngine()   # CU-13: motor de IA (Gemini)
        self._sending           = False   # evita envíos dobles simultáneos
        self._asking_ai         = False   # evita consultas IA dobles simultáneas
        self.ai_window          = None    # Referencia a la ventana flotante de sugerencias
        self._original_request  = ""      # copia intacta al cargar (para Restablecer)

        self._build_toolbar()
        self._build_panels()

    # ── API pública ────────────────────────────────────────────────────────────

    def load_request(self, raw: str) -> None:
        """
        Carga una petición en el panel Request (CU-05: Clonación).

        Guarda una copia intacta en ``_original_request`` para que el botón
        Restablecer pueda devolver el panel a su estado inicial.

        Args:
            raw (str): Texto completo de la petición HTTP (headers + body).
        """
        self._original_request = raw          # guardar copia para Restablecer
        self._set_request_text(raw)
        self._set_response_text("")
        self._status_lbl.configure(
            text="Petición cargada. Edítala y pulsa Enviar.",
            text_color=TEXT_MUTED,
        )

    # ── Construcción de la UI ──────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        """Barra superior: botón Send, selector de timeout y label de estado."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        # Botón Enviar (prominente)
        self._btn_send = ctk.CTkButton(
            bar,
            text="▶  Enviar",
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

        # Botón Restablecer — restaura la petición original
        self._btn_reset = ctk.CTkButton(
            bar,
            text="🔄  Restablecer",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            border_color=BORDER,
            border_width=1,
            width=140,
            height=BTN_SEND_H,
            corner_radius=6,
            command=self._on_reset,
        )
        self._btn_reset.pack(side="left", padx=(0, 6), pady=9)

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

        # ── Separador ────────────────────────────────────────────────────────
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # ── Botón Solicitar Sugerencias IA — CU-13 ──────────────────────────
        self._btn_ai = ctk.CTkButton(
            bar,
            text="🤖  Solicitar Sugerencias IA",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1e1e3a",
            hover_color="#2a2a52",
            text_color="#a78bfa",
            border_color="#6d28d9",
            border_width=1,
            width=210,
            height=BTN_SEND_H,
            corner_radius=6,
            command=self._on_ask_ai,
        )
        self._btn_ai.pack(side="left", padx=(10, 4), pady=9)

        # ── Selector de modelo IA ──────────────────────────────────────────────
        self._ai_models = self._ai_engine.get_installed_models()
        self._model_var = ctk.StringVar()
        
        self._model_menu = ctk.CTkOptionMenu(
            bar,
            variable=self._model_var,
            values=self._ai_models if self._ai_models else ["No models found"],
            width=140,
            height=BTN_SEND_H,
            font=ctk.CTkFont(size=11),
            fg_color="#1e1e3a",
            button_color="#2a2a52",
            button_hover_color="#3b3b72",
        )
        self._model_menu.pack(side="left", padx=(4, 10), pady=9)
        
        if self._ai_models:
            self._model_var.set(self._ai_models[0])
        else:
            self._model_menu.configure(state="disabled")
            self._btn_ai.configure(state="disabled")

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
        self._btn_reset.configure(state="disabled")
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
        self._btn_send.configure(state="normal", text="▶  Enviar")
        self._btn_reset.configure(state="normal")

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

    # ── CU-13: Copiloto de Evasión de WAF ─────────────────────────────────────

    def _on_ask_ai(self) -> None:
        """
        CU-13: Inicia la consulta al copiloto de IA en un hilo daemon.

        Lee el contenido actual de los paneles Request y Response, y lanza
        un hilo background que llama a AIEngine.suggest_waf_bypass().
        Mientras el hilo está activo, el botón se deshabilita para evitar
        consultas simultáneas.
        """
        if self._asking_ai:
            return

        request_text  = self._request_box.get("1.0", "end-1c").strip()
        response_text = self._response_box.get("1.0", "end-1c").strip()

        if not request_text:
            self._status_lbl.configure(
                text="⚠  El panel Request está vacío. Envía primero una petición.",
                text_color=ACCENT_YELLOW,
            )
            return

        if not response_text:
            self._status_lbl.configure(
                text="⚠  No hay respuesta. Pulsa Send antes de consultar a la IA.",
                text_color=ACCENT_YELLOW,
            )
            return

        # Bloquear el botón y mostrar estado de carga
        self._asking_ai = True
        self._btn_ai.configure(
            state="disabled",
            text="⏳  Analizando…",
            text_color=ACCENT_YELLOW,
        )
        self._btn_reset.configure(state="disabled")
        self._model_menu.configure(state="disabled")
        self._status_lbl.configure(
            text="🤖  Consultando al copiloto de IA",
            text_color="#a78bfa",
        )

        model = self._model_var.get()

        threading.Thread(
            target=self._run_ai_in_background,
            args=(request_text, response_text, model),
            daemon=True,
            name="AIWafBypass",
        ).start()

    def _run_ai_in_background(
        self,
        request_text: str,
        response_text: str,
        model: str,
    ) -> None:
        """
        Ejecuta AIEngine.suggest_waf_bypass() fuera del hilo principal.

        Publica el resultado (éxito o error) de vuelta al hilo principal
        usando after(0, ...) para garantizar thread-safety con Tkinter.

        Args:
            request_text  (str): Texto del panel Request.
            response_text (str): Texto del panel Response.
        """
        try:
            result = self._ai_engine.suggest_waf_bypass(
                request_text=request_text,
                response_text=response_text,
                model_override=model,
            )
            self.after(0, lambda: self._on_ai_complete(result, request_text))
        except GeminiConfigError as exc:
            self.after(0, lambda e=exc: self._on_ai_error(
                "🔑 API Key no configurada",
                str(e),
            ))
        except GeminiConnectionError as exc:
            self.after(0, lambda e=exc: self._on_ai_error(
                "🔌 Error de conexión con Gemini",
                str(e),
            ))
        except GeminiEngineError as exc:
            self.after(0, lambda e=exc: self._on_ai_error(
                "❌ Error del motor de IA",
                str(e),
            ))
        except Exception as exc:  # pylint: disable=broad-except
            self.after(0, lambda e=exc: self._on_ai_error(
                "❌ Error inesperado",
                f"{type(e).__name__}: {e}",
            ))

    def _on_ai_complete(self, result: str, request_text: str) -> None:
        """
        Callback en el hilo principal: muestra el resultado en una ventana modal.

        Args:
            result        (str): Texto de sugerencias generado por la IA.
            request_text  (str): Primera línea de la petición (para el título).
        """
        # Restaurar el botón
        self._asking_ai = False
        self._btn_ai.configure(
            state="normal",
            text="🤖  Solicitar Sugerencias IA",
            text_color="#a78bfa",
        )
        self._btn_reset.configure(state="normal")
        self._model_menu.configure(state="normal")
        self._status_lbl.configure(
            text="✓  Análisis de IA completado.",
            text_color=ACCENT_GREEN,
        )

        # Extraer primera línea de la petición como resumen para el título
        summary = request_text.split("\n")[0].strip()

        # Mostrar ventana flotante o actualizar existente
        if self.ai_window and self.ai_window.winfo_exists():
            self.ai_window.update_results(result, summary)
            self.ai_window.focus_set()
        else:
            self.ai_window = AIResultWindow(
                parent=self,
                result_text=result,
                request_summary=summary,
                on_apply_callback=self.apply_ai_payload,
            )

    def _on_ai_error(self, title: str, detail: str) -> None:
        """
        Callback en el hilo principal: muestra el error de la IA en la status bar
        y en una ventana modal informativa.

        Args:
            title  (str): Título corto del error (para el botón y la barra).
            detail (str): Descripción técnica completa del error.
        """
        self._asking_ai = False
        self._btn_ai.configure(
            state="normal",
            text="🤖  Solicitar Sugerencias IA",
            text_color="#a78bfa",
        )
        self._btn_reset.configure(state="normal")
        self._model_menu.configure(state="normal")
        self._status_lbl.configure(
            text=f"✗  {title}",
            text_color=ACCENT_RED,
        )

        # Mostrar el detalle del error en la misma ventana modal reutilizando
        # AIResultWindow — el mensaje de error es suficientemente informativo.
        error_message = (
            f"⚠️  {title}\n\n"
            f"{detail}\n\n"
            "─────────────────────────────\n"
            "Acciones recomendadas:\n"
            "  1. Verifica que Ollama está corriendo:  ollama serve\n"
            "  2. Verifica que el modelo está instalado: ollama pull llama3\n"
            "  3. Comprueba que tienes al menos 8 GB de RAM libre."
        )
        
        if self.ai_window and self.ai_window.winfo_exists():
            self.ai_window.update_results(error_message, title)
            self.ai_window.focus_set()
        else:
            self.ai_window = AIResultWindow(
                parent=self,
                result_text=error_message,
                request_summary=title,
                on_apply_callback=self.apply_ai_payload,
            )

    def _on_reset(self) -> None:
        """
        Restaura el panel Request al contenido original con el que fue cargada
        la petición (el que llegó desde ProxyTab o fue escrito manualmente).

        Si no hay petición original guardada, limpia el panel.
        """
        if self._original_request:
            self._set_request_text(self._original_request)
            self._set_response_text("")
            self._status_lbl.configure(
                text="🔄  Petición restablecida al estado original.",
                text_color=TEXT_MUTED,
            )
        else:
            self._status_lbl.configure(
                text="⚠  No hay petición original guardada.",
                text_color=ACCENT_YELLOW,
            )

    def _apply_waf_suggestion(self, payload: str) -> None:
        """
        Inyecta heurísticamente el payload sugerido por la IA en la petición
        actual, detectando el contexto (verbo HTTP, cabeceras, body JSON) y
        recalculando Content-Length automáticamente cuando es necesario.

        Regla A — El payload empieza con un verbo HTTP:
            Reemplaza únicamente la primera línea (request line).

        Regla B — El payload son cabecera(s) clave: valor:
            Actualiza las cabeceras existentes o las añade tras Host:.
            Si se modifica el body implícitamente, recalcula Content-Length.

        Regla C — El payload es un JSON completo ({ … }):
            Sustituye todo el body y actualiza Content-Length en bytes.

        Fallback — Ninguna regla aplica:
            Copia el payload al portapapeles para inserción manual.
        """
        raw = self._request_box.get("1.0", "end-1c")
        if not raw:
            return

        # ── Normalizar saltos de línea a \n para manipulación uniforme ─────────
        raw     = raw.replace("\r\n", "\n")
        payload = payload.strip()

        # ── Separar cabeceras y cuerpo ─────────────────────────────────────────
        if "\n\n" in raw:
            headers_block, body = raw.split("\n\n", 1)
        else:
            headers_block, body = raw, ""

        header_lines = headers_block.split("\n")

        # ── Helpers ────────────────────────────────────────────────────────────
        def _update_header(lines: list[str], key: str, value: str) -> list[str]:
            """Actualiza una cabecera existente o la inserta tras Host:."""
            key_lo = key.lower()
            for i, line in enumerate(lines[1:], start=1):
                if ":" in line and line.split(":", 1)[0].strip().lower() == key_lo:
                    lines[i] = f"{key}: {value}"
                    return lines
            # No existía → insertar tras Host:
            insert_at = 1
            for i, line in enumerate(lines[1:], start=1):
                if line.lower().startswith("host:"):
                    insert_at = i + 1
                    break
            lines.insert(insert_at, f"{key}: {value}")
            return lines

        def _recalc_content_length(lines: list[str], new_body: str) -> list[str]:
            """Actualiza Content-Length al tamaño real del nuevo body en bytes."""
            body_bytes = new_body.encode("utf-8", errors="replace")
            return _update_header(lines, "Content-Length", str(len(body_bytes)))

        def _rebuild(lines: list[str], new_body: str | None = None) -> str:
            """Reconstruye la petición completa."""
            headers = "\n".join(lines)
            if new_body is None:
                return headers + ("\n\n" + body if body else "")
            return headers + "\n\n" + new_body

        def _commit(new_text: str, msg: str) -> None:
            """Escribe el texto resultante en el editor y actualiza la UI."""
            self._request_box.delete("1.0", "end")
            self._request_box.insert("1.0", new_text)
            apply_syntax_highlighting(self._request_box)
            self._status_lbl.configure(text=msg, text_color=ACCENT_GREEN)

        # ── Regla A: Verbo HTTP ────────────────────────────────────────────────
        _HTTP_VERBS = (
            "GET ", "POST ", "PUT ", "DELETE ",
            "PATCH ", "OPTIONS ", "HEAD ", "TRACE ",
        )
        if payload.upper().startswith(_HTTP_VERBS):
            header_lines[0] = payload
            _commit(_rebuild(header_lines), "✓  Verbo / Request-line reemplazado.")
            return

        # ── Regla B: Cabecera(s) clave: valor ─────────────────────────────────
        payload_lines = [ln.strip() for ln in payload.split("\n") if ln.strip()]
        is_headers = (
            len(payload_lines) > 0
            and all(
                ":" in ln and not ln.startswith("{")
                for ln in payload_lines
            )
        )

        if is_headers:
            for p_line in payload_lines:
                key, val = p_line.split(":", 1)
                header_lines = _update_header(header_lines, key.strip(), val.strip())

            _commit(_rebuild(header_lines), "✓  Cabecera(s) aplicada(s).")
            return

        # ── Regla C: Body JSON completo ────────────────────────────────────────
        stripped = payload.strip()
        is_json_body = stripped.startswith("{") and stripped.endswith("}")

        if is_json_body:
            header_lines = _recalc_content_length(header_lines, stripped)
            _commit(_rebuild(header_lines, stripped), "✓  Body JSON reemplazado y Content-Length actualizado.")
            return

        # ── Fallback: copiar al portapapeles ───────────────────────────────────
        self.clipboard_clear()
        self.clipboard_append(payload)
        self._status_lbl.configure(
            text="ℹ  Payload copiado al portapapeles. Insértalo manualmente.",
            text_color=ACCENT_BLUE,
        )

    # Alias de compatibilidad — AIResultWindow llama a este nombre
    apply_ai_payload = _apply_waf_suggestion
