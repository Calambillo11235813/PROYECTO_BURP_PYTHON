"""
gui/proxy_tab.py
----------------
Pestaña 'Proxy' de Mini-Burp Suite.

Responsabilidad ÚNICA: construcción y layout de la UI.
Toda la lógica de eventos está en proxy_events.ProxyEventsMixin.

Mejoras implementadas:
    1. Vinculación de selección de tabla → carga raw en editor inferior.
    2. Auto-scroll inteligente (solo si el usuario está al final)
       con checkbox de control en la barra superior.
    3. Forward toma el texto modificado del editor y lo envía al hilo
       del handler via threading.Event (flujo completo CU-04).

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import customtkinter as ctk

from proxy.server import ProxyServer
from proxy.handler import PendingRequest
from .proxy_events import ProxyEventsMixin
from .colors import (
    BG_DARK, BG_SECONDARY, BG_ROW_ODD, BG_HOVER,
    ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED,
    TEXT_PRIMARY, TEXT_MUTED, BORDER,
)

# ── Constantes ─────────────────────────────────────────────────────────────────
POLL_MS        = 400   # ms entre cada ciclo de polling
PATH_MAX_CHARS = 55    # caracteres máximos de path en la tabla


class ProxyTab(ProxyEventsMixin, ctk.CTkFrame):
    """
    Panel de la pestaña 'Proxy'.

    Hereda de ProxyEventsMixin (event handlers) y ctk.CTkFrame (widget base).
    El orden de herencia es importante: ProxyEventsMixin no tiene __init__,
    por lo que MRO de Python lleva la inicialización a ctk.CTkFrame.

    Args:
        master              : Widget padre (tab del CTkTabview).
        proxy               : Instancia del ProxyServer ya iniciado.
        on_send_to_repeater : Callback opcional para CU-05. Recibe el
                              raw de la petición seleccionada y cambia el
                              foco a la pestaña Repeater.
    """

    def __init__(
        self,
        master              : tk.Widget,
        proxy               : ProxyServer,
        on_send_to_repeater : Optional[Callable[[str], None]] = None,
        on_send_to_intruder : Optional[Callable[[str], None]] = None,
    ) -> None:
        ctk.CTkFrame.__init__(self, master, fg_color="transparent")
        self.proxy    = proxy
        self._pending : PendingRequest | None = None
        self._seen_ids: set[int] = set()
        self._row_by_id: dict[int, str] = {}
        self._repeater_callback = on_send_to_repeater
        self._intruder_callback = on_send_to_intruder
        self._filter_mode_var = tk.StringVar(value=self.proxy.get_filter_mode())
        self._filter_domain_var = tk.StringVar(value="")
        self._filter_status_var = tk.StringVar(value="Sin filtros")
        self._filter_file_var = tk.StringVar(value=f"Archivo: {self.proxy.get_filter_config_path()}")
        self._filter_modal: ctk.CTkToplevel | None = None
        self._filter_rules_listbox: tk.Listbox | None = None
        self._filter_paths_listbox: tk.Listbox | None = None
        self._filter_path_var = tk.StringVar(value="")

        # BooleanVar del checkbox de auto-scroll (True = activo por defecto)
        self._auto_scroll_var = tk.BooleanVar(value=True)

        self._build_control_bar()
        self._build_main_panel()
        self._refresh_filter_summary()
        self._poll()

    # ── Barra de control ──────────────────────────────────────────────────────

    def _build_control_bar(self) -> None:
        """Fila superior: botón Intercept, Clear, Export CSV, Auto-scroll y contador."""
        bar = ctk.CTkFrame(self, fg_color=BG_SECONDARY, height=54, corner_radius=8)
        bar.pack(fill="x", pady=(0, 6))
        bar.pack_propagate(False)

        # ── Botón Intercept (toggle) ───────────────────────────────────────
        self._intercept_btn = ctk.CTkButton(
            bar,
            text="⬛  Interceptar: OFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=BG_DARK, hover_color=BG_HOVER,
            border_color=ACCENT_GREEN, border_width=2,
            text_color=ACCENT_GREEN,
            width=190, height=36, corner_radius=6,
            command=self._toggle_intercept,
        )
        self._intercept_btn.pack(side="left", padx=12, pady=9)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # ── Limpiar ───────────────────────────────────────────────────────
        ctk.CTkButton(
            bar, text="🗑  Limpiar", width=100, height=32,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            corner_radius=6, command=self._clear_history,
        ).pack(side="left", padx=10, pady=9)

        # ── Export CSV ────────────────────────────────────────────────────
        ctk.CTkButton(
            bar, text="💾  Exportar CSV", width=130, height=32,
            fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            corner_radius=6, command=self._export_csv,
        ).pack(side="left", padx=0, pady=9)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        # ── Menú desplegable "Acciones" (Repeater / Intruder) ────────────
        self._actions_var = tk.StringVar(value="⚡  Acciones")
        self._actions_menu = ctk.CTkOptionMenu(
            bar,
            values=["🔁  Enviar al Repeater", "💥  Enviar al Intruder"],
            variable=self._actions_var,
            width=175,
            height=32,
            fg_color="#1f3d5c",
            button_color="#1a3352",
            button_hover_color="#152b45",
            text_color=ACCENT_BLUE,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
            command=self._on_action_selected,
        )
        # No se hace .pack() aquí — aparece al seleccionar una fila

        # ── Checkbox Auto-scroll (derecha) ────────────────────────────────
        ctk.CTkCheckBox(
            bar,
            text="Auto-scroll",
            variable=self._auto_scroll_var,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            fg_color=ACCENT_BLUE,
            hover_color="#1a5fb4",
            width=16, height=16,
            command=self._on_auto_scroll_toggle,
        ).pack(side="right", padx=12)

        # ── Contador ──────────────────────────────────────────────────────
        self._count_lbl = ctk.CTkLabel(
            bar, text="0 peticiones",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self._count_lbl.pack(side="right", padx=10)

        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)

        ctk.CTkButton(
            bar,
            text="⚙️  Configurar Filtros",
            width=170,
            height=32,
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=self._open_filter_modal,
        ).pack(side="left", padx=(10, 6), pady=9)

        ctk.CTkLabel(
            bar,
            textvariable=self._filter_status_var,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(side="left", padx=(2, 0))

    def _on_filter_mode_change(self) -> None:
        """Sincroniza el modo de filtro en tiempo real con el backend."""
        self.proxy.set_filter_mode(self._filter_mode_var.get())
        self.proxy.save_filter_config()
        self._refresh_filter_summary()
        self._refresh_filter_modal_rules()

    def _on_add_filter(self) -> None:
        """Agrega una nueva regla de host (acepta wildcards con '*')."""
        pattern = self._filter_domain_var.get().strip()
        if not pattern:
            return
        if self.proxy.add_filter_pattern(pattern):
            self._filter_domain_var.set("")
            self.proxy.save_filter_config()
        self._refresh_filter_summary()
        self._refresh_filter_modal_rules()

    def _on_clear_filters(self) -> None:
        """Elimina todas las reglas de filtrado de host activas."""
        self.proxy.clear_filter_patterns()
        self.proxy.save_filter_config()
        self._refresh_filter_summary()
        self._refresh_filter_modal_rules()

    def _on_reload_filters(self) -> None:
        """Recarga reglas desde archivo externo editable."""
        self.proxy.load_filter_config()
        self._filter_mode_var.set(self.proxy.get_filter_mode())
        self._refresh_filter_summary()
        self._refresh_filter_modal_rules()

    def _refresh_filter_summary(self) -> None:
        """Actualiza el resumen visual de reglas activas en la barra de filtro."""
        patterns = self.proxy.get_filter_patterns()
        mode = self._filter_mode_var.get().strip().lower()
        mode_title = "Whitelist" if mode == "whitelist" else "Blacklist"
        if not patterns:
            self._filter_status_var.set("Sin filtros")
            return
        self._filter_status_var.set(
            f"Modo actual: {mode_title} ({len(patterns)} reglas)"
        )

    def _open_filter_modal(self) -> None:
        """Abre una ventana modal con la configuración completa de filtros."""
        if self._filter_modal is not None and self._filter_modal.winfo_exists():
            self._filter_modal.focus()
            self._filter_modal.lift()
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Configurar Filtros de Host")
        modal.geometry("760x520")
        modal.minsize(680, 460)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()
        modal.protocol("WM_DELETE_WINDOW", self._close_filter_modal)
        self._filter_modal = modal

        # Limpiar variables asociadas para evitar crashes en CTkEntry tras reabrir el modal
        self._filter_domain_var = tk.StringVar(value="")
        self._filter_path_var = tk.StringVar(value="")
        self._filter_mode_var = tk.StringVar(value=self.proxy.get_filter_mode())

        container = ctk.CTkFrame(modal, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            container,
            text="Configuración de Filtros",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            container,
            textvariable=self._filter_file_var,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        tabs = ctk.CTkTabview(container, fg_color=BG_DARK, segmented_button_selected_color=ACCENT_BLUE)
        tabs.pack(fill="both", expand=True, pady=(0, 10))
        
        tab_hosts = tabs.add("Filtro de Dominios")
        tab_paths = tabs.add("Rutas Ignoradas")

        # ── Tab 1: Dominios ─────────────────────────────────────
        mode_row = ctk.CTkFrame(tab_hosts, fg_color=BG_SECONDARY, corner_radius=8, height=42)
        mode_row.pack(fill="x", pady=(5, 10))
        mode_row.pack_propagate(False)

        ctk.CTkLabel(
            mode_row,
            text="Modo activo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 8))

        ctk.CTkRadioButton(
            mode_row,
            text="Blacklist",
            variable=self._filter_mode_var,
            value="blacklist",
            command=self._on_filter_mode_change,
            text_color=TEXT_MUTED,
            fg_color=ACCENT_RED,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkRadioButton(
            mode_row,
            text="Whitelist",
            variable=self._filter_mode_var,
            value="whitelist",
            command=self._on_filter_mode_change,
            text_color=TEXT_MUTED,
            fg_color=ACCENT_GREEN,
        ).pack(side="left")

        add_row = ctk.CTkFrame(tab_hosts, fg_color=BG_SECONDARY, corner_radius=8, height=48)
        add_row.pack(fill="x", pady=(0, 10))
        add_row.pack_propagate(False)

        ctk.CTkEntry(
            add_row,
            textvariable=self._filter_domain_var,
            height=32,
            placeholder_text="Dominio o wildcard, ej: *.microsoft.com",
            fg_color=BG_DARK,
            text_color=TEXT_PRIMARY,
            border_color=BORDER,
        ).pack(side="left", fill="x", expand=True, padx=(12, 8), pady=8)

        ctk.CTkButton(
            add_row,
            text="Añadir",
            width=92,
            height=32,
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            command=self._on_add_filter,
        ).pack(side="left", pady=8)

        ctk.CTkButton(
            add_row,
            text="Limpiar",
            width=92,
            height=32,
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            command=self._on_clear_filters,
        ).pack(side="left", padx=(8, 8), pady=8)

        ctk.CTkButton(
            add_row,
            text="Recargar",
            width=92,
            height=32,
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            command=self._on_reload_filters,
        ).pack(side="left", padx=(0, 12), pady=8)

        ctk.CTkButton(
            add_row,
            text="Eliminar seleccionada",
            width=180,
            height=32,
            fg_color=BG_HOVER,
            hover_color="#373e47",
            text_color=TEXT_MUTED,
            command=self._on_remove_selected_filter,
        ).pack(side="left", padx=(0, 12), pady=8)

        ctk.CTkLabel(
            tab_hosts,
            text="Dominios en la lista activa:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 6))

        list_frame = tk.Frame(tab_hosts, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER)
        list_frame.pack(fill="both", expand=True)

        self._filter_rules_listbox = tk.Listbox(
            list_frame,
            bg=BG_DARK,
            fg=TEXT_PRIMARY,
            selectbackground=ACCENT_BLUE,
            selectforeground="#ffffff",
            activestyle="none",
            font=("Consolas", 12),
            borderwidth=0,
            highlightthickness=0,
        )
        self._filter_rules_listbox.pack(side="left", fill="both", expand=True)
        self._filter_rules_listbox.bind("<Double-Button-1>", self._on_remove_selected_filter)

        rules_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._filter_rules_listbox.yview)
        rules_scroll.pack(side="right", fill="y")
        self._filter_rules_listbox.configure(yscrollcommand=rules_scroll.set)

        # ── Tab 2: Rutas Ignoradas ──────────────────────────────
        ctk.CTkLabel(
            tab_paths,
            text="Rutas y extensiones que el proxy reenviará silenciosamente sin mostrar en el historial.",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED, justify="left", anchor="w"
        ).pack(fill="x", pady=(5, 10))

        add_path_row = ctk.CTkFrame(tab_paths, fg_color=BG_SECONDARY, corner_radius=8, height=48)
        add_path_row.pack(fill="x", pady=(0, 10))
        add_path_row.pack_propagate(False)
        
        ctk.CTkEntry(
            add_path_row, textvariable=self._filter_path_var, height=32,
            placeholder_text="Ruta, ej: /socket.io/* o *tunnel*",
            fg_color=BG_DARK, text_color=TEXT_PRIMARY, border_color=BORDER,
        ).pack(side="left", fill="x", expand=True, padx=(12, 8), pady=8)

        ctk.CTkButton(
            add_path_row, text="Añadir", width=92, height=32, fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, command=self._on_add_filter_path,
        ).pack(side="left", pady=8)
        
        ctk.CTkButton(
            add_path_row, text="Limpiar", width=92, height=32, fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, command=self._on_clear_filter_paths,
        ).pack(side="left", padx=(8, 8), pady=8)

        ctk.CTkButton(
            add_path_row, text="Eliminar seleccionada", width=180, height=32, fg_color=BG_HOVER, hover_color="#373e47",
            text_color=TEXT_MUTED, command=self._on_remove_selected_path,
        ).pack(side="left", padx=(8, 12), pady=8)

        paths_list_frame = tk.Frame(tab_paths, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER)
        paths_list_frame.pack(fill="both", expand=True)

        self._filter_paths_listbox = tk.Listbox(
            paths_list_frame, bg=BG_DARK, fg=TEXT_PRIMARY, selectbackground=ACCENT_BLUE,
            selectforeground="#ffffff", activestyle="none", font=("Consolas", 12),
            borderwidth=0, highlightthickness=0,
        )
        self._filter_paths_listbox.pack(side="left", fill="both", expand=True)
        self._filter_paths_listbox.bind("<Double-Button-1>", self._on_remove_selected_path)

        paths_scroll = ttk.Scrollbar(paths_list_frame, orient="vertical", command=self._filter_paths_listbox.yview)
        paths_scroll.pack(side="right", fill="y")
        self._filter_paths_listbox.configure(yscrollcommand=paths_scroll.set)

        # ── Footer común ─────────────────────────────────────────

        footer = ctk.CTkFrame(container, fg_color="transparent", height=42)
        footer.pack(fill="x", pady=(10, 0))
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer,
            text="Guardar y Cerrar",
            width=150,
            height=32,
            fg_color=ACCENT_GREEN,
            hover_color="#2ea843",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._close_filter_modal,
        ).pack(side="right")

        self._refresh_filter_modal_rules()

    def _close_filter_modal(self) -> None:
        """Cierra el modal de filtros guardando estado actual en archivo."""
        self.proxy.save_filter_config()
        if self._filter_modal is not None and self._filter_modal.winfo_exists():
            self._filter_modal.grab_release()
            self._filter_modal.destroy()
        self._filter_modal = None
        self._filter_rules_listbox = None
        self._filter_paths_listbox = None

    def _on_add_filter_path(self) -> None:
        pattern = self._filter_path_var.get().strip()
        if not pattern: return
        if self.proxy.add_ignore_path(pattern):
            self._filter_path_var.set("")
            self.proxy.save_filter_config()
        self._refresh_filter_modal_rules()

    def _on_clear_filter_paths(self) -> None:
        self.proxy.clear_ignore_paths()
        self.proxy.save_filter_config()
        self._refresh_filter_modal_rules()

    def _on_remove_selected_path(self, _event: tk.Event | None = None) -> None:
        if self._filter_paths_listbox is None: return
        selection = self._filter_paths_listbox.curselection()
        if not selection: return
        selected = self._filter_paths_listbox.get(selection[0]).strip()
        if not selected or selected.startswith("("): return
        
        if self.proxy.remove_ignore_path(selected):
            self.proxy.save_filter_config()
            self._refresh_filter_modal_rules()

    def _on_remove_selected_filter(self, _event: tk.Event | None = None) -> None:
        """Elimina la regla seleccionada de la lista activa."""
        if self._filter_rules_listbox is None:
            return

        selection = self._filter_rules_listbox.curselection()
        if not selection:
            return

        selected_text = self._filter_rules_listbox.get(selection[0]).strip()
        if not selected_text or selected_text.startswith("("):
            return

        if self.proxy.remove_filter_pattern(selected_text):
            self.proxy.save_filter_config()
            self._refresh_filter_summary()
            self._refresh_filter_modal_rules()

    def _refresh_filter_modal_rules(self) -> None:
        """Refresca la lista visible de dominios del modo activo en el modal."""
        if self._filter_rules_listbox is None:
            return

        patterns = self.proxy.get_filter_patterns()
        mode = self._filter_mode_var.get().strip().lower()
        mode_title = "Whitelist" if mode == "whitelist" else "Blacklist"

        self._filter_rules_listbox.delete(0, "end")
        if not patterns:
            self._filter_rules_listbox.insert("end", "(Sin reglas en esta lista)")
        else:
            for pattern in patterns:
                self._filter_rules_listbox.insert("end", pattern)
                
        # Refrescar Paths
        if self._filter_paths_listbox is not None:
            self._filter_paths_listbox.delete(0, "end")
            paths = self.proxy.get_ignore_paths()
            if not paths:
                self._filter_paths_listbox.insert("end", "(Sin rutas ignoradas)")
            else:
                for p in paths:
                    self._filter_paths_listbox.insert("end", p)

        self._filter_status_var.set(
            f"Modo actual: {mode_title} ({len(patterns)} reglas | {len(paths if self._filter_paths_listbox else [])} paths)"
        )

    # ── Panel principal ────────────────────────────────────────────────────────

    def _build_main_panel(self) -> None:
        """Vista maestro-detalle con sash redimensionable (estilo Burp Suite)."""
        paned = tk.PanedWindow(
            self,
            orient=tk.VERTICAL,
            bg=BG_DARK,
            sashwidth=5,
            sashrelief="flat",
            sashpad=1,
        )
        paned.pack(fill="both", expand=True)

        # Panel superior: tabla de historial
        table_frame = tk.Frame(paned, bg=BG_DARK)
        paned.add(table_frame, minsize=120, stretch="always")
        self._build_history_table(table_frame)

        # Panel inferior: detalle Request / Response
        details_frame = tk.Frame(paned, bg=BG_SECONDARY)
        paned.add(details_frame, minsize=220, stretch="always")
        self._build_details_panel(details_frame)

        # Posicionar el sash: tabla ocupa ~50% del espacio al inicio
        self.after(150, lambda: paned.sash_place(0, 1, int(paned.winfo_height() * 0.50)))

    # ── Tabla de historial ────────────────────────────────────────────────────

    def _build_history_table(self, parent: tk.Frame) -> None:
        """
        Tabla ttk.Treeview estilizada en modo dark.
        Columnas: #, METHOD, HOST, PATH, STATUS, ms.
        El evento <<TreeviewSelect>> está vinculado a _on_row_select.
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
            ("PATH",   260, "w",      True),
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
        self._tree.tag_configure("pending",     background="#3a2d14",
                            foreground="#f2cc60")

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        # Listener de selección → carga raw en el editor inferior
        self._tree.bind("<<TreeviewSelect>>", self._on_row_select)

    # ── Detalle inferior (Request/Response) ───────────────────────────────────

    def _build_details_panel(self, parent: tk.Frame) -> None:
        """Panel dual Request / Response con layout grid correcto (estilo IDE)."""
        # Fila 0: barra de encabezados (altura fija)
        # Fila 1: textboxes (absorbe TODO el espacio restante)
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)
        # Dos columnas iguales al 50/50
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        # ── Encabezado izquierdo (Request) ──
        header_left = tk.Frame(parent, bg=BG_SECONDARY, height=28)
        header_left.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=(4, 2))
        header_left.pack_propagate(False)

        self._btn_frame = tk.Frame(header_left, bg=BG_SECONDARY)
        self._btn_frame.pack(side="right")

        self._editor_lbl = tk.Label(
            header_left,
            text="📋 Request",
            font=("Consolas", 10, "bold"),
            fg=TEXT_MUTED,
            bg=BG_SECONDARY,
            anchor="w",
        )
        self._editor_lbl.pack(side="left", fill="x", expand=True)

        self._btn_forward = ctk.CTkButton(
            self._btn_frame, text="▶  Reenviar",
            width=110, height=26, fg_color=ACCENT_GREEN, hover_color="#2ea843",
            text_color="#ffffff", font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6, command=self._on_forward,
        )
        self._btn_drop = ctk.CTkButton(
            self._btn_frame, text="✕  Descartar",
            width=100, height=26, fg_color=ACCENT_RED, hover_color="#da3633",
            text_color="#ffffff", font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6, command=self._on_drop,
        )

        # ── Encabezado derecho (Response) ──
        header_right = tk.Frame(parent, bg=BG_SECONDARY, height=28)
        header_right.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(4, 2))
        header_right.pack_propagate(False)
        tk.Label(
            header_right,
            text="📥 Response",
            font=("Consolas", 10, "bold"),
            fg=TEXT_MUTED,
            bg=BG_SECONDARY,
            anchor="w",
        ).pack(side="left")

        # ── Textbox Request (editable durante intercepción) ──
        req_frame = tk.Frame(parent, bg=BORDER)
        req_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 3), pady=(0, 6))
        req_frame.grid_rowconfigure(0, weight=1)
        req_frame.grid_columnconfigure(0, weight=1)

        self._editor_box = tk.Text(
            req_frame,
            font=("Consolas", 11),
            bg=BG_DARK, fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            selectbackground=ACCENT_BLUE,
            relief="flat", borderwidth=0,
            wrap="none",
        )
        vsb_req = ttk.Scrollbar(req_frame, orient="vertical",   command=self._editor_box.yview)
        hsb_req = ttk.Scrollbar(req_frame, orient="horizontal", command=self._editor_box.xview)
        self._editor_box.configure(yscrollcommand=vsb_req.set, xscrollcommand=hsb_req.set)
        vsb_req.grid(row=0, column=1, sticky="ns")
        hsb_req.grid(row=1, column=0, sticky="ew")
        self._editor_box.grid(row=0, column=0, sticky="nsew")
        self._editor_box.configure(state="disabled")

        # ── Textbox Response (solo lectura) ──
        resp_frame = tk.Frame(parent, bg=BORDER)
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
            wrap="none",
        )
        vsb_resp = ttk.Scrollbar(resp_frame, orient="vertical",   command=self._response_box.yview)
        hsb_resp = ttk.Scrollbar(resp_frame, orient="horizontal", command=self._response_box.xview)
        self._response_box.configure(yscrollcommand=vsb_resp.set, xscrollcommand=hsb_resp.set)
        vsb_resp.grid(row=0, column=1, sticky="ns")
        hsb_resp.grid(row=1, column=0, sticky="ew")
        self._response_box.grid(row=0, column=0, sticky="nsew")
        self._response_box.configure(state="disabled")

    def _format_request_title(
        self,
        req_id: int,
        method: str,
        host: str,
        path: str,
        prefix: str = "📋",
    ) -> str:
        """
        Construye un título corto para el encabezado del editor.

        Preserva siempre el número de petición y el método, truncando host/path
        para evitar que oculten los botones Forward/Drop.
        """
        host_short = host if len(host) <= 32 else host[:31] + "…"
        path_short = path if len(path) <= 68 else path[:67] + "…"
        return f"{prefix} #{req_id}  {method}  {host_short}{path_short}"

    # ── Ciclo de polling ───────────────────────────────────────────────────────

    def _poll(self) -> None:
        """
        Ciclo de refresco que corre en el hilo principal cada POLL_MS ms.
        Actualiza la tabla con nuevas peticiones y detecta intercepts.
        """
        self._refresh_table()
        self._check_intercept_queue()
        self.after(POLL_MS, self._poll)

    def _refresh_table(self) -> None:
        """
        Inserta en la tabla todos los registros nuevos del historial.

        Auto-scroll inteligente:
            - Si el checkbox 'Auto-scroll' está activo Y el usuario ya
              estaba al final de la lista, se desplaza automáticamente.
            - Si el usuario scrolleó hacia arriba para revisar peticiones
              anteriores, NO se interrumpe su navegación.
        """
        # Capturar posición ANTES de insertar (para decisión de scroll)
        was_at_bottom = self._is_scrolled_to_bottom()

        for record in self.proxy.history.all():
            path_display   = record.path
            if len(path_display) > PATH_MAX_CHARS:
                path_display = path_display[:PATH_MAX_CHARS] + "…"
            status_display = (record.response_status or "—")[:32]

            if record.id in self._seen_ids:
                item_id = self._row_by_id.get(record.id)
                if item_id:
                    self._tree.item(
                        item_id,
                        values=(
                            record.id, record.method, record.host,
                            path_display, status_display,
                            f"{record.duration_ms:.0f}",
                        ),
                        tags=(self._row_tag(record.id, record.response_status),),
                    )
                continue

            self._seen_ids.add(record.id)
            tag = self._row_tag(record.id, record.response_status)

            item_id = self._tree.insert(
                "", "end", tags=(tag,),
                values=(
                    record.id, record.method, record.host,
                    path_display, status_display,
                    f"{record.duration_ms:.0f}",
                ),
            )
            self._row_by_id[record.id] = item_id

        # Auto-scroll: solo si estaba al fondo y el checkbox está activo
        if was_at_bottom and self._auto_scroll_var.get():
            children = self._tree.get_children()
            if children:
                self._tree.see(children[-1])

        total = len(self._seen_ids)
        noun  = "petición" if total == 1 else "peticiones"
        self._count_lbl.configure(text=f"{total} {noun}")

    def _row_tag(self, req_id: int, response_status: str) -> str:
        """Retorna el tag visual para una fila según su estado actual."""
        if response_status.upper() == "PENDIENTE":
            return "pending"
        return "even" if req_id % 2 == 0 else "odd"

    def _check_intercept_queue(self) -> None:
        """
        Obtiene la siguiente petición interceptada de la Queue y la muestra
        en el editor, habilitando los botones Forward y Drop.
        Thread-safe: InterceptController.next_pending() usa Queue.get_nowait().
        """
        if self._pending is not None:
            return

        pending = self.proxy.intercept.next_pending()
        if pending is None:
            return

        self._pending = pending
        text = pending.display_text or pending.raw.decode("utf-8", errors="replace")
        self._set_editor_text(text, editable=True)
        self._set_response_text("")
        self._editor_lbl.configure(text=self._format_request_title(
            req_id=pending.id,
            method=pending.parsed.method,
            host=pending.parsed.host,
            path=pending.parsed.path,
            prefix="🔴 INTERCEPTADO",
        ))
        self._show_intercept_buttons()
