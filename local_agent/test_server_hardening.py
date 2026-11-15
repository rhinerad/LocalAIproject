#!/usr/bin/env python3
"""Audit 2026-11-02 server fixes: request parsing, /api/action allowlist,
one turn per conversation, render-watch locking, media streaming."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import file_edit_gate  # noqa: E402
import gpu_gate  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402


def _headers(**fields: str) -> Message:
    message = Message()
    for key, value in fields.items():
        message[key] = value
    return message


def _trusted(body: bytes, content_length: str | None = None) -> Message:
    return _headers(**{
        "Host": f"127.0.0.1:{server.PORT}",
        "Origin": f"http://127.0.0.1:{server.PORT}",
        "Content-Type": "application/json",
        "Content-Length": str(len(body)) if content_length is None else content_length,
        "Cookie": f"la_csrf={server.SESSION_CSRF}",
        "X-CSRF-Token": server.SESSION_CSRF,
    })


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


def _response(handler: server.Handler) -> tuple[int, dict[str, str], bytes]:
    raw = handler.wfile.getvalue()
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers, body


class LocalHostListTests(unittest.TestCase):
    def test_localhost_with_port_is_a_local_host(self) -> None:
        self.assertIn(f"localhost:{server.PORT}", server._LOCAL_HOSTS)
        self.assertNotIn("localhost:{PORT}", server._LOCAL_HOSTS)


class RequestParsingTests(unittest.TestCase):
    def _post(self, body: bytes, headers: Message, path: str = "/api/action"):
        handler = _handler(path, body, headers)
        with patch.object(server.tools, "call", return_value="{}") as call:
            handler.do_POST()
        status, _h, raw = _response(handler)
        return status, raw, call

    def test_non_numeric_content_length_is_400(self) -> None:
        body = b'{"action":"project_state"}'
        status, raw, call = self._post(body, _trusted(body, content_length="abc"))
        self.assertEqual(400, status)
        self.assertIn(b"Content-Length", raw)
        call.assert_not_called()

    def test_negative_content_length_is_400(self) -> None:
        body = b'{"action":"project_state"}'
        status, _raw, call = self._post(body, _trusted(body, content_length="-5"))
        self.assertEqual(400, status)
        call.assert_not_called()

    def test_oversized_body_is_413(self) -> None:
        body = b'{"action":"project_state","args":{"pad":"' + b"x" * 64 + b'"}}'
        with patch.object(server, "MAX_JSON_BYTES", 16):
            status, _raw, call = self._post(body, _trusted(body))
        self.assertEqual(413, status)
        call.assert_not_called()

    def test_non_object_json_is_400(self) -> None:
        body = b'[1, 2, 3]'
        status, raw, call = self._post(body, _trusted(body))
        self.assertEqual(400, status)
        self.assertIn(b"JSON object", raw)
        call.assert_not_called()


class ActionRouteAllowlistTests(unittest.TestCase):
    def _post(self, payload: dict):
        body = json.dumps(payload).encode()
        handler = _handler("/api/action", body, _trusted(body))
        with patch.object(server.tools, "call", return_value='{"ok": true}') as call:
            handler.do_POST()
        status, _h, raw = _response(handler)
        return status, raw, call

    def test_ui_never_posts_to_the_action_route(self) -> None:
        html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("/api/action", html)

    def test_unlisted_tool_is_403_and_never_dispatched(self) -> None:
        for name in ("write_file", "run_code", "comfy_generate", "", "list_tools"):
            status, raw, call = self._post({"action": name, "args": {"path": "x"}})
            self.assertEqual(403, status, name)
            self.assertIn(b"not allowed", raw)
            call.assert_not_called()

    def test_listed_tool_runs_with_an_explicit_desktop_context(self) -> None:
        status, raw, call = self._post({"action": "project_state", "args": {}})
        self.assertEqual(200, status)
        self.assertEqual({"result": '{"ok": true}'}, json.loads(raw))
        call.assert_called_once()
        context = call.call_args.kwargs.get("context")
        self.assertIsNotNone(context)
        self.assertEqual("desktop", context.source)
        self.assertFalse(context.remote)
        self.assertEqual("api_action", context.request_id)

    def test_non_object_args_is_400(self) -> None:
        status, _raw, call = self._post({"action": "project_state", "args": [1, 2]})
        self.assertEqual(400, status)
        call.assert_not_called()

    def test_allowlist_is_exactly_the_gui_dispatched_tools(self) -> None:
        self.assertEqual({"project_state", "stop_all_comfyui"}, set(server.ACTION_ROUTE_ALLOWLIST))


class TurnRequestValidationTests(unittest.TestCase):
    def test_validate_turn_request_shapes(self) -> None:
        ok = server.validate_turn_request
        self.assertIsNone(ok({"id": "c1", "message": "hi"}))
        self.assertIsNone(ok({"id": "c1", "message": None}))
        self.assertIsNone(ok({"message": "hi", "attachments": [
            {"kind": "text", "name": "a.txt", "content": "x"},
            {"kind": "image", "name": "a.png", "path": "/tmp/a.png", "size": 12},
            {"kind": "image", "name": "b.png", "path": "/tmp/b.png", "size": "12"},
        ]}))
        self.assertIsNotNone(ok([]))
        self.assertIsNotNone(ok({"id": 5}))
        self.assertIsNotNone(ok({"message": 123}))
        self.assertIsNotNone(ok({"message": ["x"]}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": {"kind": "text"}}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": ["text"]}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": [{"kind": "text", "content": 5}]}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": [{"kind": 1}]}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": [{"path": ["x"]}]}))
        self.assertIsNotNone(ok({"message": "hi", "attachments": [{"size": True}]}))

    def test_send_turn_writes_a_400_for_bad_shapes(self) -> None:
        for payload in ({"id": "c1", "message": 123},
                        {"id": "c1", "message": "x", "attachments": [{"content": 7}]},
                        {"id": ["c1"], "message": "x"}):
            captured: list[tuple[object, int]] = []
            handler = object.__new__(server.Handler)
            handler._json = lambda obj, code=200: captured.append((obj, code))
            with patch.object(server.store, "load", side_effect=AssertionError("store touched")), \
                 patch.object(agent, "answer", side_effect=AssertionError("answer ran")):
                handler._send_turn(payload)
            self.assertEqual(1, len(captured), payload)
            self.assertEqual(400, captured[0][1], payload)
            self.assertIn("error", captured[0][0])


class ConcurrentTurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        (root / "chats").mkdir()
        p = patch.object(store, "DIR", root / "chats")
        p.start()
        self.addCleanup(p.stop)
        gpu_gate.STATE_FILE = root / "gpu_gate.json"
        file_edit_gate.STATE_FILE = root / "file_edit_gate.json"
        os.environ["LOCAL_AGENT_TRACING"] = "0"
        with server._active_turns_lock:
            server._active_turns.clear()

    def _handler(self, captured: list):
        h = object.__new__(server.Handler)
        h.wfile = io.BytesIO()
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda: None
        h._json = lambda obj, code=200: captured.append((obj, code))
        return h

    def test_claim_and_release_semantics(self) -> None:
        self.assertTrue(server._claim_turn("c-a"))
        self.assertFalse(server._claim_turn("c-a"))
        self.assertTrue(server.turn_in_flight("c-a"))
        self.assertTrue(server._claim_turn("c-b"))
        server._release_turn("c-a")
        self.assertFalse(server.turn_in_flight("c-a"))
        self.assertTrue(server.turn_in_flight("c-b"))
        server._release_turn("c-b")
        server._release_turn("never-claimed")
        self.assertTrue(server._claim_turn("c-a"))
        server._release_turn("c-a")

    def test_second_turn_on_same_conversation_is_409_and_appends_nothing(self) -> None:
        conv = store.create("seed", model="huihui_ai/qwen3-abliterated:14b", workspace="general")
        cid = conv["id"]
        before = len(store.load(cid)["messages"])
        self.assertTrue(server._claim_turn(cid))
        try:
            captured: list = []
            h = self._handler(captured)
            with patch.object(agent, "answer", side_effect=AssertionError("second turn ran")):
                h._send_turn({"id": cid, "message": "hello again", "prefer": "auto"})
            self.assertEqual([(captured[0][0], 409)], captured)
            self.assertEqual("busy", captured[0][0]["status"])
            self.assertEqual(before, len(store.load(cid)["messages"]))
            # The refused request did not release the running turn's claim.
            self.assertTrue(server.turn_in_flight(cid))
        finally:
            server._release_turn(cid)

    def test_turn_holds_the_claim_while_running_and_releases_after(self) -> None:
        conv = store.create("seed", model="huihui_ai/qwen3-abliterated:14b", workspace="general")
        cid = conv["id"]
        seen: dict = {}

        def fake_answer(history, push, **kwargs):
            seen["in_flight"] = server.turn_in_flight(cid)
            return "done"

        captured: list = []
        h = self._handler(captured)
        with patch.object(agent, "answer", fake_answer):
            h._send_turn({"id": cid, "message": "hello", "prefer": "auto"})
        self.assertTrue(seen.get("in_flight"))
        self.assertFalse(server.turn_in_flight(cid))
        self.assertEqual([], captured)
        roles = [m["role"] for m in store.load(cid)["messages"]]
        self.assertEqual("assistant", roles[-1])
        # A fresh turn is admitted again once the first finished.
        self.assertTrue(server._claim_turn(cid))
        server._release_turn(cid)


class RenderWatchLockingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = patch.object(server, "RENDER_WATCH_PATH", Path(self._tmp.name) / "render_watch.json")
        p.start()
        self.addCleanup(p.stop)
        server._render_watch_checked_at = 0.0
        with server._active_turns_lock:
            server._active_turns.clear()
        server._save_render_watches([{"id": "w1", "cid": "c1", "kind": "comfy",
                                      "label": "prompt p1", "prompt_id": "p1",
                                      "status": "running", "started_at": 1.0}])

    def test_check_runs_with_the_watch_lock_free_and_merges_under_it(self) -> None:
        observed: dict = {}
        arts = [{"kind": "image", "status": "ready", "filename": "a.png", "root": "shared_output",
                 "subfolder": "", "sha256": "", "bytes": 1}]

        def fake_check(watch, now):
            free = server._render_watch_lock.acquire(blocking=False)
            observed["lock_free_during_check"] = free
            if free:
                # A turn registering a new watch mid-check must not block or be lost.
                watches = server._load_render_watches()
                watches.append({"id": "w2", "cid": "c2", "kind": "comfy", "label": "prompt p2",
                                "prompt_id": "p2", "status": "running", "started_at": 2.0})
                server._save_render_watches(watches)
                server._render_watch_lock.release()
            return "complete", arts, ""

        with patch.object(server, "_check_render_watch", side_effect=fake_check) as check, \
             patch.object(server, "_attach_late_artifacts", return_value=(arts, "Title")):
            result = server.poll_render_watches(force=True)
        check.assert_called_once()
        self.assertTrue(observed.get("lock_free_during_check"))
        by_id = {w["id"]: w for w in result["watches"]}
        self.assertEqual("complete", by_id["w1"]["status"])
        self.assertEqual(arts, by_id["w1"]["artifacts"])
        self.assertEqual("Title", by_id["w1"]["title"])
        self.assertEqual("running", by_id["w2"]["status"])
        saved = {w["id"]: w for w in json.loads(server.RENDER_WATCH_PATH.read_text())}
        self.assertEqual("complete", saved["w1"]["status"])
        self.assertIn("w2", saved)

    def test_busy_chat_watch_is_not_checked(self) -> None:
        self.assertTrue(server._claim_turn("c1"))
        try:
            with patch.object(server, "_check_render_watch") as check:
                result = server.poll_render_watches(force=True)
            check.assert_not_called()
        finally:
            server._release_turn("c1")
        self.assertEqual("running", result["watches"][0]["status"])


class MediaStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "clip.mp4"
        block = bytes(range(256)) * 4096  # 1 MiB of a known pattern
        self.data = block + block + block[: 512 * 1024 + 7]  # 2.5 MiB + 7 bytes
        self.path.write_bytes(self.data)

    def _get(self, range_header: str | None = None) -> server.Handler:
        headers = _headers(Host=f"127.0.0.1:{server.PORT}")
        if range_header is not None:
            headers["Range"] = range_header
        handler = _handler("/api/generated_media", b"", headers, method="GET")
        handler._send_file(self.path, "video/mp4")
        return handler

    def test_full_file_is_streamed_with_length_and_accept_ranges(self) -> None:
        status, headers, body = _response(self._get())
        self.assertEqual(200, status)
        self.assertEqual(str(len(self.data)), headers["content-length"])
        self.assertEqual("bytes", headers["accept-ranges"])
        self.assertEqual("video/mp4", headers["content-type"])
        self.assertEqual(self.data, body)

    def test_single_range_is_206_with_content_range(self) -> None:
        first, last = 1024 * 1024 - 3, 1024 * 1024 + 10
        status, headers, body = _response(self._get(f"bytes={first}-{last}"))
        self.assertEqual(206, status)
        self.assertEqual(f"bytes {first}-{last}/{len(self.data)}", headers["content-range"])
        self.assertEqual(str(last - first + 1), headers["content-length"])
        self.assertEqual(self.data[first:last + 1], body)

    def test_open_ended_and_suffix_ranges(self) -> None:
        size = len(self.data)
        status, headers, body = _response(self._get(f"bytes={size - 5}-"))
        self.assertEqual(206, status)
        self.assertEqual(self.data[-5:], body)
        status, headers, body = _response(self._get("bytes=-9"))
        self.assertEqual(206, status)
        self.assertEqual(f"bytes {size - 9}-{size - 1}/{size}", headers["content-range"])
        self.assertEqual(self.data[-9:], body)

    def test_unsatisfiable_range_is_416(self) -> None:
        status, headers, body = _response(self._get(f"bytes={len(self.data)}-"))
        self.assertEqual(416, status)
        self.assertEqual(f"bytes */{len(self.data)}", headers["content-range"])
        self.assertEqual(b"", body)

    def test_multi_range_and_garbage_fall_back_to_full_file(self) -> None:
        for header in ("bytes=0-1,5-6", "items=0-1", "bytes=a-b", "bytes=-", "bytes="):
            status, _headers, body = _response(self._get(header))
            self.assertEqual(200, status, header)
            self.assertEqual(self.data, body, header)

    def test_parse_byte_range(self) -> None:
        parse = server.parse_byte_range
        self.assertIsNone(parse(None, 100))
        self.assertIsNone(parse("", 100))
        self.assertEqual((0, 9), parse("bytes=0-9", 100))
        self.assertEqual((90, 99), parse("bytes=90-500", 100))
        self.assertEqual((40, 99), parse("bytes=40-", 100))
        self.assertEqual((95, 99), parse("bytes=-5", 100))
        self.assertEqual((0, 99), parse("bytes=-500", 100))
        for bad in ("bytes=100-", "bytes=5-2", "bytes=-0"):
            with self.assertRaises(ValueError, msg=bad):
                parse(bad, 100)
        with self.assertRaises(ValueError):
            parse("bytes=0-1", 0)

    def test_generated_media_route_streams_through_send_file(self) -> None:
        headers = _headers(Host=f"127.0.0.1:{server.PORT}", Range="bytes=0-3")
        handler = _handler("/api/generated_media?root=shared_output&filename=clip.mp4",
                           b"", headers, method="GET")
        with patch.object(server, "generated_media_file",
                          return_value=(self.path, "video/mp4", None, 200)):
            handler.do_GET()
        status, headers_out, body = _response(handler)
        self.assertEqual(206, status)
        self.assertEqual(self.data[:4], body)
        self.assertEqual("bytes", headers_out["accept-ranges"])

    def test_generated_media_route_still_returns_json_errors(self) -> None:
        headers = _headers(Host=f"127.0.0.1:{server.PORT}")
        handler = _handler("/api/generated_media?root=shared_output&filename=nope.mp4",
                           b"", headers, method="GET")
        with patch.object(server, "generated_media_file",
                          return_value=(None, "application/json",
                                        {"error": "file missing", "status": "missing"}, 404)):
            handler.do_GET()
        status, _h, body = _response(handler)
        self.assertEqual(404, status)
        self.assertEqual("missing", json.loads(body)["status"])

    def test_generated_media_payload_keeps_the_bytes_contract(self) -> None:
        with patch.object(server, "generated_media_file",
                          return_value=(self.path, "video/mp4", None, 200)):
            body, code, ctype = server.generated_media_payload("shared_output", "", "clip.mp4")
        self.assertEqual((200, "video/mp4"), (code, ctype))
        self.assertEqual(self.data, body)


class Sha256CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        with server._sha256_cache_lock:
            server._SHA256_CACHE.clear()

    def test_digest_is_cached_per_path_mtime_size(self) -> None:
        path = Path(self._tmp.name) / "a.bin"
        path.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(expected, server.file_sha256(path))
        key = server._sha256_cache_key(path)
        self.assertIn(key, server._SHA256_CACHE)
        with server._sha256_cache_lock:
            server._SHA256_CACHE[key] = "cached-marker"
        self.assertEqual("cached-marker", server.file_sha256(path))
        # A rewrite with a different size invalidates the key.
        path.write_bytes(b"hello world, changed")
        self.assertEqual(hashlib.sha256(b"hello world, changed").hexdigest(),
                         server.file_sha256(path))

    def test_cache_is_bounded(self) -> None:
        with patch.object(server, "_SHA256_CACHE_LIMIT", 3):
            for i in range(6):
                path = Path(self._tmp.name) / f"f{i}.bin"
                path.write_bytes(bytes([i]) * (i + 1))
                server.file_sha256(path)
        self.assertLessEqual(len(server._SHA256_CACHE), 3)


if __name__ == "__main__":
    unittest.main()
