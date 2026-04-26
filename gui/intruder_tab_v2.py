"""
gui/intruder_tab_v2.py
----------------------
Módulo C: Intruder — Iteración 1 (esqueleto base).

Estructura:
    IntruderTab
        └── CTkTabview
                ├── "  Posiciones  "   (editor de plantilla + marcadores §)
                └── "  Payloads    "   (arsenal + resultados)

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk

from intruder import Intruder, IntruderResult
from .utils import apply_syntax_highlighting
from logic.ai_copilot import GeminiCopilot, AICopilotError
from .colors import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_RED,
    ACCENT_YELLOW,
    BG_DARK,
    BG_HOVER,
    BG_SECONDARY,
    BORDER,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class IntruderTab(ctk.CTkFrame):
    """
    Pestaña principal del módulo Intruder.

    Hereda de ctk.CTkFrame y organiza su contenido en dos
    sub-pestañas: Posiciones y Payloads.

    Args:
        master: Widget padre (tab del CTkTabview principal de App).
    """

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, fg_color="transparent")
        self._payloads        : list[str]                   = []
        self._intruder        : Intruder                    = Intruder()
        self._result_queue    : queue.Queue[IntruderResult] = queue.Queue()
        self._original_request: str                         = ""
        self._build_attack_bar()
        self._build_main_pane()

    # ── Barra de ataque global ─────────────────────────────────────────────

    def _build_attack_bar(self) -> None:
        """Barra superior fija: Atacar, Detener e input de Hilos."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        self._btn_attack = ctk.CTkButton(
            bar, text="🚀  Atacar",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT_RED, hover_color="#da3633",
            border_color="#ff6b63", border_width=1,
            text_color="#ffffff", width=110, height=32, corner_radius=6,
            command=self._start_attack,
        )
        self._btn_attack.pack(side="left", padx=12, pady=9)

        self._btn_stop = ctk.CTkButton(
            bar, text="⏹  Detener",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_DARK, hover_color=BG_HOVER,
            border_color=BORDER, border_width=1,
            text_color=TEXT_MUTED, width=100, height=32, corner_radius=6,
            state="disabled", command=self._stop_attack,
        )
        self._btn_stop.pack(side="left", padx=(0, 8), pady=9)

        self._btn_reset = ctk.CTkButton(
            bar, text="🔄  Restablecer",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=BG_DARK, hover_color=BG_HOVER,
            border_color=BORDER, border_width=1,
            text_color=TEXT_MUTED, width=118, height=32, corner_radius=6,
            command=self._on_reset,
        )
        self._btn_reset.pack(side="left", padx=(0, 8), pady=9)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=10)

        ctk.CTkLabel(
            bar, text="Hilos:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(10, 4))

        self._threads_var = tk.StringVar(value="5")
        ctk.CTkEntry(
            bar, textvariable=self._threads_var,
            width=44, height=28, justify="center",
            fg_color=BG_DARK, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).pack(side="left", pady=9)

        self._attack_status_lbl = ctk.CTkLabel(
            bar, text="Listo. Define la plantilla y carga payloads.",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._attack_status_lbl.pack(side="right", padx=16)

    # ── Divisor móvil (PanedWindow) ──────────────────────────────────────

    def _build_main_pane(self) -> None:
        """
        PanedWindow vertical que separa el editor/payloads (arriba)
        de la tabla de resultados (abajo). El usuario puede arrastrar
        el divisor para redimensionar ambas secciones.
        """
        pane = tk.PanedWindow(
            self,
            orient=tk.VERTICAL,
            bg=BORDER,
            sashwidth=5,
            sashpad=0,
            sashrelief="flat",
            handlesize=0,
        )
        pane.pack(fill="both", expand=True)

        # Panel superior: sub-pestañas Posiciones / Payloads
        top = tk.Frame(pane, bg=BG_DARK)
        pane.add(top, stretch="always", minsize=280)
        self._build_tab_view(top)

        # Panel inferior: tabla de resultados
        bottom = tk.Frame(pane, bg=BG_SECONDARY)
        pane.add(bottom, stretch="never", minsize=120)
        self._build_results_table(bottom)

    # ── Tabla de resultados ────────────────────────────────────────────────

    def _build_results_table(self, parent: tk.Widget) -> None:
        """Panel inferior con tabla de resultados del ataque."""
        container = tk.Frame(parent, bg=BG_SECONDARY)
        container.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        hdr = ctk.CTkFrame(container, fg_color="transparent", height=32)
        hdr.pack(fill="x", padx=10, pady=(6, 2))
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="📊  Resultados del ataque",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED,
        ).pack(side="left")

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Intruder2.Treeview",
            background=BG_SECONDARY, foreground=TEXT_PRIMARY,
            fieldbackground=BG_SECONDARY, borderwidth=0,
            rowheight=24, font=("Consolas", 11),
        )
        style.configure(
            "Intruder2.Treeview.Heading",
            background=BG_DARK, foreground=TEXT_MUTED,
            relief="flat", font=("Consolas", 11, "bold"),
        )
        style.map("Intruder2.Treeview",
                  background=[("selected", ACCENT_BLUE)],
                  foreground=[("selected", "#ffffff")])
        style.map("Intruder2.Treeview.Heading",
                  relief=[("active", "flat")])

        cols = ("#", "Payload", "Status", "Length", "ms")
        self._results_tree = ttk.Treeview(
            container, columns=cols, show="headings",
            style="Intruder2.Treeview", selectmode="browse", height=6,
        )
        for col, w, anchor in [
            ("#",       48,  "center"),
            ("Payload", 320, "w"),
            ("Status",  80,  "center"),
            ("Length",  80,  "center"),
            ("ms",      60,  "center"),
        ]:
            self._results_tree.heading(col, text=col)
            self._results_tree.column(col, width=w, anchor=anchor, stretch=(col == "Payload"))

        vsb = ttk.Scrollbar(container, orient="vertical", command=self._results_tree.yview)
        self._results_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 4))
        self._results_tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 4))

        # ── Tags de color por rango de status ───────────────────────────────
        # Configurados UNA sola vez aquí para no llamarlos en cada fila.
        # background sutil para dark mode; foreground de alto contraste.
        self._results_tree.tag_configure(
            "status_2xx",
            background="#0d2818",      # verde muy oscuro
            foreground=ACCENT_GREEN,   # #3fb950
        )
        self._results_tree.tag_configure(
            "status_3xx",
            background="#0d1f35",      # azul marino oscuro
            foreground="#58a6ff",      # azul clásico GitHub
        )
        self._results_tree.tag_configure(
            "status_4xx",
            background="#2b1d0e",      # naranja muy oscuro
            foreground=ACCENT_YELLOW,  # #e3b341
        )
        self._results_tree.tag_configure(
            "status_5xx",
            background="#2d0f0f",      # rojo muy oscuro
            foreground=ACCENT_RED,     # #f85149
        )
        self._results_tree.tag_configure(
            "status_err",
            background=BG_SECONDARY,
            foreground=TEXT_MUTED,     # gris neutro para errores de red
        )

    # ── Construcción del CTkTabview principal ──────────────────────────────────

    def _build_tab_view(self, parent: tk.Widget) -> None:
        """Crea el CTkTabview con las dos sub-pestañas dentro del panel superior."""
        self._tab_view = ctk.CTkTabview(
            parent,
            fg_color=BG_SECONDARY,
            segmented_button_fg_color=BG_DARK,
            segmented_button_selected_color=ACCENT_BLUE,
            segmented_button_selected_hover_color="#1a5fb4",
            segmented_button_unselected_color=BG_SECONDARY,
            segmented_button_unselected_hover_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            corner_radius=8,
        )
        self._tab_view.pack(fill="both", expand=True)

        # ── Sub-pestaña 1: Posiciones ──────────────────────────────────────────
        self._tab_view.add("  Posiciones  ")
        self._build_positions_tab(
            self._tab_view.tab("  Posiciones  ")
        )

        # ── Sub-pestaña 2: Payloads ────────────────────────────────────────────
        self._tab_view.add("  Payloads    ")
        self._build_payloads_tab(
            self._tab_view.tab("  Payloads    ")
        )

    # ── Contenido de sub-pestañas (placeholders) ───────────────────────────────

    def _build_positions_tab(self, parent: tk.Widget) -> None:
        """Pestaña Posiciones: tipo de ataque, editor de plantilla y botones §."""

        # ── Barra superior: Tipo de Ataque ─────────────────────────────────────
        top_bar = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, height=44, corner_radius=8)
        top_bar.pack(fill="x", pady=(0, 8))
        top_bar.pack_propagate(False)

        ctk.CTkLabel(
            top_bar,
            text="Tipo de Ataque:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 6), pady=8)

        self._attack_type_var = ctk.StringVar(value="Sniper")
        ctk.CTkComboBox(
            top_bar,
            values=["Sniper", "Battering ram", "Pitchfork", "Cluster bomb"],
            variable=self._attack_type_var,
            width=185,
            height=28,
            fg_color=BG_DARK,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="readonly",
        ).pack(side="left", pady=8)

        # ── Área principal: editor + panel lateral ────────────────────────────
        main = tk.Frame(parent, bg=BG_DARK)
        main.pack(fill="both", expand=True)

        # Editor de plantilla HTTP
        editor_frame = ctk.CTkFrame(main, fg_color=BG_SECONDARY, corner_radius=8)
        editor_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkLabel(
            editor_frame,
            text="📝  Plantilla (petición con §marcadores§)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=8, pady=(8, 2))

        self._template_box = ctk.CTkTextbox(
            editor_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            border_color=BORDER,
            border_width=1,
            wrap="none",
            corner_radius=6,
        )
        self._template_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._template_box.insert(
            "1.0",
            "GET /search?q=§test§ HTTP/1.1\n"
            "Host: example.com\n"
            "User-Agent: Mozilla/5.0\n"
            "Connection: close\n",
        )
        apply_syntax_highlighting(self._template_box)

        # Panel lateral de botones §
        btn_panel = ctk.CTkFrame(main, fg_color=BG_SECONDARY, corner_radius=8, width=118)
        btn_panel.pack(side="right", fill="y")
        btn_panel.pack_propagate(False)

        ctk.CTkLabel(
            btn_panel,
            text="Marcadores",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(pady=(14, 8))

        _btn_cfg = dict(
            width=96, height=32, corner_radius=6,
            fg_color=BG_DARK, hover_color=BG_HOVER,
            border_width=1,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        for label, cmd, color in [
            ("Añadir §",  self._add_marker,      ACCENT_YELLOW),
            ("Limpiar §", self._clear_markers,    ACCENT_RED),
            ("Auto §",    self._auto_markers,     ACCENT_GREEN),
            ("Refrescar", self._refresh_template, ACCENT_BLUE),
        ]:
            ctk.CTkButton(
                btn_panel, text=label, command=cmd,
                text_color=color, border_color=color, **_btn_cfg,
            ).pack(pady=(0, 6))

    def _build_payloads_tab(self, parent: tk.Widget) -> None:
        """Pestaña Payloads: selector de set, botones de gestión y previsualización."""

        # ── Barra superior: Set de Payload ─────────────────────────────────
        top_bar = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, height=44, corner_radius=8)
        top_bar.pack(fill="x", pady=(0, 8))
        top_bar.pack_propagate(False)

        ctk.CTkLabel(
            top_bar,
            text="Set de Payload:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 6), pady=8)

        self._payload_set_var = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            top_bar,
            values=["1", "2", "3", "4"],
            variable=self._payload_set_var,
            width=80,
            height=28,
            fg_color=BG_DARK,
            button_color=BG_HOVER,
            button_hover_color="#373e47",
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).pack(side="left", pady=8)

        self._payload_count_lbl = ctk.CTkLabel(
            top_bar,
            text="Payloads cargados: 0",
            font=ctk.CTkFont(size=11),
            text_color=ACCENT_YELLOW,
        )
        self._payload_count_lbl.pack(side="left", padx=(20, 0))

        # ── Sección: Opciones de Payload (Lista simple) ─────────────────
        section = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=8)
        section.pack(fill="both", expand=True)

        ctk.CTkLabel(
            section,
            text="Opciones de Payload  [Lista simple]",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ACCENT_BLUE,
        ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            section,
            text="Lista de cadenas de texto que se usarán como payloads.",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # Fila: entrada manual + botón Añadir
        add_row = ctk.CTkFrame(section, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=(0, 6))

        self._manual_entry_var = tk.StringVar()
        ctk.CTkEntry(
            add_row,
            textvariable=self._manual_entry_var,
            height=30,
            placeholder_text="Escribe un payload y pulsa Añadir…",
            fg_color=BG_DARK,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            add_row,
            text="➕  Añadir",
            command=self._add_payload_manual,
            width=90, height=30, corner_radius=5,
            fg_color=ACCENT_BLUE, hover_color="#1a5fb4",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        # Fila de botones de archivo
        file_row = ctk.CTkFrame(section, fg_color="transparent")
        file_row.pack(fill="x", padx=12, pady=(0, 8))

        _sec_btn = dict(
            height=30, corner_radius=5,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        )
        ctk.CTkButton(
            file_row, text="📁  Cargar...",
            command=self._load_payloads,
            width=110, **_sec_btn,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            file_row, text="🗑  Limpiar",
            command=self._clear_payloads,
            width=90, **_sec_btn,
        ).pack(side="left")

        # Botón IA — generacion automática de payloads con Gemini
        self._btn_ai = ctk.CTkButton(
            section,
            text="✨  Generar con IA",
            command=self._generate_ai_payloads,
            height=34, corner_radius=6,
            fg_color="#3b1f6b", hover_color="#4e2a90",
            border_color="#a78bfa", border_width=1,
            text_color="#a78bfa",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._btn_ai.pack(fill="x", padx=12, pady=(2, 10))

        # Etiqueta + Textbox de previsualización (solo lectura)
        ctk.CTkLabel(
            section,
            text="Previsualización de payloads cargados:",
            font=ctk.CTkFont(size=10),
            text_color=BORDER,
        ).pack(anchor="w", padx=12, pady=(0, 2))

        self._payload_preview = ctk.CTkTextbox(
            section,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=BG_DARK,
            text_color=TEXT_MUTED,
            border_color=BORDER,
            border_width=1,
            wrap="none",
            corner_radius=6,
            state="disabled",
        )
        self._payload_preview.pack(
            fill="both", expand=True, padx=12, pady=(0, 12)
        )

    # ── API pública ────────────────────────────────────────────────────────────

    def load_request(self, raw: str) -> None:
        """
        Carga una petición HTTP en el editor de plantilla.
        Guarda una copia en _original_request para poder restablecer.

        Args:
            raw: Texto completo de la petición HTTP.
        """
        self._original_request = raw
        if hasattr(self, "_template_box"):
            self._template_box.delete("1.0", "end")
            self._template_box.insert("1.0", raw)
            apply_syntax_highlighting(self._template_box)

    def _on_reset(self) -> None:
        """Restaura el editor de plantilla a la petición original cargada."""
        if self._original_request:
            if hasattr(self, "_template_box"):
                self._template_box.delete("1.0", "end")
                self._template_box.insert("1.0", self._original_request)
                apply_syntax_highlighting(self._template_box)
            self._attack_status_lbl.configure(
                text="🔄  Plantilla restablecida al estado original.",
                text_color=TEXT_MUTED,
            )
        else:
            self._attack_status_lbl.configure(
                text="⚠  No hay petición original guardada. Envía una desde el Proxy.",
                text_color=ACCENT_YELLOW,
            )

    # ── Callbacks: marcadores § ────────────────────────────────────────────────

    def _add_marker(self) -> None:
        """Envuelve el texto seleccionado (o el cursor) con marcadores §§."""
        try:
            start = self._template_box.index("sel.first")
            end   = self._template_box.index("sel.last")
            text  = self._template_box.get(start, end)
            self._template_box.delete(start, end)
            self._template_box.insert(start, f"§{text}§")
        except tk.TclError:
            self._template_box.insert("insert", "§§")

    def _clear_markers(self) -> None:
        """Elimina todos los marcadores § del template."""
        content = self._template_box.get("1.0", "end-1c")
        self._template_box.delete("1.0", "end")
        self._template_box.insert("1.0", content.replace("§", ""))

    def _auto_markers(self) -> None:
        """Placeholder: detectará automáticamente valores de parámetros (iteración futura)."""

    def _refresh_template(self) -> None:
        """Placeholder: actualizará el resaltado de marcadores (iteración futura)."""

    # ── Copiloto IA (CU-14) ────────────────────────────────────────────────────

    def _generate_ai_payloads(self) -> None:
        """
        Lanza un hilo daemon que llama a GeminiCopilot y añade los payloads
        generados a self._payloads de forma 100 % thread-safe con .after().
        """
        template = self._template_box.get("1.0", "end-1c").strip()
        if not template:
            self._attack_status_lbl.configure(
                text="⚠  Escribe una plantilla en Posiciones primero.",
                text_color=ACCENT_YELLOW,
            )
            return

        # Bloquear el botón mientras Gemini trabaja
        self._btn_ai.configure(
            state="disabled",
            text="⏳  Consultando a Gemini...",
            text_color=TEXT_MUTED,
        )

        def _worker() -> None:
            """Hilo daemon: llama a Gemini y despacha el resultado al hilo principal."""
            try:
                copilot  = GeminiCopilot()
                payloads = copilot.generate_intruder_payloads(template)
                self.after(0, lambda p=payloads: _on_success(p))
            except AICopilotError as exc:
                self.after(0, lambda e=exc: _on_error(str(e)))
            except Exception as exc:        # pylint: disable=broad-except
                self.after(0, lambda e=exc: _on_error(f"Error inesperado: {e}"))

        def _on_success(payloads: list[str]) -> None:
            """Recibe la lista en el hilo principal y actualiza la UI."""
            if payloads:
                self._payloads.extend(payloads)
                self._refresh_payload_preview()
                self._attack_status_lbl.configure(
                    text=f"✨  Gemini generó {len(payloads)} payloads.",
                    text_color=ACCENT_GREEN,
                )
            else:
                self._attack_status_lbl.configure(
                    text="⚠  Gemini no devolvió payloads válidos. Inténtalo de nuevo.",
                    text_color=ACCENT_YELLOW,
                )
            _restore_button()

        def _on_error(msg: str) -> None:
            self._attack_status_lbl.configure(
                text=f"❌  {msg[:90]}",
                text_color=ACCENT_RED,
            )
            _restore_button()

        def _restore_button() -> None:
            self._btn_ai.configure(
                state="normal",
                text="✨  Generar con IA",
                text_color="#a78bfa",
            )

        threading.Thread(target=_worker, daemon=True, name="GeminiCopilot").start()

    # ── Callbacks: payloads ───────────────────────────────────────────────────

    def _load_payloads(self) -> None:
        """Abre un .txt y carga cada línea como payload en el preview."""
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar diccionario de payloads",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
        self._payloads.extend(lines)
        self._refresh_payload_preview()

    def _add_payload_manual(self) -> None:
        """Añade el texto del input a la lista y limpia el campo."""
        text = self._manual_entry_var.get().strip()
        if not text:
            return
        self._payloads.append(text)
        self._manual_entry_var.set("")
        self._refresh_payload_preview()

    def _clear_payloads(self) -> None:
        """Vacía la lista de payloads y el preview."""
        self._payloads.clear()
        self._refresh_payload_preview()

    def _refresh_payload_preview(self) -> None:
        """Actualiza el CTkTextbox de preview y el contador."""
        self._payload_preview.configure(state="normal")
        self._payload_preview.delete("1.0", "end")
        self._payload_preview.insert("1.0", "\n".join(self._payloads))
        self._payload_preview.configure(state="disabled")
        self._payload_count_lbl.configure(
            text=f"Payloads cargados: {len(self._payloads)}"
        )

    # ── Callbacks: ataque ─────────────────────────────────────────────────

    def _start_attack(self) -> None:
        """Valida los datos, resetea la tabla e inicia el hilo daemon de ataque."""
        template = self._template_box.get("1.0", "end-1c").strip()
        if not self._intruder.validate_template(template):
            self._attack_status_lbl.configure(
                text="⚠  El template no tiene marcadores §§. Añádelos en la pestaña Posiciones.",
                text_color="#f2cc60",
            )
            return
        if not self._payloads:
            self._attack_status_lbl.configure(
                text="⚠  No hay payloads cargados. Carga un .txt o añade payloads manualmente.",
                text_color="#f2cc60",
            )
            return

        try:
            n_threads = int(self._threads_var.get())
        except ValueError:
            n_threads = 5

        # Preparar el motor y la cola
        self._intruder.set_template(template)
        self._result_queue = queue.Queue()
        self._results_tree.delete(*self._results_tree.get_children())

        # Actualizar UI
        self._btn_attack.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._attack_status_lbl.configure(
            text=f"⏳  Atacando con {len(self._payloads)} payloads y {n_threads} hilos…",
            text_color="#f2cc60",
        )

        # Hilo daemon: llama a intruder.run() (bloqueante) y al terminar avisa
        threading.Thread(
            target=self._attack_worker,
            args=(self._payloads.copy(), n_threads),
            daemon=True,
            name="IntruderUI-Orchestrator",
        ).start()

        # Arrancar el poller de resultados en el hilo principal
        self.after(100, self._poll_results)

    def _attack_worker(self, payloads: list[str], n_threads: int) -> None:
        """Hilo daemon: ejecuta Intruder.run() y encola cada resultado."""
        def _enqueue(result: IntruderResult) -> None:
            self._result_queue.put(result)

        self._intruder.run(
            payloads=payloads, on_result=_enqueue, threads=n_threads,
        )
        # Centinela: indica al poller que el ataque terminó
        self._result_queue.put(None)

    def _poll_results(self) -> None:
        """
        Corre en el hilo principal cada 100 ms.
        Drena la queue y añade filas a _results_tree de forma thread-safe.
        """
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item is None:               # centinela: ataque finalizado
                    self._on_attack_done()
                    return
                self._insert_result_row(item)
        except queue.Empty:
            pass
        self.after(100, self._poll_results)    # seguir sondeando

    def _insert_result_row(self, r: IntruderResult) -> None:
        """Inserta una fila con el tag de color correspondiente al rango de status."""
        if r.status_code:
            status_text = str(r.status_code)
            code = r.status_code
            if 200 <= code < 300:
                tag = "status_2xx"
            elif 300 <= code < 400:
                tag = "status_3xx"
            elif 400 <= code < 500:
                tag = "status_4xx"
            elif 500 <= code < 600:
                tag = "status_5xx"
            else:
                tag = "status_err"
        else:
            status_text = f"ERR: {(r.error or '?')[:18]}"
            tag = "status_err"

        row_id = self._results_tree.insert(
            "", "end",
            values=(
                r.index,
                r.payload[:80],
                status_text,
                r.length,
                f"{r.duration_ms:.0f}",
            ),
            tags=(tag,),
        )
        # Auto-scroll al último resultado si el usuario está al fondo
        self._results_tree.see(row_id)

    def _on_attack_done(self) -> None:
        """Restaura la UI cuando el ataque finaliza o se detiene."""
        total = len(self._results_tree.get_children())
        self._btn_attack.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._attack_status_lbl.configure(
            text=f"✓  Ataque completado — {total} resultado(s).",
            text_color=ACCENT_GREEN,
        )

    def _stop_attack(self) -> None:
        """Señala al motor Intruder que debe abortar el ataque."""
        self._intruder.stop()
        self._btn_stop.configure(state="disabled")
        self._attack_status_lbl.configure(
            text="⏹  Deteniendo… esperando hilos activos.",
            text_color=ACCENT_YELLOW,
        )
