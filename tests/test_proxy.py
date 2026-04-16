"""
test_proxy.py
-------------
Tests unitarios para ProxyServer, History (CU-03) e InterceptController (CU-04).
Ejecutar:
    python -m pytest test_proxy.py -v
    ó
    python test_proxy.py
"""

import os
import csv
import tempfile
import unittest
from datetime import datetime

from proxy.proxy_server import ProxyServer
from proxy.history import History, RequestRecord
from proxy.handler import InterceptController, PendingRequest
from logic.parser import parse_request, ParsedRequest


# ─────────────────────────────────────────────────────────────
#  Helper: construye un RequestRecord de prueba
# ─────────────────────────────────────────────────────────────
def make_record(
    req_id=1,
    method="GET",
    host="example.com",
    port=80,
    path="/index.html",
    response_status="HTTP/1.1 200 OK",
    duration_ms=42.0,
    body=b"",
    client_ip="127.0.0.1",
) -> RequestRecord:
    return RequestRecord(
        id=req_id,
        timestamp=datetime(2026, 4, 16, 10, 0, 0),
        method=method,
        host=host,
        port=port,
        path=path,
        response_status=response_status,
        duration_ms=duration_ms,
        body=body,
        client_ip=client_ip,
    )


class TestParseRequest(unittest.TestCase):
    """Pruebas sobre logic.parser.parse_request() — trasladado desde proxy_server."""

    # ── GET simple ────────────────────────────────────────
    def test_parse_get_request(self):
        raw = (
            b"GET http://example.com/index.html HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"User-Agent: TestClient/1.0\r\n"
            b"\r\n"
        )
        result = parse_request(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.method, "GET")
        self.assertEqual(result.host,   "example.com")
        self.assertEqual(result.port,   80)
        self.assertEqual(result.path,   "/index.html")

    # ── Puerto explícito en la URL ───────────────────────────
    def test_parse_get_with_custom_port(self):
        raw = (
            b"GET http://localhost:3000/api/users HTTP/1.1\r\n"
            b"Host: localhost:3000\r\n"
            b"\r\n"
        )
        result = parse_request(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.host, "localhost")
        self.assertEqual(result.port, 3000)
        self.assertEqual(result.path, "/api/users")

    # ── CONNECT (HTTPS tunnel) ──────────────────────────────
    def test_parse_connect_request(self):
        raw = (
            b"CONNECT github.com:443 HTTP/1.1\r\n"
            b"Host: github.com:443\r\n"
            b"\r\n"
        )
        result = parse_request(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.method, "CONNECT")
        self.assertEqual(result.host,   "github.com")
        self.assertEqual(result.port,   443)

    # ── POST con cuerpo ────────────────────────────────────
    def test_parse_post_with_body(self):
        body_content = b"username=admin&password=secret"
        raw = (
            b"POST http://example.com/login HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Content-Length: 30\r\n"
            b"\r\n" + body_content
        )
        result = parse_request(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.method, "POST")
        self.assertEqual(result.path,   "/login")
        self.assertIn("Content-Type", result.headers)
        self.assertEqual(result.body, body_content)

    # ── Petición malformada ─────────────────────────────────
    def test_parse_empty_request_returns_none(self):
        self.assertIsNone(parse_request(b""))

    # ── Cabeceras parseadas correctamente ─────────────────────
    def test_headers_parsed_as_dict(self):
        raw = (
            b"GET http://api.test.com/ HTTP/1.1\r\n"
            b"Host: api.test.com\r\n"
            b"Authorization: Bearer mytoken123\r\n"
            b"Accept: application/json\r\n"
            b"\r\n"
        )
        result = parse_request(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.headers.get("Authorization"), "Bearer mytoken123")
        self.assertEqual(result.headers.get("Accept"),        "application/json")


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

    def test_proxy_has_history(self):
        proxy = ProxyServer()
        self.assertIsInstance(proxy.history, History)

    def test_proxy_has_intercept_controller(self):
        # CU-04: el ProxyServer debe exponer un InterceptController
        proxy = ProxyServer()
        self.assertIsInstance(proxy.intercept, InterceptController)
        self.assertFalse(proxy.intercept.intercept_enabled)


