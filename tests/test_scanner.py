"""
tests/test_scanner.py
---------------------
Suite de pruebas unitarias para el escáner pasivo (PassiveScanner).
Verifica la correcta detección de vulnerabilidades basadas en reglas estáticas
sobre el historial de peticiones.
"""

import unittest
from datetime import datetime

from proxy.history import RequestRecord
from logic.scanner import PassiveScanner


class TestPassiveScanner(unittest.TestCase):
    """
    Pruebas unitarias para la clase PassiveScanner.
    Simula objetos RequestRecord para validar la lógica de detección
    de cabeceras de seguridad, fugas de información y errores 500.
    """

    def setUp(self) -> None:
        """Inicializa la instancia del escáner antes de cada prueba."""
        self.scanner = PassiveScanner()
        # Mock de datos requeridos para instanciar RequestRecord
        self.base_kwargs = {
            "id": 1,
            "timestamp": datetime.now(),
            "method": "GET",
            "host": "example.com",
            "port": 443,
            "path": "/",
        }

    def test_no_vulnerabilities(self) -> None:
        """El escáner no debe retornar hallazgos si la petición es segura."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 200 OK",
            response_headers={
                "Strict-Transport-Security": "max-age=31536000",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'",
                "Server": "Apache",  # Sin versión exacta, no debe ser detectado
            }
        )
        
        findings = self.scanner.scan_history([record])
        self.assertEqual(findings, [])

    def test_missing_security_headers(self) -> None:
        """Debe detectar la falta explícita de CSP y X-Frame-Options."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 200 OK",
            response_headers={
                "Strict-Transport-Security": "max-age=31536000",
                "X-Content-Type-Options": "nosniff",
                # Omitimos deliberadamente CSP y X-Frame-Options
            }
        )

        findings = self.scanner.scan_history([record])
        
        # Deben haber exactamente 2 hallazgos
        self.assertEqual(len(findings), 2)
        
        titles = [f.title for f in findings]
        self.assertIn("Falta X-Frame-Options (Clickjacking)", titles)
        self.assertIn("Falta Content-Security-Policy (CSP)", titles)
        
        # Verificar que el request_id coincide
        for finding in findings:
            self.assertEqual(finding.request_id, 1)
            self.assertEqual(finding.severity, "Low")

    def test_information_leakage(self) -> None:
        """Debe detectar fuga de información si hay versiones específicas en Server o X-Powered-By."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 200 OK",
            response_headers={
                "Strict-Transport-Security": "max-age=31536000",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'",
                "Server": "Apache/2.4.41",
                "X-Powered-By": "PHP/8.1",
            }
        )

        findings = self.scanner.scan_history([record])
        
        # Ambos headers revelan versión
        self.assertEqual(len(findings), 2)
        
        titles = [f.title for f in findings]
        self.assertIn("Fuga de Información en Server", titles)
        self.assertIn("Fuga de Información en X-Powered-By", titles)
        
        for finding in findings:
            self.assertEqual(finding.severity, "Medium")

    def test_server_errors(self) -> None:
        """Debe detectar códigos de estado 500+ como errores del servidor."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 500 Internal Server Error",
            response_headers={
                "Strict-Transport-Security": "max-age=31536000",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'",
            }
        )

        findings = self.scanner.scan_history([record])
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].title, "Error del Servidor (Serie 500)")
        self.assertEqual(findings[0].severity, "Info")

    def test_empty_history_returns_empty_list(self) -> None:
        """Si el historial está vacío, debe retornar una lista vacía."""
        findings = self.scanner.scan_history([])
        self.assertEqual(findings, [])

    def test_critical_body_leak_rsa(self) -> None:
        """Debe detectar una fuga de llave privada RSA en el cuerpo de la respuesta."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 200 OK",
            response_headers={"Content-Type": "text/html; charset=utf-8"},
            response_body=b"<html><body>-----BEGIN RSA PRIVATE KEY-----<br>MIIEowIBAAKCAQEA...</body></html>"
        )
        
        findings = self.scanner.scan_history([record])
        
        # Filtramos para buscar el finding critico (por si hay otros de headers)
        critical_findings = [f for f in findings if f.severity == "Critical"]
        self.assertEqual(len(critical_findings), 1)
        self.assertEqual(critical_findings[0].title, "Fuga Crítica: Llave Privada Expuesta")

    def test_high_body_leak_db_error(self) -> None:
        """Debe detectar un error de base de datos SQL en el cuerpo (JSON)."""
        record = RequestRecord(
            **self.base_kwargs,
            response_status="HTTP/1.1 500 Internal Server Error",
            response_headers={"Content-Type": "application/json"},
            response_body=b'{"error": "You have an error in your SQL syntax near \\"\'admin\' AND 1=1\\" at line 1", "backend": "MySQL"}'
        )
        
        findings = self.scanner.scan_history([record])
        
        # Debe haber un finding alto
        high_findings = [f for f in findings if f.severity == "High"]
        self.assertEqual(len(high_findings), 1)
        self.assertEqual(high_findings[0].title, "Fuga de Información: Error de Base de Datos")

        # Como es un 500, tambien debe estar el hallazgo informativo
        info_findings = [f for f in findings if f.severity == "Info"]
        self.assertEqual(len(info_findings), 1)
        self.assertEqual(info_findings[0].title, "Error del Servidor (Serie 500)")

if __name__ == "__main__":
    unittest.main()
