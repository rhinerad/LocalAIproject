#!/usr/bin/env python3
"""Unit tests for mcp_client.py against a mocked stdio MCP subprocess.

No live ComfyUI, Node, or npx is required. The mock server is a Python
script that speaks Content-Length JSON-RPC on stdin/stdout.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mcp_client

MOCK_SERVER = r'''
import json, os, sys, time

def read_message():
    first = sys.stdin.buffer.read(1)
    if not first:
        return None
    if first == b"{":
        rest = b""
        while True:
            ch = sys.stdin.buffer.read(1)
            if not ch or ch == b"\n":
                break
            rest += ch
        return json.loads((first + rest).decode("utf-8"))
    header = first
    while not header.endswith(b"\r\n\r\n"):
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk
    length = None
    for line in header.decode("ascii", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    if length is None:
        raise SystemExit("missing Content-Length")
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))

def write_message(msg):
    body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(("Content-Length: %d\r\n\r\n" % len(body)).encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()

def tool_result(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return {"content": [{"type": "text", "text": text}], "isError": False}

calls = []
hold_s = float(os.environ.get("MOCK_MCP_HOLD_S", "0"))
sys.stderr.write("mock-mcp ready pid=%s\n" % os.getpid())
sys.stderr.flush()
while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "notifications/initialized":
        continue
    if method == "initialize":
        write_message({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-comfyui-mcp", "version": "test"},
            },
        })
        continue
    if method == "tools/list":
        write_message({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": [
                {"name": "get_system_stats", "description": "stats"},
                {"name": "generate_image", "description": "gen"},
                {"name": "restart_comfyui", "description": "proc"},
            ]},
        })
        continue
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        calls.append({"name": name, "arguments": arguments, "t": time.time()})
        if hold_s:
            time.sleep(hold_s)
        if name == "get_system_stats":
            payload = {
                "ok": True,
                "comfyui_path": os.environ.get("COMFYUI_PATH"),
                "comfyui_url": os.environ.get("COMFYUI_URL"),
                "comfyui_code_path": os.environ.get("COMFYUI_CODE_PATH"),
                "tool_mode": os.environ.get("COMFYUI_MCP_TOOL_MODE"),
                "pid": os.getpid(),
                "n_calls": len(calls),
            }
        elif name == "fail_tool":
            write_message({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": "boom"}], "isError": True},
            })
            continue
        elif name == "rpc_error":
            write_message({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": "no such tool"},
            })
            continue
        else:
            payload = {"ok": True, "tool": name, "arguments": arguments, "n_calls": len(calls)}
        write_message({"jsonrpc": "2.0", "id": req_id, "result": tool_result(payload)})
        continue
    write_message({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "unknown method %s" % method},
    })
'''


def _write_mock() -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix="_mock_mcp.py", delete=False, encoding="utf-8")
    handle.write(MOCK_SERVER)
    handle.close()
    return handle.name


class McpClientMockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_path = _write_mock()
        self.addCleanup(lambda: Path(self.mock_path).unlink(missing_ok=True))
        self.clients: list[mcp_client.McpClient] = []
        self.addCleanup(self._close_all)
        mcp_client.reset_client()

    def _close_all(self) -> None:
        for client in self.clients:
            client.close()
        mcp_client.reset_client()

    def _client(self, extra_env: dict | None = None, **kwargs) -> mcp_client.McpClient:
        env = mcp_client.child_env(extra_env)
        client = mcp_client.McpClient(
            argv=[sys.executable, "-u", self.mock_path],
            env=env,
            stall_s=kwargs.get("stall_s", 10),
            handshake_s=kwargs.get("handshake_s", 10),
        )
        self.clients.append(client)
        return client

    def test_child_env_sets_shared_comfyui_explicitly(self):
        env = mcp_client.child_env()
        self.assertEqual(env["COMFYUI_PATH"], mcp_client.COMFYUI_PATH)
        self.assertEqual(env["COMFYUI_URL"], mcp_client.COMFYUI_URL)
        self.assertEqual(env["COMFYUI_CODE_PATH"], mcp_client.COMFYUI_CODE_PATH)
        self.assertEqual(env["COMFYUI_MCP_TOOL_MODE"], "full")
        self.assertEqual(env["COMFYUI_PATH"], r"A:\Users\rhine\ComfyUI-Shared")
        self.assertEqual(env["COMFYUI_URL"], "http://127.0.0.1:8188")
        self.assertIn("COMFYUI_RESTART_COMMAND", env)
        self.assertIn("restart_comfy_rockernow.ps1", env["COMFYUI_RESTART_COMMAND"])
        self.assertEqual(env.get("COMFYUI_REMOTE_REBOOT_BUDGET_S"), "300")

    def test_initialize_and_system_stats_roundtrip(self):
        client = self._client()
        result = client.call("get_system_stats", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["comfyui_path"], mcp_client.COMFYUI_PATH)
        self.assertEqual(result["comfyui_url"], mcp_client.COMFYUI_URL)
        self.assertEqual(result["comfyui_code_path"], mcp_client.COMFYUI_CODE_PATH)
        self.assertEqual(result["tool_mode"], "full")
        self.assertEqual(client.pid, result["pid"])

    def test_keeps_same_child_across_calls(self):
        client = self._client()
        first = client.call("get_system_stats", {})
        second = client.call("get_system_stats", {})
        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(second["n_calls"], 2)

    def test_list_tools(self):
        client = self._client()
        names = [t["name"] for t in client.list_tools()]
        self.assertIn("get_system_stats", names)
        self.assertIn("generate_image", names)

    def test_lock_serializes_concurrent_calls(self):
        client = self._client({"MOCK_MCP_HOLD_S": "0.2"})
        client.call("get_system_stats", {})  # handshake + first call
        results = []
        errors = []

        def worker(tag):
            try:
                results.append(client.call("generate_image", {"action": "image", "tag": tag}))
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        start = time.monotonic()
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        elapsed = time.monotonic() - start
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2)
        # Two 0.2s holds under a lock cannot finish in ~0.2s.
        self.assertGreaterEqual(elapsed, 0.35)

    def test_tool_iserror_raises(self):
        client = self._client()
        with self.assertRaises(mcp_client.McpError) as ctx:
            client.call("fail_tool", {})
        self.assertIn("boom", str(ctx.exception))

    def test_rpc_error_raises(self):
        client = self._client()
        with self.assertRaises(mcp_client.McpError) as ctx:
            client.call("rpc_error", {})
        self.assertIn("no such tool", str(ctx.exception))

    def test_timeout(self):
        client = self._client({"MOCK_MCP_HOLD_S": "2"}, stall_s=1, handshake_s=10)
        with self.assertRaises(mcp_client.McpTimeout):
            client.call("generate_image", {"action": "image"})

    def test_captures_stderr(self):
        client = self._client()
        client.call("get_system_stats", {})
        self.assertIn("mock-mcp ready", client.stderr_tail())

    def test_singleton_reset(self):
        mcp_client.reset_client()
        original = mcp_client.McpClient
        created = []

        class Fake(original):
            def __init__(self, *a, **k):
                super().__init__(
                    argv=[sys.executable, "-u", self_path],
                    env=mcp_client.child_env(),
                    stall_s=10,
                    handshake_s=10,
                )
                created.append(self)

        self_path = self.mock_path
        mcp_client.McpClient = Fake  # type: ignore
        try:
            a = mcp_client.get_client()
            b = mcp_client.get_client()
            self.assertIs(a, b)
            mcp_client.reset_client()
            c = mcp_client.get_client()
            self.assertIsNot(a, c)
            self.assertEqual(len(created), 2)
        finally:
            mcp_client.McpClient = original  # type: ignore
            mcp_client.reset_client()

    def test_spawn_false_uninitialized_does_not_handshake(self):
        client = self._client()
        self.assertFalse(client.ready())
        with self.assertRaises(mcp_client.McpError) as ctx:
            client.call("get_system_stats", {}, spawn=False)
        self.assertIn("not started", str(ctx.exception).lower())
        self.assertIsNone(client.pid)

    def test_spawn_false_works_after_start(self):
        client = self._client()
        client.call("get_system_stats", {})
        self.assertTrue(client.ready())
        again = client.call("get_system_stats", {}, spawn=False, timeout=5)
        self.assertEqual(again["n_calls"], 2)

    def test_lock_timeout_raises_when_held(self):
        client = self._client({"MOCK_MCP_HOLD_S": "1"}, stall_s=5, handshake_s=10)
        client.call("get_system_stats", {})
        errors = []

        def holder():
            client.call("generate_image", {"action": "image"})

        t = threading.Thread(target=holder)
        t.start()
        time.sleep(0.05)
        try:
            with self.assertRaises(mcp_client.McpError) as ctx:
                client.call("get_system_stats", {}, lock_timeout=0.2, spawn=False)
            self.assertIn("lock busy", str(ctx.exception).lower())
        finally:
            t.join()
        self.assertFalse(errors)

    def test_module_spawn_false_without_singleton(self):
        mcp_client.reset_client()
        self.assertFalse(mcp_client.ready())
        with self.assertRaises(mcp_client.McpError) as ctx:
            mcp_client.call("get_system_stats", {}, spawn=False)
        self.assertIn("not started", str(ctx.exception).lower())
        self.assertFalse(mcp_client.ready())


if __name__ == "__main__":
    unittest.main()
