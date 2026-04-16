"""
gui/proxy_tab.py
----------------
Pestaña 'Proxy' de Mini-Burp Suite.

Responsabilidades:
    - Barra de control: switch Intercept ON/OFF, Clear, Export CSV.
    - Tabla de historial de peticiones (ttk.Treeview con tema dark).
    - Visor/Editor: muestra la petición seleccionada o la interceptada.
    - Botones Forward / Drop (CU-04): visibles solo cuando hay intercepción activa.

Patrón de actualización: polling con window.after() cada POLL_MS ms,
que corre en el hilo principal (thread-safe con la Queue de InterceptController).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

import customtkinter as ctk

from proxy.server import ProxyServer
from proxy.handler import PendingRequest
from .colors import (
    BG_DARK, BG_SECONDARY, BG_ROW_ODD, BG_HOVER,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    TEXT_PRIMARY, TEXT_MUTED, BORDER,
)

# ── Constantes de comportamiento ───────────────────────────────────────────────
POLL_MS       = 400    # ms entre cada ciclo de refresco de la UI
PATH_MAX_CHARS = 55    # truncar paths largos en la tabla


class ProxyTab(ctk.CTkFrame):
    """
    Panel de la pestaña 'Proxy'.

    Muestra en tiempo real el historial de peticiones interceptadas y
    permite al usuario interactuar con peticiones pausadas (CU-04).

    Args:
        master      : Widget padre (tab del CTkTabview).
        proxy (ProxyServer): Instancia del proxy ya iniciado.
    """

    def __init__(self, master: tk.Widget, proxy: ProxyServer) -> None:
        super().__init__(master, fg_color="transparent")
        self.proxy    = proxy
        self._pending : PendingRequest | None = None  # petición interceptada activa
        self._seen_ids: set[int] = set()              # IDs ya pintados en la tabla

        self._build_control_bar()
        self._build_main_panel()
        self._poll()  # arrancar ciclo de refresco

    # ── Barra de control ──────────────────────────────────────────────────────

    def _build_control_bar(self) -> None:
        """Fila superior: botón Intercept, Clear, Export y contador."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        # Botón de intercepción (actúa como toggle)
        self._intercept_btn = ctk.CTkButton(
            bar,
            text="⬛  Intercept: OFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=BG_DARK,
            hover_color=BG_HOVER,
            border_color=ACCENT_GREEN,
            border_width=2,
            text_color=ACCENT_GREEN,
            width=190,
            height=36,
            corner_radius=6,
            command=self._toggle_intercept,
        )
        self._intercept_btn.pack(side="left", padx=12, pady=9)

        # Separador visual
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # Botón Clear
        ctk.CTkButton(
            bar, text="🗑  Limpiar", width=100, height=32,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            corner_radius=6, command=self._clear_history,
        ).pack(side="left", padx=10, pady=9)

        # Botón Export CSV
        ctk.CTkButton(
            bar, text="💾  Export CSV", width=130, height=32,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            corner_radius=6, command=self._export_csv,
        ).pack(side="left", padx=0, pady=9)

        # Contador de peticiones (derecha)
        self._count_lbl = ctk.CTkLabel(
            bar, text="0 peticiones",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right", padx=16)

    # ── Panel principal (tabla arriba · editor abajo) ─────────────────────────

    def _build_main_panel(self) -> None:
        """
        PanedWindow vertical para que el usuario redimensione la tabla y el editor.
        """
        paned = tk.PanedWindow(
            self, orient=tk.VERTICAL,
            bg=BG_DARK, sashwidth=6, sashrelief="flat", sashpad=2,
        )
        paned.pack(fill="both", expand=True)

        table_frame = tk.Frame(paned, bg=BG_DARK)
        paned.add(table_frame, minsize=160)
        self._build_history_table(table_frame)

        editor_frame = ctk.CTkFrame(paned, fg_color=BG_SECONDARY, corner_radius=8)
        paned.add(editor_frame, minsize=140)
        self._build_request_editor(editor_frame)

    def _build_history_table(self, parent: tk.Widget) -> None:
        """
        Tabla de historial con ttk.Treeview estilizado en modo dark.

        Columnas: #, METHOD, HOST, PATH, STATUS, ms
        """
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Burp.Treeview",
            background=BG_SECONDARY, foreground=TEXT_PRIMARY,
            fieldbackground=BG_SECONDARY, borderwidth=0,
            rowheight=26, font=("Consolas", 11),
        )
        style.configure(
            "Burp.Treeview.Heading",
            background=BG_DARK, foreground=TEXT_MUTED,
            relief="flat", font=("Consolas", 11, "bold"),
        )
        style.map(
            "Burp.Treeview",
            background=[("selected", ACCENT_BLUE)],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Burp.Treeview.Heading", relief=[("active", "flat")])

        columns = ("#", "METHOD", "HOST", "PATH", "STATUS", "ms")
        self._tree = ttk.Treeview(
            parent, columns=columns, show="headings",
            style="Burp.Treeview", selectmode="browse",
        )

        col_cfg: list[tuple[str, int, str, bool]] = [
            ("#",      48,  "center", False),
            ("METHOD", 72,  "center", False),
            ("HOST",   200, "w",      False),
            ("PATH",   260, "w",      True),   # stretch
            ("STATUS", 145, "center", False),
            ("ms",     60,  "center", False),
        ]
        for col, w, anchor, stretch in col_cfg:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor=anchor, stretch=stretch)

        self._tree.tag_configure("even",        background=BG_SECONDARY)
        self._tree.tag_configure("odd",         background=BG_ROW_ODD)
        self._tree.tag_configure("intercepted", background="#3d1a1a",
                                                foreground=ACCENT_RED)

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)

    def _build_request_editor(self, parent: ctk.CTkFrame) -> None:
        """
        Panel inferior: encabezado con botones Forward/Drop + CTkTextbox editor.
        """
        header = ctk.CTkFrame(parent, fg_color="transparent", height=34)
        header.pack(fill="x", padx=10, pady=(6, 2))
        header.pack_propagate(False)

        self._editor_lbl = ctk.CTkLabel(
            header, text="📋 Petición seleccionada",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED,
        )
        self._editor_lbl.pack(side="left")

        # Botones Forward / Drop — se muestran solo cuando hay intercepción
        self._btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        self._btn_frame.pack(side="right")

        self._btn_forward = ctk.CTkButton(
            self._btn_frame, text="▶  Forward", width=110, height=28,
            fg_color=ACCENT_GREEN, hover_color="#2ea843",
            text_color="#ffffff", font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6, command=self._on_forward,
        )
        self._btn_drop = ctk.CTkButton(
            self._btn_frame, text="✕  Drop", width=90, height=28,
            fg_color=ACCENT_RED, hover_color="#da3633",
            text_color="#ffffff", font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6, command=self._on_drop,
        )

        self._editor_box = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_DARK, text_color=TEXT_PRIMARY,
            border_color=BORDER, border_width=1,
            wrap="none", corner_radius=6,
        )
        self._editor_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ── Lógica: toggle, limpiar, exportar ─────────────────────────────────────

    def _toggle_intercept(self) -> None:
        """Activa o desactiva el modo intercept y actualiza el botón."""
        if self.proxy.intercept.intercept_enabled:
            self.proxy.intercept.disable()
            self._intercept_btn.configure(
                text="⬛  Intercept: OFF",
                border_color=ACCENT_GREEN, text_color=ACCENT_GREEN,
            )
        else:
            self.proxy.intercept.enable()
            self._intercept_btn.configure(
                text="🔴  Intercept: ON",
                border_color=ACCENT_RED, text_color=ACCENT_RED,
            )

    def _clear_history(self) -> None:
        """Vacía el historial y la tabla."""
        self.proxy.history.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._seen_ids.clear()
        self._set_editor_text("")
        self._count_lbl.configure(text="0 peticiones")
        self._hide_intercept_buttons()
        self._pending = None

    def _export_csv(self) -> None:
        """Exporta el historial a un archivo CSV seleccionado por el usuario."""
        if len(self.proxy.history) == 0:
            messagebox.showinfo("Export", "El historial está vacío.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"historial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if path:
            self.proxy.history.export_csv(path)
            messagebox.showinfo("Export", f"✅ Exportado a:\n{path}", parent=self)

    # ── Lógica: Forward / Drop (CU-04) ────────────────────────────────────────

    def _on_forward(self) -> None:
        """Reenvía la petición interceptada (posiblemente modificada en el editor)."""
        if self._pending:
            modified = self._editor_box.get("1.0", "end-1c").encode("utf-8", errors="replace")
            self._pending.forward(modified)
            self._pending = None
            self._hide_intercept_buttons()
            self._editor_lbl.configure(text="📋 Petición seleccionada")

    def _on_drop(self) -> None:
        """Descarta la petición interceptada (el navegador recibe 403)."""
        if self._pending:
            self._pending.drop()
            self._pending = None
            self._hide_intercept_buttons()
            self._editor_lbl.configure(text="📋 Petición seleccionada")

    def _show_intercept_buttons(self) -> None:
        self._btn_forward.pack(side="left", padx=(0, 6))
        self._btn_drop.pack(side="left")

    def _hide_intercept_buttons(self) -> None:
        self._btn_forward.pack_forget()
        self._btn_drop.pack_forget()

    # ── Selección manual de fila ───────────────────────────────────────────────

    def _on_row_select(self, _event: tk.Event | None = None) -> None:
        """Muestra el raw de la petición seleccionada en el editor."""
        if self._pending:
            return  # no sobreescribir una petición interceptada activa

        selected = self._tree.selection()
        if not selected:
            return

        values = self._tree.item(selected[0], "values")
        if not values:
            return

        req_id = int(values[0])
        record = self.proxy.history.get_by_id(req_id)
        if record and record.raw_request:
            self._set_editor_text(record.raw_request.decode("utf-8", errors="replace"))
            self._editor_lbl.configure(
                text=f"📋 #{req_id}  {record.method}  {record.host}{record.path}"
            )

    # ── Polling: actualizar tabla y revisar intercepción ──────────────────────

    def _poll(self) -> None:
        """
        Ciclo de refresco ejecutado cada POLL_MS ms en el hilo principal.
        Actualiza la tabla con nuevas peticiones y detecta intercepts pendientes.
        """
        self._refresh_table()
        self._check_intercept_queue()
        self.after(POLL_MS, self._poll)

    def _refresh_table(self) -> None:
        """Inserta en la tabla los registros del historial que aún no se han pintado."""
        for record in self.proxy.history.all():
            if record.id in self._seen_ids:
                continue
            self._seen_ids.add(record.id)
            tag = "even" if len(self._seen_ids) % 2 == 0 else "odd"
            path_display = record.path
            if len(path_display) > PATH_MAX_CHARS:
                path_display = path_display[:PATH_MAX_CHARS] + "…"
            status_display = (record.response_status or "—")[:32]
            self._tree.insert(
                "", "end", tags=(tag,),
                values=(
                    record.id, record.method, record.host,
                    path_display, status_display,
                    f"{record.duration_ms:.0f}",
                ),
            )

        children = self._tree.get_children()
        if children:
            self._tree.see(children[-1])   # auto-scroll al final

        total = len(self._seen_ids)
        noun  = "petición" if total == 1 else "peticiones"
        self._count_lbl.configure(text=f"{total} {noun}")

    def _check_intercept_queue(self) -> None:
        """
        Obtiene la siguiente petición interceptada (si la hay) y la muestra
        en el editor, habilitando los botones Forward y Drop.
        """
        if self._pending is not None:
            return  # ya hay una en proceso

        pending = self.proxy.intercept.next_pending()
        if pending is None:
            return

        self._pending = pending
        self._set_editor_text(pending.raw.decode("utf-8", errors="replace"))
        self._editor_lbl.configure(
            text=(
                f"🔴  INTERCEPTADO  #{pending.id}  "
                f"{pending.parsed.method}  "
                f"{pending.parsed.host}{pending.parsed.path}"
            )
        )
        self._show_intercept_buttons()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_editor_text(self, text: str) -> None:
        """Reemplaza el contenido del editor con el texto dado."""
        self._editor_box.delete("1.0", "end")
        if text:
            self._editor_box.insert("1.0", text)
