"""
gui/reporting_tab.py
--------------------
Panel visual para presentar los resultados del escáner pasivo de vulnerabilidades.

Muestra métricas globales y lista de hallazgos detectados sobre el historial
de tráfico interceptado de forma organizada y responsiva.

Autores: Diogo Nicolas Rodriguez Gomez, Javier Soliz Rueda
Materia: Ingeniería de Software 2
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from logic.scanner import PassiveScanner, PassiveFinding
from logic.exporter import export_to_html, export_to_pdf
from .colors import (
    BG_DARK, BG_SECONDARY, BG_HOVER, BORDER,
    ACCENT_BLUE, ACCENT_RED, ACCENT_YELLOW, ACCENT_GREEN,
    TEXT_PRIMARY, TEXT_MUTED
)

from dataclasses import dataclass, field

@dataclass
class GroupedFinding:
    """Representa una vulnerabilidad agrupada por título y host."""
    base_finding: PassiveFinding
    host: str
    count: int = 0
    paths: set[str] = field(default_factory=set)


class ReportingTab(ctk.CTkFrame):
    """
    Pestaña de Reportes y Análisis Pasivo.

    Provee un dashboard interactivo donde el usuario puede ejecutar el escáner
    sobre su historial y visualizar contadores e informes detallados por cada
    vulnerabilidad detectada.
    """

    def __init__(self, master: tk.Widget, **kwargs) -> None:
        super().__init__(master, fg_color=BG_DARK, corner_radius=0, **kwargs)

        self._scanner = PassiveScanner()

        # Almacena los hallazgos actuales agrupados para poder exportarlos
        self._current_findings: list[GroupedFinding] = []

        # Diccionario para mantener referencias a los Labels de contadores
        self._counters: dict[str, ctk.CTkLabel] = {}

        self._build_header()
        self._build_dashboard()
        self._build_findings_list()

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _build_header(self) -> None:
        """Construye el encabezado con el título y el botón de acción."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title = ctk.CTkLabel(
            header_frame,
            text="🛡️ Panel de Seguridad y Reportes",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.pack(side="left")

        # Contenedor para botones derechos
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        self.btn_export_pdf = ctk.CTkButton(
            btn_frame,
            text="Exportar PDF",
            font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            fg_color=BG_HOVER,
            text_color=TEXT_PRIMARY,
            corner_radius=6,
            height=30,
            width=100,
            command=self._export_pdf
        )
        self.btn_export_pdf.pack(side="right", padx=(10, 0))

        self.btn_export_html = ctk.CTkButton(
            btn_frame,
            text="Exportar HTML",
            font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            fg_color=BG_HOVER,
            text_color=TEXT_PRIMARY,
            corner_radius=6,
            height=30,
            width=100,
            command=self._export_html
        )
        self.btn_export_html.pack(side="right", padx=(10, 0))

        # Botón para ejecutar el escaneo
        self.btn_scan = ctk.CTkButton(
            btn_frame,
            text="Ejecutar Escaneo Pasivo",
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            fg_color=ACCENT_BLUE,
            text_color=TEXT_PRIMARY,
            corner_radius=6,
            height=36,
        )
        self.btn_scan.pack(side="right", padx=(10, 0))

    def _build_dashboard(self) -> None:
        """Construye la fila de tarjetas métricas."""
        dashboard_frame = ctk.CTkFrame(self, fg_color="transparent")
        dashboard_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Configuramos un grid parejo para 4 tarjetas
        dashboard_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="card")

        self._create_metric_card(
            parent=dashboard_frame,
            col=0,
            key="total",
            title="Total Hallazgos",
            color=TEXT_PRIMARY
        )
        self._create_metric_card(
            parent=dashboard_frame,
            col=1,
            key="high",
            title="Críticos / Altos",
            color=ACCENT_RED
        )
        self._create_metric_card(
            parent=dashboard_frame,
            col=2,
            key="medium",
            title="Medios",
            color=ACCENT_YELLOW
        )
        self._create_metric_card(
            parent=dashboard_frame,
            col=3,
            key="low",
            title="Info / Bajos",
            color=ACCENT_BLUE
        )

    def _create_metric_card(self, parent: ctk.CTkFrame, col: int, key: str, title: str, color: str) -> None:
        """Crea una tarjeta individual para el dashboard."""
        card = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, border_width=1, border_color=BORDER, corner_radius=8)
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)

        lbl_title = ctk.CTkLabel(
            card,
            text=title.upper(),
            font=ctk.CTkFont(family="Inter", size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        lbl_title.pack(pady=(12, 0))

        lbl_count = ctk.CTkLabel(
            card,
            text="0",
            font=ctk.CTkFont(family="Inter", size=28, weight="bold"),
            text_color=color,
        )
        lbl_count.pack(pady=(4, 12))

        self._counters[key] = lbl_count

    def _build_findings_list(self) -> None:
        """Construye el área scrollable para mostrar los resultados."""
        # Contenedor con borde para separar del fondo
        container = ctk.CTkFrame(self, fg_color=BG_SECONDARY, corner_radius=8, border_width=1, border_color=BORDER)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Cabecera de la lista
        header = ctk.CTkFrame(container, fg_color="transparent", height=30)
        header.pack(fill="x", padx=16, pady=(10, 0))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="HALLAZGO DETECTADO", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(side="left")

        # Separador
        tk.Frame(container, bg=BORDER, height=1).pack(fill="x", padx=10, pady=(6, 0))

        # Scrollable Frame
        self.scrollable_list = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.scrollable_list.pack(fill="both", expand=True, padx=10, pady=10)

    # ── Lógica y Actualización de UI ──────────────────────────────────────────

    def run_analysis(self, history_data: list) -> None:
        """
        Ejecuta el escáner sobre el historial proveído y agrupa los resultados
        por (Título, Host) para evitar saturar la interfaz.

        Args:
            history_data (list): Lista de objetos RequestRecord a analizar.
        """
        # 1. Ejecutar análisis crudo
        findings = self._scanner.scan_history(history_data)

        # 2. Agrupar resultados por (title, host)
        history_map = {r.id: r for r in history_data}
        groups: dict[tuple[str, str], GroupedFinding] = {}

        for f in findings:
            record = history_map.get(f.request_id)
            if not record:
                continue
            
            host = record.host
            path = record.path
            key = (f.title, host)

            if key not in groups:
                groups[key] = GroupedFinding(
                    base_finding=f,
                    host=host,
                )
            groups[key].count += 1
            groups[key].paths.add(path)

        grouped_list = list(groups.values())
        self._current_findings = grouped_list

        # 3. Actualizar contadores (basados en los grupos únicos)
        count_high = sum(1 for g in grouped_list if g.base_finding.severity in ("High", "Critical"))
        count_med  = sum(1 for g in grouped_list if g.base_finding.severity == "Medium")
        count_low  = sum(1 for g in grouped_list if g.base_finding.severity in ("Low", "Info"))

        self._counters["total"].configure(text=str(len(grouped_list)))
        self._counters["high"].configure(text=str(count_high))
        self._counters["medium"].configure(text=str(count_med))
        self._counters["low"].configure(text=str(count_low))

        # 4. Limpiar lista visual actual (winfo_children es eficiente si hay menos widgets gracias a la agrupación)
        for widget in self.scrollable_list.winfo_children():
            widget.destroy()

        # 5. Renderizar nuevos hallazgos agrupados
        if not grouped_list:
            self._render_empty_state()
            return

        for group in grouped_list:
            self._render_finding_row(group)

    def _render_empty_state(self) -> None:
        """Muestra un mensaje cuando no hay vulnerabilidades detectadas."""
        lbl = ctk.CTkLabel(
            self.scrollable_list,
            text="🎉 ¡Excelente! No se detectaron vulnerabilidades en el historial actual.",
            font=ctk.CTkFont(size=14),
            text_color=ACCENT_GREEN,
        )
        lbl.pack(pady=40)

    def _render_finding_row(self, group: GroupedFinding) -> None:
        """
        Renderiza una fila individual para un grupo de vulnerabilidades.

        Args:
            group (GroupedFinding): Los datos del hallazgo agrupado.
        """
        row = ctk.CTkFrame(self.scrollable_list, fg_color="transparent")
        row.pack(fill="x", pady=6, padx=4)

        finding = group.base_finding

        # Determinar color según severidad
        color_map = {
            "Critical": ACCENT_RED,
            "High": ACCENT_RED,
            "Medium": ACCENT_YELLOW,
            "Low": ACCENT_BLUE,
            "Info": ACCENT_BLUE,
        }
        color = color_map.get(finding.severity, TEXT_MUTED)

        # Indicador visual de severidad (Línea lateral)
        indicator = tk.Frame(row, bg=color, width=4)
        indicator.pack(side="left", fill="y", padx=(0, 10))

        # Contenedor de texto
        text_container = ctk.CTkFrame(row, fg_color="transparent")
        text_container.pack(side="left", fill="x", expand=True)

        # Fila superior: Título, Host y Badge de peticiones
        top_row = ctk.CTkFrame(text_container, fg_color="transparent")
        top_row.pack(fill="x", side="top")

        ctk.CTkLabel(
            top_row,
            text=f"{finding.title}  [{group.host}]",
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        # Badge indicador del número de peticiones
        ctk.CTkLabel(
            top_row,
            text=f"{group.count} peticiones afectadas",
            font=ctk.CTkFont(family="Inter", size=10, weight="bold"),
            text_color=BG_DARK,
            fg_color=color,
            corner_radius=4,
        ).pack(side="left", padx=12)

        ctk.CTkLabel(
            top_row,
            text=f"Severidad: {finding.severity}",
            font=ctk.CTkFont(family="Inter", size=11, weight="bold"),
            text_color=color,
        ).pack(side="right")

        # Fila intermedia: Descripción
        desc = ctk.CTkLabel(
            text_container,
            text=finding.description,
            font=ctk.CTkFont(family="Inter", size=12),
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=800, # Evitar desborde horizontal
        )
        desc.pack(side="top", pady=(4, 2), anchor="w")

        # Fila inferior: Botón para ver rutas afectadas
        btn_paths = ctk.CTkButton(
            text_container,
            text=f"▶ Ver detalle de las {len(group.paths)} rutas afectadas",
            font=ctk.CTkFont(family="Inter", size=11, weight="bold"),
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=ACCENT_BLUE,
            anchor="w",
            height=24,
            command=lambda t=finding.title, p=group.paths: self._show_paths_modal(t, p)
        )
        btn_paths.pack(side="top", pady=(0, 4), anchor="w")

        # Separador sutil al fondo de la fila
        tk.Frame(self.scrollable_list, bg=BG_DARK, height=1).pack(fill="x", padx=10, pady=2)

    def _show_paths_modal(self, title: str, paths: set) -> None:
        """
        Abre una ventana secundaria (modal) mostrando el detalle
        completo de todas las rutas afectadas por un hallazgo.
        """
        modal = ctk.CTkToplevel(self)
        modal.title("Detalle de Rutas Afectadas")
        modal.geometry("500x400")
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        # Título del hallazgo en el modal
        ctk.CTkLabel(
            modal, 
            text=title,
            font=ctk.CTkFont(family="Inter", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
            wraplength=460
        ).pack(pady=(20, 10), padx=20, anchor="w")

        # Área de texto scrollable para las rutas
        textbox = ctk.CTkTextbox(
            modal, 
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_DARK,
            border_width=1,
            border_color=BORDER,
            wrap="none"
        )
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Insertar datos y bloquear escritura
        sorted_paths = sorted(list(paths))
        textbox.insert("1.0", "\n".join(sorted_paths))
        textbox.configure(state="disabled")

    # ── Exportación ─────────────────────────────────────────────────────────

    def _export_html(self) -> None:
        """Exporta los hallazgos mostrados a un archivo HTML."""
        if not self._current_findings:
            messagebox.showwarning("Aviso", "No hay hallazgos para exportar. Ejecuta el escaneo primero.")
            return
            
        filepath = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML files", "*.html")],
            title="Guardar Reporte HTML"
        )
        
        if filepath:
            success = export_to_html(self._current_findings, filepath)
            if success:
                messagebox.showinfo("Éxito", f"Reporte exportado exitosamente a:\n{filepath}")
            else:
                messagebox.showerror("Error", "Ocurrió un error al intentar exportar el archivo HTML.")

    def _export_pdf(self) -> None:
        """Exporta los hallazgos mostrados a un archivo PDF."""
        if not self._current_findings:
            messagebox.showwarning("Aviso", "No hay hallazgos para exportar. Ejecuta el escaneo primero.")
            return
            
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Guardar Reporte PDF"
        )
        
        if filepath:
            success = export_to_pdf(self._current_findings, filepath)
            if success:
                messagebox.showinfo("Éxito", f"Reporte exportado exitosamente a:\n{filepath}")
            else:
                messagebox.showerror("Error", "Ocurrió un error al intentar exportar el archivo PDF.\nAsegúrate de que el archivo no esté abierto en otro programa.")
