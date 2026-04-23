"""
logic/exporter.py
-----------------
Módulo D: Reporting & Analysis (CU-12: Exportación de Resultados)

Provee funciones para exportar los hallazgos de seguridad agrupados
a formatos estándar como HTML y PDF.
"""

from datetime import datetime
from fpdf import FPDF

def _get_severity_color_hex(severity: str) -> str:
    """Devuelve un color hexadecimal según la severidad para HTML."""
    colors = {
        "Critical": "#f85149",
        "High": "#f85149",
        "Medium": "#e3b341",
        "Low": "#1f6feb",
        "Info": "#1f6feb",
    }
    return colors.get(severity, "#8b949e")

def _get_severity_color_rgb(severity: str) -> tuple[int, int, int]:
    """Devuelve un color RGB según la severidad para FPDF."""
    colors = {
        "Critical": (248, 81, 73),
        "High": (248, 81, 73),
        "Medium": (227, 179, 65),
        "Low": (31, 111, 235),
        "Info": (31, 111, 235),
    }
    return colors.get(severity, (139, 148, 158))

def export_to_html(agrupados: list, filepath: str) -> bool:
    """
    Exporta los hallazgos agrupados a un archivo HTML con estilo Dark Mode.

    Args:
        agrupados (list): Lista de objetos GroupedFinding.
        filepath (str): Ruta donde guardar el archivo.
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Estructura base del HTML y CSS
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>NetLens - Reporte de Auditoría de Seguridad</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d1117; color: #e6edf3; margin: 0; padding: 40px; }}
        h1 {{ color: #ffffff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
        .header-info {{ color: #8b949e; font-size: 14px; margin-bottom: 40px; }}
        .card {{ background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 20px; padding: 20px; border-left-width: 5px; }}
        .card h2 {{ margin-top: 0; font-size: 18px; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; color: #0d1117; display: inline-block; margin-left: 15px; }}
        .paths {{ background-color: #0d1117; border: 1px solid #30363d; padding: 10px; border-radius: 4px; margin-top: 15px; font-family: Consolas, monospace; font-size: 12px; color: #8b949e; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }}
        .desc {{ margin-top: 10px; font-size: 14px; color: #c9d1d9; }}
    </style>
</head>
<body>
    <h1>🛡️ NetLens - Reporte de Auditoría de Seguridad</h1>
    <div class="header-info">Generado el: {timestamp} | Total de Hallazgos Únicos: {len(agrupados)}</div>
"""
        # Iterar sobre grupos para crear las tarjetas
        for group in agrupados:
            finding = group.base_finding
            color = _get_severity_color_hex(finding.severity)
            
            paths_html = "&#10;".join(sorted(list(group.paths)))
            
            card = f"""
    <div class="card" style="border-left-color: {color};">
        <h2>
            {finding.title} <span style="color: #8b949e; font-weight: normal;">[{group.host}]</span>
            <span class="badge" style="background-color: {color};">{group.count} peticiones afectadas</span>
        </h2>
        <div style="font-weight: bold; color: {color}; margin-bottom: 10px;">Severidad: {finding.severity}</div>
        <div class="desc">{finding.description}</div>
        <div class="paths">{paths_html}</div>
    </div>
"""
            html += card
            
        html += """
</body>
</html>"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
            
        return True
    except Exception as e:
        print(f"Error exportando HTML: {e}")
        return False


def export_to_pdf(agrupados: list, filepath: str) -> bool:
    """
    Exporta los hallazgos agrupados a un documento PDF,
    incluyendo las rutas afectadas.

    Args:
        agrupados (list): Lista de objetos GroupedFinding.
        filepath (str): Ruta donde guardar el archivo.
    """
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Título Principal
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 10, "NetLens - Reporte de Auditoria de Seguridad", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        
        # Fecha y resumen
        pdf.set_font("Helvetica", "", 10)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf.cell(0, 10, f"Generado el: {timestamp} | Total de Hallazgos Unicos: {len(agrupados)}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        
        # Iterar sobre grupos
        for group in agrupados:
            finding = group.base_finding
            r, g, b = _get_severity_color_rgb(finding.severity)
            
            # Caja con el título
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(r, g, b)
            title_text = f"[{finding.severity}] {finding.title} ({group.host})"
            pdf.multi_cell(0, 8, title_text, new_x="LMARGIN", new_y="NEXT")
            
            # Descripción
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, finding.description, new_x="LMARGIN", new_y="NEXT")
            
            # Badge de impacto
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 8, f"Impacto: {group.count} peticion(es) afectada(s):", new_x="LMARGIN", new_y="NEXT")
            
            # Detalle de Rutas Afectadas
            pdf.set_font("Courier", "", 9)
            pdf.set_text_color(80, 80, 80)
            
            sorted_paths = sorted(list(group.paths))
            limite_rutas = 15
            
            for i, path in enumerate(sorted_paths):
                if i >= limite_rutas:
                    break
                # Usar multi_cell con tabulación simulada para manejar rutas que exceden el ancho
                pdf.multi_cell(0, 5, f"   - {path}", new_x="LMARGIN", new_y="NEXT")
                
            if len(sorted_paths) > limite_rutas:
                rutas_omitidas = len(sorted_paths) - limite_rutas
                pdf.set_font("Courier", "I", 9)
                pdf.cell(0, 6, f"   ... y {rutas_omitidas} rutas adicionales omitidas para mantener la legibilidad.", new_x="LMARGIN", new_y="NEXT")
            
            # Espaciado final antes del siguiente hallazgo
            pdf.ln(8)
            
        pdf.output(filepath)
        return True
    except Exception as e:
        print(f"Error exportando PDF: {e}")
        return False
