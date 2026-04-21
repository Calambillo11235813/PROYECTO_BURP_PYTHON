"""Tests para logic.http_body (descompresión y render legible)."""

from __future__ import annotations

import gzip
import unittest
import zlib

import brotli

from logic.http_body import build_display_http_message


def _http_response(headers: list[str], body: bytes) -> bytes:
    head = "\r\n".join(["HTTP/1.1 200 OK", *headers]).encode("iso-8859-1")
    return head + b"\r\n\r\n" + body


class TestHttpBody(unittest.TestCase):
    def test_gzip_body_is_decompressed_and_rendered(self) -> None:
        payload = b'{"ok": true, "source": "gzip"}'
        compressed = gzip.compress(payload)
        raw = _http_response(
            [
                "Content-Type: application/json; charset=utf-8",
                "Content-Encoding: gzip",
            ],
            compressed,
        )

        display = build_display_http_message(raw)

        self.assertIn("Content-Encoding: gzip", display)
        self.assertIn('{"ok": true, "source": "gzip"}', display)

    def test_deflate_body_is_decompressed_and_rendered(self) -> None:
        payload = b"{\"event\": \"deflate\"}"
        compressed = zlib.compress(payload)
        raw = _http_response(
            [
                "Content-Type: application/json",
                "Content-Encoding: deflate",
            ],
            compressed,
        )

        display = build_display_http_message(raw)

        self.assertIn('{"event": "deflate"}', display)

    def test_brotli_body_is_decompressed_and_rendered(self) -> None:
        payload = b"<html><body>Brotli OK</body></html>"
        compressed = brotli.compress(payload)
        raw = _http_response(
            [
                "Content-Type: text/html; charset=utf-8",
                "Content-Encoding: br",
            ],
            compressed,
        )

        display = build_display_http_message(raw)

        self.assertIn("Brotli OK", display)

    def test_binary_payload_shows_placeholder(self) -> None:
        payload = b"\x89PNG\x00\x01\x02\x03\x04\x00\xff\xfe"
        raw = _http_response(["Content-Type: image/png"], payload)

        display = build_display_http_message(raw)

        self.assertIn("[Cuerpo Binario / No legible]", display)


if __name__ == "__main__":
    unittest.main(verbosity=2)
