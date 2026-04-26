"""
gui/intruder_tab.py
-------------------
Pestaña 'Intruder' de Mini-Burp Suite (CU-08, CU-09, CU-10).

Responsabilidades:
    - Editor de template con marcadores §payload§ (CU-08).
    - Carga de diccionarios de payloads desde archivos .txt (CU-09).
    - Botón Attack que lanza el motor Intruder en un hilo daemon (CU-10).
    - Tabla de resultados con coloreado por código HTTP.
    - Botón Stop para cancelar el ataque en curso.
    - Exportación de resultados a CSV.

Patrón de threading:
    El ataque corre en un Thread daemon. Cada IntruderResult se publica
    al hilo principal usando widget.after(0, callback), siguiendo el mismo
    patrón de repeater_tab.py.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import csv
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from intruder import Intruder, IntruderResult
from .colors import (
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_YELLOW,
    BG_DARK, BG_HOVER, BG_ROW_ODD, BG_SECONDARY,
    BORDER, TEXT_MUTED, TEXT_PRIMARY,
)

# ── Constantes de layout ───────────────────────────────────────────────────────
EDITOR_FONT   = ("Consolas", 12)
LABEL_FONT_SZ = 12

# Directorio de payloads incluidos en el proyecto
_PAYLOADS_DIR = Path(__file__).parent.parent / "payloads"


class IntruderTab(ctk.CTkFrame):
    """
    Panel de la pestaña 'Intruder'.

    Expone el método público `load_request(raw: str)` para que en el futuro
    la pestaña Proxy pueda enviar una petición directamente aquí.

    Args:
        master: Widget padre (tab del CTkTabview).
    """

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, fg_color="transparent")
        self._intruder   = Intruder()
        self._payloads   : list[str] = []
        self._results    : list[IntruderResult] = []
        self._attacking  : bool = False

        self._build_toolbar()
        self._build_body()

    # ── API pública ────────────────────────────────────────────────────────────

    def load_request(self, raw: str) -> None:
        """
        Carga una petición en el editor de template (integración futura con ProxyTab).

        Args:
            raw (str): Texto completo de la petición HTTP.
        """
        self._set_template_text(raw)
        self._status_lbl.configure(
            text="Petición cargada. Añade §marcadores§ y carga payloads.",
            text_color=TEXT_MUTED,
        )

    # ── Construcción de la UI ──────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        """Barra superior: Attack, Stop, hilos, timeout y estado."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        # Botón Attack
        self._btn_attack = ctk.CTkButton(
            bar,
            text="💥  Atacar",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT_RED,
            hover_color="#da3633",
            text_color="#ffffff",
            width=120, height=36, corner_radius=6,
            command=self._on_attack,
        )
        self._btn_attack.pack(side="left", padx=12, pady=9)

        # Botón Stop
        self._btn_stop = ctk.CTkButton(
            bar,
            text="⏹  Detener",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            width=100, height=36, corner_radius=6,
            state="disabled",
            command=self._on_stop,
        )
        self._btn_stop.pack(side="left", padx=(0, 8), pady=9)

        # Separador
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # Threads
        ctk.CTkLabel(
            bar, text="Hilos:",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 4))

        self._threads_var = tk.StringVar(value="5")
        ctk.CTkEntry(
            bar, textvariable=self._threads_var,
            width=44, height=28,
            fg_color=BG_DARK, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="center",
        ).pack(side="left", pady=9)

        # Timeout
        ctk.CTkLabel(
            bar, text="Tiempo límite (s):",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        ).pack(side="left", padx=(10, 4))

        self._timeout_var = tk.StringVar(value="10")
        ctk.CTkEntry(
            bar, textvariable=self._timeout_var,
            width=44, height=28,
            fg_color=BG_DARK, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="center",
        ).pack(side="left", pady=9)

        # Label estado (derecha)
        self._status_lbl = ctk.CTkLabel(
            bar, text="Listo. Carga payloads y define el template.",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._status_lbl.pack(side="right", padx=16)

    def _build_body(self) -> None:
        """Divide la pestaña en panel superior (template + payloads) e inferior (tabla)."""
        paned = tk.PanedWindow(
            self, orient=tk.VERTICAL,
            bg=BG_DARK, sashwidth=6, sashrelief="flat",
        )
        paned.pack(fill="both", expand=True)

        top = ctk.CTkFrame(paned, fg_color="transparent")
        paned.add(top, minsize=200)
        self._build_top_section(top)

        bottom = ctk.CTkFrame(paned, fg_color=BG_SECONDARY, corner_radius=8)
        paned.add(bottom, minsize=180)
        self._build_results_table(bottom)

    def _build_top_section(self, parent: ctk.CTkFrame) -> None:
        """Panel izquierdo (template) y derecho (payloads) lado a lado."""
        paned = tk.PanedWindow(
            parent, orient=tk.HORIZONTAL,
            bg=BG_DARK, sashwidth=6, sashrelief="flat",
        )
        paned.pack(fill="both", expand=True)

        left = ctk.CTkFrame(paned, fg_color=BG_SECONDARY, corner_radius=8)
        paned.add(left, minsize=400)
        self._build_template_panel(left)

        right = ctk.CTkFrame(paned, fg_color=BG_SECONDARY, corner_radius=8)
        paned.add(right, minsize=220)
        self._build_payload_panel(right)

    def _build_template_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel editor del template HTTP con marcadores §."""
        # Encabezado
        hdr = ctk.CTkFrame(parent, fg_color="transparent", height=32)
        hdr.pack(fill="x", padx=8, pady=(8, 2))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="📝  Plantilla (petición con §marcadores§)",
            font=ctk.CTkFont(size=LABEL_FONT_SZ, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        # Botón "Añadir §§" — envuelve la selección con marcadores
        ctk.CTkButton(
            hdr, text="Añadir §§", width=90, height=24,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=ACCENT_YELLOW,
            font=ctk.CTkFont(size=11), corner_radius=4,
            command=self._wrap_selection,
        ).pack(side="right")

        # Editor
        self._template_box = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family=EDITOR_FONT[0], size=EDITOR_FONT[1]),
            fg_color=BG_DARK, text_color=TEXT_PRIMARY,
            border_color=BORDER, border_width=1,
            wrap="none", corner_radius=6,
        )
        self._template_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Template de ejemplo
        example = (
            "GET /search?q=§test§ HTTP/1.1\n"
            "Host: example.com\n"
            "User-Agent: Mozilla/5.0\n"
            "Connection: close\n"
        )
        self._template_box.insert("1.0", example)

    def _build_payload_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel derecho para cargar y visualizar payloads."""
        # Encabezado
        hdr = ctk.CTkFrame(parent, fg_color="transparent", height=32)
        hdr.pack(fill="x", padx=8, pady=(8, 2))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🎯  Payloads",
            font=ctk.CTkFont(size=LABEL_FONT_SZ, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self._payload_count_lbl = ctk.CTkLabel(
            hdr, text="0 cargados",
            font=ctk.CTkFont(size=11), text_color=ACCENT_YELLOW,
        )
        self._payload_count_lbl.pack(side="right")

        # Botones de payloads integrados
        btn_cfg = ctk.CTkFont(size=11, weight="bold")
        btn_kw  = dict(width=190, height=30, corner_radius=5)

        ctk.CTkButton(
            parent, text="🗄  Cargar SQLi", font=btn_cfg,
            fg_color="#2d1b1b", hover_color="#3d2020",
            border_color=ACCENT_RED, border_width=1,
            text_color=ACCENT_RED, **btn_kw,
            command=lambda: self._load_builtin("sqli.txt"),
        ).pack(padx=8, pady=(4, 2))

        ctk.CTkButton(
            parent, text="🌐  Cargar XSS", font=btn_cfg,
            fg_color="#1b2a1b", hover_color="#203520",
            border_color=ACCENT_GREEN, border_width=1,
            text_color=ACCENT_GREEN, **btn_kw,
            command=lambda: self._load_builtin("xss.txt"),
        ).pack(padx=8, pady=2)

        ctk.CTkButton(
            parent, text="📂  Cargar Traversal", font=btn_cfg,
            fg_color="#1b1b2d", hover_color="#20203d",
            border_color=ACCENT_BLUE, border_width=1,
            text_color=ACCENT_BLUE, **btn_kw,
            command=lambda: self._load_builtin("traversal.txt"),
        ).pack(padx=8, pady=2)

        # Separador
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=8, pady=6)

        ctk.CTkButton(
            parent, text="📁  Archivo personalizado…", font=btn_cfg,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, **btn_kw,
            command=self._load_custom_file,
        ).pack(padx=8, pady=2)

        # Vista previa de payloads
        ctk.CTkLabel(
            parent, text="Vista previa:",
            font=ctk.CTkFont(size=10), text_color=BORDER,
        ).pack(padx=8, pady=(8, 2), anchor="w")

        self._payload_preview = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=BG_DARK, text_color=TEXT_MUTED,
            border_color=BORDER, border_width=1,
            wrap="none", corner_radius=6,
            state="disabled",
        )
        self._payload_preview.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_results_table(self, parent: ctk.CTkFrame) -> None:
        """Tabla de resultados con ttk.Treeview estilizado en modo dark."""
        # Encabezado de la tabla
        hdr = ctk.CTkFrame(parent, fg_color="transparent", height=36)
        hdr.pack(fill="x", padx=10, pady=(6, 2))
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="📊  Resultados del ataque",
            font=ctk.CTkFont(size=LABEL_FONT_SZ, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="🗑  Limpiar", width=90, height=28,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11),
            corner_radius=5, command=self._clear_results,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            hdr, text="💾  Exportar CSV", width=110, height=28,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11),
            corner_radius=5, command=self._export_csv,
        ).pack(side="right", padx=4)

        # Estilos Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Intruder.Treeview",
            background=BG_SECONDARY, foreground=TEXT_PRIMARY,
            fieldbackground=BG_SECONDARY, borderwidth=0,
            rowheight=24, font=("Consolas", 11),
        )
        style.configure(
            "Intruder.Treeview.Heading",
            background=BG_DARK, foreground=TEXT_MUTED,
            relief="flat", font=("Consolas", 11, "bold"),
        )
        style.map(
            "Intruder.Treeview",
            background=[("selected", ACCENT_BLUE)],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Intruder.Treeview.Heading", relief=[("active", "flat")])

        columns = ("#", "Payload", "Status", "Length", "ms")
        self._tree = ttk.Treeview(
            parent, columns=columns, show="headings",
            style="Intruder.Treeview", selectmode="browse",
        )

        col_cfg = [
            ("#",       50,  "center", False),
            ("Payload", 340, "w",      True),
            ("Status",  80,  "center", False),
            ("Length",  90,  "center", False),
            ("ms",      70,  "center", False),
        ]
        for col, w, anchor, stretch in col_cfg:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor=anchor, stretch=stretch)

        # Tags de color por código HTTP
        self._tree.tag_configure("ok",      background="#1a2d1a", foreground=ACCENT_GREEN)
        self._tree.tag_configure("redirect",background="#1a1a2d", foreground=ACCENT_BLUE)
        self._tree.tag_configure("client",  background="#2d2d1a", foreground=ACCENT_YELLOW)
        self._tree.tag_configure("server",  background="#2d1a1a", foreground=ACCENT_RED)
        self._tree.tag_configure("error",   background=BG_ROW_ODD, foreground=TEXT_MUTED)
        self._tree.tag_configure("odd",     background=BG_ROW_ODD)
        self._tree.tag_configure("even",    background=BG_SECONDARY)

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))

    # ── Lógica: payloads ───────────────────────────────────────────────────────

    def _load_builtin(self, filename: str) -> None:
        """Carga uno de los diccionarios incluidos en /payloads/."""
        path = _PAYLOADS_DIR / filename
        self._do_load_payloads(str(path))

    def _load_custom_file(self) -> None:
        """Abre un diálogo para cargar un .txt personalizado."""
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar diccionario de payloads",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._do_load_payloads(path)

    def _do_load_payloads(self, path: str) -> None:
        """Carga los payloads desde `path` y actualiza la UI."""
        try:
            self._payloads = self._intruder.load_payloads(path)
        except (FileNotFoundError, ValueError) as exc:
            messagebox.showerror("Error al cargar payloads", str(exc), parent=self)
            return

        count = len(self._payloads)
        self._payload_count_lbl.configure(
            text=f"{count} cargados", text_color=ACCENT_GREEN,
        )
        self._status_lbl.configure(
            text=f"✓  {count} payloads cargados desde '{Path(path).name}'.",
            text_color=ACCENT_GREEN,
        )
        self._update_payload_preview()

    def _update_payload_preview(self) -> None:
        """Muestra los primeros payloads en el visor de vista previa."""
        preview_lines = self._payloads[:30]
        text = "\n".join(preview_lines)
        if len(self._payloads) > 30:
            text += f"\n… ({len(self._payloads) - 30} más)"

        self._payload_preview.configure(state="normal")
        self._payload_preview.delete("1.0", "end")
        self._payload_preview.insert("1.0", text)
        self._payload_preview.configure(state="disabled")

    # ── Lógica: ataque ─────────────────────────────────────────────────────────

    def _on_attack(self) -> None:
        """Valida los datos y lanza el ataque en un hilo daemon."""
        if self._attacking:
            return

        # Validar template
        raw = self._template_box.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showwarning(
                "Template vacío",
                "Escribe la petición HTTP en el editor de Template.",
                parent=self,
            )
            return

        if not self._intruder.validate_template(raw):
            messagebox.showwarning(
                "Sin puntos de inyección",
                "El template no contiene ningún marcador §§.\n\n"
                "Selecciona el texto que quieres atacar y pulsa 'Añadir §§',\n"
                "o escríbelo manualmente: §valor§",
                parent=self,
            )
            return

        # Validar payloads
        if not self._payloads:
            messagebox.showwarning(
                "Sin payloads",
                "Carga un diccionario de payloads antes de iniciar el ataque.",
                parent=self,
            )
            return

        try:
            self._intruder.set_template(raw)
        except ValueError as exc:
            messagebox.showerror("Error en el template", str(exc), parent=self)
            return

        threads = self._parse_int(self._threads_var.get(), default=5, lo=1, hi=20)
        timeout = self._parse_int(self._timeout_var.get(), default=10, lo=1, hi=120)

        # Limpiar resultados anteriores
        self._clear_results()

        self._attacking = True
        self._btn_attack.configure(state="disabled", text="⏳  Atacando…")
        self._btn_stop.configure(state="normal")
        total = len(self._payloads)
        self._status_lbl.configure(
            text=f"Atacando… 0 / {total}",
            text_color=ACCENT_YELLOW,
        )

        threading.Thread(
            target=self._attack_in_background,
            args=(list(self._payloads), threads, timeout, total),
            daemon=True,
            name="IntruderAttack",
        ).start()

    def _attack_in_background(
        self,
        payloads : list[str],
        threads  : int,
        timeout  : int,
        total    : int,
    ) -> None:
        """Ejecuta Intruder.run() fuera del hilo principal."""
        self._intruder.run(
            payloads  = payloads,
            on_result = lambda r: self.after(0, lambda res=r: self._on_result(res, total)),
            threads   = threads,
            timeout   = timeout,
        )
        # Notificar finalización al hilo de la GUI
        self.after(0, self._on_attack_done)

    def _on_result(self, result: IntruderResult, total: int) -> None:
        """Callback en el hilo principal: agrega una fila a la tabla."""
        self._results.append(result)
        self._insert_row(result)

        done = len(self._results)
        self._status_lbl.configure(
            text=f"Atacando… {done} / {total}",
            text_color=ACCENT_YELLOW,
        )

    def _on_attack_done(self) -> None:
        """Restaura la UI tras finalizar o detener el ataque."""
        self._attacking = False
        self._btn_attack.configure(state="normal", text="💥  Atacar")
        self._btn_stop.configure(state="disabled")

        total   = len(self._results)
        errors  = sum(1 for r in self._results if not r.success)
        successes = total - errors

        self._status_lbl.configure(
            text=f"✓  Ataque completado — {total} enviados, {successes} OK, {errors} errores.",
            text_color=ACCENT_GREEN,
        )

    def _on_stop(self) -> None:
        """Señala al Intruder que detenga el ataque."""
        self._intruder.stop()
        self._btn_stop.configure(state="disabled")
        self._status_lbl.configure(
            text="⏹  Deteniendo… esperando hilos activos.",
            text_color=ACCENT_YELLOW,
        )

    # ── Helpers de la tabla ────────────────────────────────────────────────────

    def _insert_row(self, result: IntruderResult) -> None:
        """Inserta una fila en la tabla con el color apropiado según el status."""
        tag = self._status_tag(result)
        payload_display = result.payload[:80] + ("…" if len(result.payload) > 80 else "")
        status_display  = str(result.status_code) if result.status_code else "ERR"
        ms_display      = f"{result.duration_ms:.0f}"

        self._tree.insert(
            "", "end", tags=(tag,),
            values=(result.index, payload_display, status_display, result.length, ms_display),
        )
        # Auto-scroll al último resultado
        children = self._tree.get_children()
        if children:
            self._tree.see(children[-1])

    @staticmethod
    def _status_tag(result: IntruderResult) -> str:
        """Determina el tag de color según el código HTTP."""
        if not result.success or result.status_code == 0:
            return "error"
        code = result.status_code
        if 200 <= code < 300:
            return "ok"
        if 300 <= code < 400:
            return "redirect"
        if 400 <= code < 500:
            return "client"
        if 500 <= code < 600:
            return "server"
        return "odd"

    def _clear_results(self) -> None:
        """Vacía la tabla y la lista de resultados."""
        self._results.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

    def _export_csv(self) -> None:
        """Exporta los resultados actuales a un archivo CSV."""
        if not self._results:
            messagebox.showinfo("Export", "No hay resultados para exportar.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"intruder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Payload", "Status", "Length", "ms", "Error"])
            for r in self._results:
                writer.writerow([
                    r.index, r.payload, r.status_code,
                    r.length, f"{r.duration_ms:.1f}", r.error or "",
                ])

        messagebox.showinfo("Export", f"✅ Exportado a:\n{path}", parent=self)

    # ── Helpers generales ──────────────────────────────────────────────────────

    def _wrap_selection(self) -> None:
        """Envuelve el texto seleccionado en el editor con marcadores §§."""
        try:
            sel_start = self._template_box.index("sel.first")
            sel_end   = self._template_box.index("sel.last")
            selected  = self._template_box.get(sel_start, sel_end)
            self._template_box.delete(sel_start, sel_end)
            self._template_box.insert(sel_start, f"§{selected}§")
        except tk.TclError:
            # No hay selección → insertar marcador vacío en el cursor
            self._template_box.insert("insert", "§§")

    def _set_template_text(self, text: str) -> None:
        """Reemplaza el contenido del editor de template."""
        self._template_box.delete("1.0", "end")
        if text:
            self._template_box.insert("1.0", text)

    @staticmethod
    def _parse_int(value: str, default: int, lo: int, hi: int) -> int:
        """Parsea un entero de un campo de texto con clamping y valor por defecto."""
        try:
            return max(lo, min(int(value), hi))
        except ValueError:
            return default
