"""
test_proxy.py
-------------
Tests unitarios para el módulo ProxyServer.
Verifica el parseo de peticiones HTTP sin levantar un servidor real.

Ejecutar:
    python -m pytest test_proxy.py -v
    ó
    python test_proxy.py
"""

import unittest
from proxy.proxy_server import ProxyServer


class TestParseRequest(unittest.TestCase):
    """Pruebas sobre _parse_request()"""

    def setUp(self):
        # Instanciamos el proxy sin llamar a start()
        self.proxy = ProxyServer()

    # ── GET simple ──────────────────────────────
    def test_parse_get_request(self):
        raw = (
            b"GET http://example.com/index.html HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"User-Agent: TestClient/1.0\r\n"
            b"\r\n"
        )
        result = self.proxy._parse_request(raw)
        self.assertIsNotNone(result)
        method, host, port, path, headers, body = result
        self.assertEqual(method, "GET")
        self.assertEqual(host, "example.com")
        self.assertEqual(port, 80)
        self.assertEqual(path, "/index.html")

    # ── Puerto explícito en la URL ────────────────
    def test_parse_get_with_custom_port(self):
        raw = (
            b"GET http://localhost:3000/api/users HTTP/1.1\r\n"
            b"Host: localhost:3000\r\n"
            b"\r\n"
        )
        result = self.proxy._parse_request(raw)
        self.assertIsNotNone(result)
        _, host, port, path, _, _ = result
        self.assertEqual(host, "localhost")
        self.assertEqual(port, 3000)
        self.assertEqual(path, "/api/users")

    # ── CONNECT (HTTPS tunnel) ───────────────────
    def test_parse_connect_request(self):
        raw = (
            b"CONNECT github.com:443 HTTP/1.1\r\n"
            b"Host: github.com:443\r\n"
            b"\r\n"
        )
        result = self.proxy._parse_request(raw)
        self.assertIsNotNone(result)
        method, host, port, _, _, _ = result
        self.assertEqual(method, "CONNECT")
        self.assertEqual(host, "github.com")
        self.assertEqual(port, 443)

    # ── POST con cuerpo ──────────────────────────
    def test_parse_post_with_body(self):
        body_content = b"username=admin&password=secret"
        raw = (
            b"POST http://example.com/login HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Content-Length: 30\r\n"
            b"\r\n" + body_content
        )
        result = self.proxy._parse_request(raw)
        self.assertIsNotNone(result)
        method, host, port, path, headers, body = result
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/login")
        self.assertIn("Content-Type", headers)
        self.assertEqual(body, body_content)

    # ── Petición malformada ──────────────────────
    def test_parse_empty_request_returns_none(self):
        result = self.proxy._parse_request(b"")
        self.assertIsNone(result)

    # ── Cabeceras parseadas correctamente ────────
    def test_headers_parsed_as_dict(self):
        raw = (
            b"GET http://api.test.com/ HTTP/1.1\r\n"
            b"Host: api.test.com\r\n"
            b"Authorization: Bearer mytoken123\r\n"
            b"Accept: application/json\r\n"
            b"\r\n"
        )
        result = self.proxy._parse_request(raw)
        self.assertIsNotNone(result)
        _, _, _, _, headers, _ = result
        self.assertEqual(headers.get("Authorization"), "Bearer mytoken123")
        self.assertEqual(headers.get("Accept"), "application/json")


class TestProxyInit(unittest.TestCase):
    """Pruebas de inicialización del ProxyServer"""

    def test_default_host_port(self):
        proxy = ProxyServer()
        self.assertEqual(proxy.host, "127.0.0.1")
        self.assertEqual(proxy.port, 8080)

    def test_custom_host_port(self):
        proxy = ProxyServer(host="0.0.0.0", port=9090)
        self.assertEqual(proxy.host, "0.0.0.0")
        self.assertEqual(proxy.port, 9090)

    def test_initial_request_count(self):
        proxy = ProxyServer()
        self.assertEqual(proxy._request_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