# ─────────────────────────────────────────────────────────────
#  CU-03: Tests de RequestRecord
# ─────────────────────────────────────────────────────────────
class TestRequestRecord(unittest.TestCase):
    """Pruebas sobre el dataclass RequestRecord."""

    def test_status_code_parsed_correctly(self):
        r = make_record(response_status="HTTP/1.1 404 Not Found")
        self.assertEqual(r.status_code, 404)

    def test_status_code_200(self):
        r = make_record(response_status="HTTP/1.1 200 OK")
        self.assertEqual(r.status_code, 200)

    def test_status_code_tunnel(self):
        # CONNECT no tiene status HTTP convencional
        r = make_record(method="CONNECT", response_status="TUNNEL")
        self.assertEqual(r.status_code, 0)

    def test_url_http(self):
        r = make_record(host="example.com", port=80, path="/page")
        self.assertEqual(r.url, "http://example.com/page")

    def test_url_https(self):
        r = make_record(host="secure.com", port=443, path="/login")
        self.assertEqual(r.url, "https://secure.com/login")

    def test_url_custom_port(self):
        r = make_record(host="localhost", port=3000, path="/api")
        self.assertEqual(r.url, "http://localhost:3000/api")

    def test_url_connect(self):
        r = make_record(method="CONNECT", host="github.com", port=443, path="github.com:443")
        self.assertEqual(r.url, "github.com:443")

    def test_to_dict_keys(self):
        r = make_record()
        d = r.to_dict()
        expected_keys = {
            "id", "timestamp", "method", "host", "port",
            "path", "url", "status_code", "response_status",
            "duration_ms", "body_size_bytes", "client_ip",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_values(self):
        r = make_record(req_id=7, method="POST", duration_ms=123.45)
        d = r.to_dict()
        self.assertEqual(d["id"], 7)
        self.assertEqual(d["method"], "POST")
        self.assertAlmostEqual(d["duration_ms"], 123.45, places=2)

    def test_str_representation(self):
        r = make_record(req_id=3, method="GET")
        s = str(r)
        self.assertIn("#0003", s)
        self.assertIn("GET", s)


# ─────────────────────────────────────────────────────────────
#  CU-03: Tests del historial (History)
# ─────────────────────────────────────────────────────────────
class TestHistory(unittest.TestCase):
    """Pruebas sobre la clase History."""

    def setUp(self):
        self.history = History()

    # ── Agregar y contar ─────────────────────────────────────
    def test_initially_empty(self):
        self.assertEqual(len(self.history), 0)

    def test_add_increases_count(self):
        self.history.add(make_record(req_id=1))
        self.history.add(make_record(req_id=2))
        self.assertEqual(len(self.history), 2)

    def test_all_returns_copy(self):
        self.history.add(make_record(req_id=1))
        records = self.history.all()
        records.clear()                           # mutamos la copia
        self.assertEqual(len(self.history), 1)   # el original no debe cambiar

    def test_get_by_id_found(self):
        self.history.add(make_record(req_id=42, method="DELETE"))
        r = self.history.get_by_id(42)
        self.assertIsNotNone(r)
        self.assertEqual(r.method, "DELETE")

    def test_get_by_id_not_found(self):
        self.assertIsNone(self.history.get_by_id(999))

    # ── Filtro por método ────────────────────────────────────
    def test_filter_by_method(self):
        self.history.add(make_record(req_id=1, method="GET"))
        self.history.add(make_record(req_id=2, method="POST"))
        self.history.add(make_record(req_id=3, method="GET"))
        results = self.history.filter(method="GET")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.method == "GET" for r in results))

    def test_filter_method_case_insensitive(self):
        self.history.add(make_record(req_id=1, method="POST"))
        results = self.history.filter(method="post")
        self.assertEqual(len(results), 1)

    # ── Filtro por host ──────────────────────────────────────
    def test_filter_by_host_substring(self):
        self.history.add(make_record(req_id=1, host="www.google.com"))
        self.history.add(make_record(req_id=2, host="www.bing.com"))
        self.history.add(make_record(req_id=3, host="api.google.com"))
        results = self.history.filter(host="google")
        self.assertEqual(len(results), 2)

    # ── Filtro por código de estado ──────────────────────────
    def test_filter_by_status_code(self):
        self.history.add(make_record(req_id=1, response_status="HTTP/1.1 200 OK"))
        self.history.add(make_record(req_id=2, response_status="HTTP/1.1 404 Not Found"))
        self.history.add(make_record(req_id=3, response_status="HTTP/1.1 200 OK"))
        results = self.history.filter(status_code=200)
        self.assertEqual(len(results), 2)

    def test_filter_by_status_range(self):
        self.history.add(make_record(req_id=1, response_status="HTTP/1.1 200 OK"))
        self.history.add(make_record(req_id=2, response_status="HTTP/1.1 301 Moved"))
        self.history.add(make_record(req_id=3, response_status="HTTP/1.1 500 Error"))
        results = self.history.filter(min_status=300, max_status=399)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status_code, 301)

    # ── Filtros combinados ───────────────────────────────────
    def test_filter_combined_method_and_host(self):
        self.history.add(make_record(req_id=1, method="POST", host="api.target.com"))
        self.history.add(make_record(req_id=2, method="GET",  host="api.target.com"))
        self.history.add(make_record(req_id=3, method="POST", host="www.other.com"))
        results = self.history.filter(method="POST", host="target")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 1)

    def test_filter_no_match_returns_empty(self):
        self.history.add(make_record(req_id=1, method="GET"))
        results = self.history.filter(method="DELETE")
        self.assertEqual(len(results), 0)

    # ── Exportar TXT ─────────────────────────────────────────
    def test_export_txt_creates_file(self):
        self.history.add(make_record(req_id=1))
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_txt(os.path.join(tmp, "historial.txt"))
            self.assertTrue(os.path.exists(out))

    def test_export_txt_contains_data(self):
        self.history.add(make_record(req_id=5, host="test.com", method="POST"))
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_txt(os.path.join(tmp, "out.txt"))
            content = open(out, encoding="utf-8").read()
            self.assertIn("test.com", content)
            self.assertIn("POST", content)

    # ── Exportar CSV ─────────────────────────────────────────
    def test_export_csv_creates_file(self):
        self.history.add(make_record(req_id=1))
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_csv(os.path.join(tmp, "historial.csv"))
            self.assertTrue(os.path.exists(out))

    def test_export_csv_has_correct_columns(self):
        self.history.add(make_record(req_id=1))
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_csv(os.path.join(tmp, "out.csv"))
            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                cols = reader.fieldnames
            self.assertIn("method", cols)
            self.assertIn("status_code", cols)
            self.assertIn("duration_ms", cols)
            self.assertIn("host", cols)

    def test_export_csv_values(self):
        self.history.add(make_record(req_id=99, method="PUT", host="csv.test.com"))
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_csv(os.path.join(tmp, "out.csv"))
            with open(out, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "PUT")
        self.assertEqual(rows[0]["host"], "csv.test.com")

    def test_export_filtered_subset(self):
        """Exportar solo registros filtrados (no todo el historial)."""
        self.history.add(make_record(req_id=1, method="GET"))
        self.history.add(make_record(req_id=2, method="POST"))
        subset = self.history.filter(method="POST")
        with tempfile.TemporaryDirectory() as tmp:
            out = self.history.export_csv(os.path.join(tmp, "out.csv"), records=subset)
            with open(out, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "POST")

    # ── Limpiar ──────────────────────────────────────────────
    def test_clear_empties_history(self):
        self.history.add(make_record(req_id=1))
        self.history.add(make_record(req_id=2))
        self.history.clear()
        self.assertEqual(len(self.history), 0)

    # ── Proxy integra History ────────────────────────────────
    def test_proxy_has_history_attribute(self):
        proxy = ProxyServer()
        self.assertIsInstance(proxy.history, History)
        self.assertEqual(len(proxy.history), 0)



