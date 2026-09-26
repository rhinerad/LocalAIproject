#!/usr/bin/env python3
"""Host, origin, content-type, and anti-forgery checks for local HTTP mutations."""
from __future__ import annotations

import io
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import server


def _headers(**fields: str) -> Message:
    message = Message()
    for key, value in fields.items():
        message[key] = value
    return message


def _handler(path: str, body: bytes, headers: Message, method: str = "POST") -> server.Handler:
    handler = server.Handler.__new__(server.Handler)
    handler.path = path
    handler.headers = headers
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.close_connection = False
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 9)
    return handler


def _trusted(body: bytes) -> Message:
    return _headers(**{
        "Host": f"127.0.0.1:{server.PORT}",
        "Origin": f"http://127.0.0.1:{server.PORT}",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "Cookie": f"la_csrf={server.SESSION_CSRF}",
        "X-CSRF-Token": server.SESSION_CSRF,
    })


class HttpMutationGuardTests(unittest.TestCase):
    def _post(self, headers: Message, body: bytes = b'{"action":"write_file","args":{}}'):
        handler = _handler("/api/action", body, headers)
        with patch.object(server.tools, "call", return_value="wrote") as call:
            handler.do_POST()
        raw = handler.wfile.getvalue().decode("utf-8", "replace")
        return raw, call

    def test_trusted_local_post_reaches_the_tool(self) -> None:
        body = b'{"action":"write_file","args":{"path":"x"}}'
        raw, call = self._post(_trusted(body), body)
        self.assertIn("200", raw.splitlines()[0])
        call.assert_called_once()

    def test_foreign_origin_is_rejected(self) -> None:
        body = b'{"action":"write_file","args":{}}'
        headers = _trusted(body)
        headers.replace_header("Origin", "https://untrusted.example")
        raw, call = self._post(headers, body)
        self.assertIn("403", raw)
        call.assert_not_called()

    def test_hostile_host_is_rejected(self) -> None:
        body = b'{"action":"write_file","args":{}}'
        headers = _trusted(body)
        headers.replace_header("Host", "untrusted.example")
        raw, call = self._post(headers, body)
        self.assertIn("403", raw)
        call.assert_not_called()

    def test_plain_content_type_is_rejected(self) -> None:
        body = b'{"action":"write_file","args":{}}'
        headers = _trusted(body)
        headers.replace_header("Content-Type", "text/plain")
        raw, call = self._post(headers, body)
        self.assertIn("415", raw)
        call.assert_not_called()

    def test_missing_csrf_is_rejected(self) -> None:
        body = b'{"action":"write_file","args":{}}'
        headers = _trusted(body)
        del headers["X-CSRF-Token"]
        raw, call = self._post(headers, body)
        self.assertIn("403", raw)
        call.assert_not_called()

    def test_approval_route_rejects_foreign_origin(self) -> None:
        body = b'{"id":"1","approve":true}'
        headers = _trusted(body)
        headers.replace_header("Origin", "https://untrusted.example")
        handler = _handler("/api/file_edit_gateway/decision", body, headers)
        with patch.object(server.file_edit_gate, "decide") as decide:
            handler.do_POST()
        decide.assert_not_called()

    def test_get_rejects_hostile_host(self) -> None:
        handler = _handler("/api/status", b"", _headers(**{"Host": "evil.example"}), method="GET")
        with patch.object(server, "app_status") as status:
            handler.do_GET()
        status.assert_not_called()
        self.assertIn("403", handler.wfile.getvalue().decode())


if __name__ == "__main__":
    unittest.main()
