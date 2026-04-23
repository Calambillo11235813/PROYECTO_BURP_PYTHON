"""
tests/test_exporter.py
----------------------
Pruebas unitarias para el módulo de exportación de reportes (logic/exporter.py).
"""

import unittest
import os

from logic.scanner import PassiveFinding
from gui.reporting_tab import GroupedFinding
from logic.exporter import export_to_html, export_to_pdf

class TestExporter(unittest.TestCase):
    """Pruebas unitarias para garantizar que los reportes se generan correctamente."""

    def setUp(self) -> None:
        """Configura rutas temporales y datos simulados antes de cada prueba."""
        self.test_html_path = "test_report.html"
        self.test_pdf_path = "test_report.pdf"
        
        # Crear mocks de hallazgos agrupados
        finding1 = PassiveFinding(
            request_id=1,
            severity="High",
            title="Fuga de Información: Error de Base de Datos",
            description="Se encontró un error de base de datos SQL."
        )
        group1 = GroupedFinding(
            base_finding=finding1,
            host="api.example.com",
            count=3,
            paths={"/api/users", "/login", "/search"}
        )
        
        finding2 = PassiveFinding(
            request_id=2,
            severity="Low",
            title="Falta X-Frame-Options (Clickjacking)",
            description="La cabecera de seguridad no está presente."
        )
        group2 = GroupedFinding(
            base_finding=finding2,
            host="www.example.com",
            count=1,
            paths={"/"}
        )
        
        self.agrupados = [group1, group2]

    def tearDown(self) -> None:
        """Limpia los archivos generados durante la prueba para no ensuciar el directorio."""
        if os.path.exists(self.test_html_path):
            os.remove(self.test_html_path)
        if os.path.exists(self.test_pdf_path):
            os.remove(self.test_pdf_path)

    def test_export_to_html(self) -> None:
        """Valida que se genere correctamente el archivo HTML y contenga la información clave."""
        result = export_to_html(self.agrupados, self.test_html_path)
        
        self.assertTrue(result, "export_to_html debería retornar True al tener éxito.")
        self.assertTrue(os.path.exists(self.test_html_path), "El archivo HTML debería existir en disco.")
        
        # Verificar contenido básico dentro del HTML generado
        with open(self.test_html_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("NetLens - Reporte de Auditoría", content)
            self.assertIn("Falta X-Frame-Options", content)
            self.assertIn("api.example.com", content)
            self.assertIn("/api/users", content)

    def test_export_to_pdf(self) -> None:
        """Valida que se genere correctamente un documento PDF válido."""
        result = export_to_pdf(self.agrupados, self.test_pdf_path)
        
        self.assertTrue(result, "export_to_pdf debería retornar True al tener éxito.")
        self.assertTrue(os.path.exists(self.test_pdf_path), "El archivo PDF debería existir en disco.")
        
        # Verificar que el archivo PDF tiene un tamaño válido (es mayor a 0 bytes)
        file_size = os.path.getsize(self.test_pdf_path)
        self.assertGreater(file_size, 0, "El archivo PDF no debería estar vacío.")

if __name__ == "__main__":
    unittest.main()