# ─────────────────────────────────────────────────────────────
class TestInterceptController(unittest.TestCase):
    """CU-04: Pruebas sobre InterceptController y PendingRequest."""

    def setUp(self):
        self.ic = InterceptController()

    # ── Estado inicial ────────────────────────────────────
    def test_initially_disabled(self):
        self.assertFalse(self.ic.intercept_enabled)

    def test_no_pending_initially(self):
        self.assertEqual(self.ic.pending_count, 0)
        self.assertIsNone(self.ic.next_pending())

    # ── enable() / disable() ────────────────────────────
    def test_enable_sets_flag(self):
        self.ic.enable()
        self.assertTrue(self.ic.intercept_enabled)

    def test_disable_clears_flag(self):
        self.ic.enable()
        self.ic.disable()
        self.assertFalse(self.ic.intercept_enabled)

    # ── PendingRequest.forward() ──────────────────────────
    def test_pending_forward_original(self):
        """forward() sin args devuelve la petición original."""
        raw    = b"GET http://test.com/ HTTP/1.1\r\n\r\n"
        parsed = parse_request(raw)
        pending = self.ic.intercept(1, raw, parsed)
        pending.forward()
        decision, final = pending.wait(timeout=1.0)
        self.assertEqual(decision, "forward")
        self.assertEqual(final, raw)

    def test_pending_forward_modified(self):
        """forward(modified) devuelve la petición modificada."""
        raw      = b"GET http://test.com/ HTTP/1.1\r\n\r\n"
        modified = b"GET http://test.com/hacked HTTP/1.1\r\n\r\n"
        parsed   = parse_request(raw)
        pending  = self.ic.intercept(1, raw, parsed)
        pending.forward(modified)
        decision, final = pending.wait(timeout=1.0)
        self.assertEqual(decision, "forward")
        self.assertEqual(final, modified)

    # ── PendingRequest.drop() ────────────────────────────
    def test_pending_drop(self):
        """drop() resuelve con 'drop'."""
        raw    = b"GET http://target.com/ HTTP/1.1\r\n\r\n"
        parsed = parse_request(raw)
        pending = self.ic.intercept(1, raw, parsed)
        pending.drop()
        decision, _ = pending.wait(timeout=1.0)
        self.assertEqual(decision, "drop")

    # ── next_pending() ─────────────────────────────────
    def test_next_pending_returns_request(self):
        """next_pending() retorna el PendingRequest encolado."""
        raw    = b"POST http://api.test.com/login HTTP/1.1\r\n\r\n"
        parsed = parse_request(raw)
        self.ic.intercept(42, raw, parsed)
        pend = self.ic.next_pending()
        self.assertIsNotNone(pend)
        self.assertEqual(pend.id, 42)
        self.assertEqual(pend.raw, raw)

    def test_pending_count_increments(self):
        raw    = b"GET http://count.test/ HTTP/1.1\r\n\r\n"
        parsed = parse_request(raw)
        self.ic.intercept(1, raw, parsed)
        self.ic.intercept(2, raw, parsed)
        self.assertEqual(self.ic.pending_count, 2)

    # ── Timeout ───────────────────────────────────────
    def test_pending_timeout_returns_original(self):
        """Si nadie resuelve la petición, wait() retorna ('timeout', raw)."""
        raw    = b"GET http://slow.com/ HTTP/1.1\r\n\r\n"
        parsed = parse_request(raw)
        pending = self.ic.intercept(99, raw, parsed)
        # timeout muy corto (0.1s) para que el test no tarde
        decision, final = pending.wait(timeout=0.1)
        self.assertEqual(decision, "timeout")
        self.assertEqual(final, raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
