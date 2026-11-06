#!/usr/bin/env python3
"""Minimal synchronous MCP stdio client for the comfyui-mcp server.

This is not a general-purpose MCP SDK. It exists to spawn
``npx -y comfyui-mcp`` once, keep that child alive, and serialize
JSON-RPC request/response on the same stdin/stdout pipes so
ThreadPoolExecutor tool calls cannot interleave.

Child environment always sets COMFYUI_PATH / COMFYUI_URL (and the
split-install COMFYUI_CODE_PATH) to this machine's shared ComfyUI
tree. comfyui-mcp's own auto-detection is never the source of truth.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("local_agent.mcp_client")

# Data/base root (models, input, output, Equal Shares evidence).
COMFYUI_PATH = os.environ.get(
    "EQUAL_SHARES_COMFYUI_PATH",
    r"A:\Users\rhine\ComfyUI-Shared",
)
# Split install: checkout that actually contains main.py / .venv.
COMFYUI_CODE_PATH = os.environ.get(
    "EQUAL_SHARES_COMFYUI_CODE_PATH",
    r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI",
)
COMFYUI_URL = os.environ.get("EQUAL_SHARES_COMFYUI_URL", "http://127.0.0.1:8188")

# Match long ComfyUI generation; do not impose a tighter ceiling than a
# legitimate render. Override with COMFYUI_MCP_STALL_S (seconds).
DEFAULT_STALL_S = int(os.environ.get("COMFYUI_MCP_STALL_S", "1800"))
HANDSHAKE_TIMEOUT_S = int(os.environ.get("COMFYUI_MCP_HANDSHAKE_S", "120"))
PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "local_agent"
CLIENT_VERSION = "1.0"

_HEADER_SEP = b"\r\n\r\n"
_MAX_STDERR_LINES = 200


class McpError(RuntimeError):
    """The MCP child failed, returned a JSON-RPC error, or a tool error."""


class McpTimeout(McpError):
    """A request exceeded its stall timeout."""


_READY_MARKERS = (
    "comfyui mcp server running on stdio",
    "mock-mcp ready",
)


def default_argv() -> list[str]:
    """Command used to spawn comfyui-mcp. Tests inject their own argv."""
    node = shutil.which("node")
    npx = shutil.which("npx")
    if not npx and not node:
        raise McpError(
            "npx/node not found on PATH. Node.js >= 22 is required to run comfyui-mcp."
        )
    # Prefer `node npx-cli.js` on Windows so stdin/stdout are real pipes to
    # Node. `npx.cmd` via cmd.exe is what dropped the initialize handshake
    # on the first live spawn (server came up; RPC never arrived).
    if node:
        npx_cli = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
        if npx_cli.is_file():
            return [node, str(npx_cli), "-y", "comfyui-mcp"]
    if not npx:
        raise McpError(
            "npx not found on PATH. Node.js >= 22 is required to run comfyui-mcp."
        )
    if sys.platform == "win32" and npx.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", npx, "-y", "comfyui-mcp"]
    return [npx, "-y", "comfyui-mcp"]


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Parent env plus explicit ComfyUI targeting. Extra overrides last."""
    env = os.environ.copy()
    env["COMFYUI_PATH"] = COMFYUI_PATH
    env["COMFYUI_URL"] = COMFYUI_URL
    env["COMFYUI_HOST"] = "127.0.0.1"
    env["COMFYUI_PORT"] = "8188"
    env["COMFYUI_CODE_PATH"] = COMFYUI_CODE_PATH
    # Our wrappers call named tools (generate_image, …), not compact meta-tools.
    env["COMFYUI_MCP_TOOL_MODE"] = "full"
    # The stdio child must not self-update/restart under us.
    env["COMFYUI_MCP_AUTO_UPDATE_DISABLE"] = "1"
    # Rockernow is launched by start_comfy_rockernow.bat with Desktop
    # --extra-model-paths-config. comfyui-mcp then classifies it as Desktop
    # and refuses kill+relaunch (parent identity unreadable). The documented
    # recovery is COMFYUI_RESTART_COMMAND — an opaque cycle of the one
    # Rockernow listener. Override with EQUAL_SHARES_COMFYUI_RESTART_COMMAND.
    restart_cmd = os.environ.get("EQUAL_SHARES_COMFYUI_RESTART_COMMAND", "").strip()
    if not restart_cmd:
        restart_ps1 = Path(r"A:\Users\rhine\.grok\long-running-background-tasks\restart_comfy_rockernow.ps1")
        if restart_ps1.is_file():
            restart_cmd = (
                f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{restart_ps1}"'
            )
    if restart_cmd:
        env["COMFYUI_RESTART_COMMAND"] = restart_cmd
    # Rockernow cold start after a cycle is slower than MCP's 120s default
    # probe budget (live 2026-09-04: PID changed, /system_stats healthy after
    # ~130s). Without this, restart_comfyui returns startup:unconfirmed even
    # though the process did come back.
    env.setdefault("COMFYUI_REMOTE_REBOOT_BUDGET_S", "300")
    if extra:
        env.update(extra)
    return env


def _encode_message(message: dict) -> bytes:
    """MCP stdio is newline-delimited JSON-RPC (no embedded newlines).

    Content-Length/LSP framing is still *accepted* on read for older servers
    and this repo's mock, but comfyui-mcp's current SDK ignores it — the
    first live spawn logged 'running on stdio' and then never answered
    initialize until writes switched to NDJSON.
    """
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    if "\n" in body:
        raise McpError("MCP stdio payload must not contain embedded newlines")
    return (body + "\n").encode("utf-8")


def _parse_frames(buffer: bytearray) -> list[dict]:
    """Pull complete MCP frames (NDJSON or Content-Length) out of *buffer*."""
    messages: list[dict] = []
    while buffer:
        # Discard non-frame preamble (npx download progress, ANSI, etc.).
        cl = buffer.lower().find(b"content-length:")
        brace = buffer.find(b"{")
        if buffer[0:1] not in (b"{", b"C", b"c"):
            cut = cl if cl >= 0 else brace
            if cut < 0:
                # Keep a short tail in case a marker is split across reads.
                if len(buffer) > 4096:
                    del buffer[:-64]
                break
            log.info(
                "comfyui-mcp stdout preamble: %s",
                bytes(buffer[:cut]).decode("utf-8", errors="replace")[:200],
            )
            del buffer[:cut]
            continue
        if buffer.startswith(b"Content-Length:") or buffer.startswith(b"content-length:"):
            sep = buffer.find(_HEADER_SEP)
            if sep < 0:
                break
            header = bytes(buffer[:sep]).decode("ascii", errors="replace")
            length = None
            for line in header.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    try:
                        length = int(line.split(":", 1)[1].strip())
                    except ValueError as exc:
                        raise McpError(f"invalid Content-Length header: {line!r}") from exc
            if length is None:
                raise McpError(f"MCP frame missing Content-Length: {header!r}")
            start = sep + len(_HEADER_SEP)
            if len(buffer) < start + length:
                break
            body = bytes(buffer[start:start + length])
            del buffer[:start + length]
            try:
                messages.append(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError as exc:
                raise McpError(f"MCP child sent invalid JSON: {body[:200]!r}") from exc
            continue
        nl = buffer.find(b"\n")
        if nl < 0:
            break
        line = bytes(buffer[:nl]).strip()
        del buffer[:nl + 1]
        if not line:
            continue
        if line[:1] != b"{":
            log.info("comfyui-mcp stdout: %s", line.decode("utf-8", errors="replace"))
            continue
        try:
            messages.append(json.loads(line.decode("utf-8")))
        except json.JSONDecodeError as exc:
            raise McpError(f"MCP child sent invalid NDJSON: {line[:200]!r}") from exc
    return messages


def _unwrap_tool_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    if result.get("isError"):
        text = _content_text(result)
        raise McpError(text or "MCP tool returned isError=true")
    text = _content_text(result)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return result


def _content_text(result: dict) -> str:
    parts: list[str] = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text":
            parts.append(str(item.get("text") or ""))
        elif kind == "image":
            mime = item.get("mimeType") or "image"
            parts.append(f"[image {mime} omitted from text result]")
        else:
            parts.append(json.dumps(item, ensure_ascii=False))
    return "\n".join(p for p in parts if p)


class McpClient:
    """One long-lived stdio MCP session. Thread-safe via a request lock."""

    def __init__(
        self,
        argv: list[str] | None = None,
        env: dict[str, str] | None = None,
        stall_s: int | None = None,
        handshake_s: int | None = None,
    ) -> None:
        self.argv = list(argv) if argv is not None else default_argv()
        self.env = env if env is not None else child_env()
        self.stall_s = DEFAULT_STALL_S if stall_s is None else int(stall_s)
        self.handshake_s = HANDSHAKE_TIMEOUT_S if handshake_s is None else int(handshake_s)
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._inbox: queue.Queue = queue.Queue()
        self._stderr_lines: list[str] = []
        self._reader_error: BaseException | None = None
        self._next_id = 1
        self._initialized = False
        self._closed = False

    @property
    def pid(self) -> int | None:
        proc = self._proc
        return proc.pid if proc is not None and proc.poll() is None else None

    def stderr_tail(self, n: int = 40) -> str:
        return "\n".join(self._stderr_lines[-n:])

    def close(self) -> None:
        with self._lock:
            self._closed = True
            proc = self._proc
            self._proc = None
            self._initialized = False
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def ready(self) -> bool:
        """True when a live, handshake-complete child exists. Never spawns."""
        return (
            not self._closed
            and self._initialized
            and self._proc is not None
            and self._proc.poll() is None
        )

    def call(self, name: str, arguments: dict | None = None, timeout: int | None = None,
             *, lock_timeout: float | None = None, spawn: bool = True) -> Any:
        """Call one MCP tool. Blocks until the result or *timeout* seconds.

        ``spawn=False`` refuses if this client has no live child (no handshake).
        ``lock_timeout`` bounds ``Lock.acquire``; on failure raises ``McpError``
        instead of waiting on an in-flight generate (up to DEFAULT_STALL_S).
        """
        payload = dict(arguments or {})
        wait = self.stall_s if timeout is None else int(timeout)
        if lock_timeout is None:
            self._lock.acquire()
        elif not self._lock.acquire(timeout=float(lock_timeout)):
            raise McpError("MCP client lock busy")
        try:
            if spawn:
                self._ensure_started()
            elif not self.ready():
                raise McpError("MCP client is not started")
            result = self._rpc(
                "tools/call",
                {"name": name, "arguments": payload},
                timeout=wait,
            )
        finally:
            self._lock.release()
        return _unwrap_tool_result(result)

    def list_tools(self, timeout: int | None = None) -> list[dict]:
        wait = self.handshake_s if timeout is None else int(timeout)
        with self._lock:
            self._ensure_started()
            result = self._rpc("tools/list", {}, timeout=wait)
        return list((result or {}).get("tools") or [])

    def _ensure_started(self) -> None:
        if self._closed:
            raise McpError("MCP client has been closed")
        if self._proc is not None and self._proc.poll() is None and self._initialized:
            return
        if self._proc is not None and self._proc.poll() is not None:
            rc = self._proc.returncode
            tail = self.stderr_tail()
            self._proc = None
            self._initialized = False
            raise McpError(
                f"comfyui-mcp child exited (rc={rc}) before the next call."
                + (f"\nstderr:\n{tail}" if tail else "")
            )
        self._spawn()
        self._wait_until_ready(self.handshake_s)
        self._handshake()

    def _wait_until_ready(self, timeout: int) -> None:
        """Wait until the child actually speaks MCP, not just until Popen returns.

        ``npx -y`` may download for minutes before comfyui-mcp binds stdio.
        Sending initialize into that window is how the first live handshake
        timed out with the server already logging 'running on stdio'.
        """
        deadline = time.monotonic() + max(1, timeout)
        while time.monotonic() < deadline:
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                tail = self.stderr_tail()
                raise McpError(
                    f"comfyui-mcp exited (rc={proc.returncode}) before it was ready."
                    + (f"\nstderr:\n{tail}" if tail else "")
                )
            text = "\n".join(self._stderr_lines).lower()
            if any(marker in text for marker in _READY_MARKERS):
                return
            time.sleep(0.05)
        # Some MCP servers print nothing on stderr. Try the handshake anyway.

    def _spawn(self) -> None:
        self._inbox = queue.Queue()
        self._reader_error = None
        self._stderr_lines = []
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": self.env,
            "bufsize": 0,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(self.argv, **kwargs)
        except OSError as exc:
            raise McpError(f"failed to spawn MCP child {self.argv!r}: {exc}") from exc
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            proc.kill()
            raise McpError("MCP child was spawned without stdio pipes")
        self._proc = proc
        threading.Thread(target=self._stdout_loop, name="mcp-stdout", daemon=True).start()
        threading.Thread(target=self._stderr_loop, name="mcp-stderr", daemon=True).start()

    def _stdout_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        buffer = bytearray()
        try:
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                for message in _parse_frames(buffer):
                    self._inbox.put(message)
        except BaseException as exc:
            self._reader_error = exc
            log.exception("MCP stdout reader failed")
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    def _stderr_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for raw in iter(proc.stderr.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > _MAX_STDERR_LINES:
                    del self._stderr_lines[: len(self._stderr_lines) - _MAX_STDERR_LINES]
                log.info("comfyui-mcp: %s", line)
        except BaseException:
            log.exception("MCP stderr reader failed")
        finally:
            try:
                proc.stderr.close()
            except Exception:
                pass

    def _handshake(self) -> None:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
            timeout=self.handshake_s,
        )
        self._notify("notifications/initialized")
        self._initialized = True
        server = (result or {}).get("serverInfo") or {}
        log.info(
            "MCP initialized: server=%s version=%s pid=%s path=%s url=%s",
            server.get("name"),
            server.get("version"),
            self.pid,
            self.env.get("COMFYUI_PATH"),
            self.env.get("COMFYUI_URL"),
        )

    def _rpc(self, method: str, params: dict, timeout: int) -> Any:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise McpError("MCP child is not running")
        req_id = self._next_id
        self._next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        try:
            proc.stdin.write(_encode_message(message))
            proc.stdin.flush()
        except OSError as exc:
            raise McpError(f"failed to write MCP request {method}: {exc}") from exc
        deadline = time.monotonic() + max(1, timeout)
        while True:
            if self._reader_error is not None:
                raise McpError(f"MCP stdout reader failed: {self._reader_error}") from self._reader_error
            if proc.poll() is not None:
                tail = self.stderr_tail()
                raise McpError(
                    f"comfyui-mcp exited (rc={proc.returncode}) during {method}."
                    + (f"\nstderr:\n{tail}" if tail else "")
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpTimeout(f"MCP {method} timed out after {timeout}s")
            try:
                incoming = self._inbox.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue
            if incoming.get("id") != req_id:
                # Notifications (progress, logging) have no matching id.
                log.debug("MCP notification: %s", incoming.get("method") or incoming)
                continue
            if "error" in incoming:
                err = incoming["error"]
                if isinstance(err, dict):
                    raise McpError(f"MCP {method} error: {err.get('message') or err}")
                raise McpError(f"MCP {method} error: {err}")
            return incoming.get("result")

    def _notify(self, method: str, params: dict | None = None) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise McpError("MCP child is not running")
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        proc.stdin.write(_encode_message(message))
        proc.stdin.flush()


_client_lock = threading.Lock()
_client: McpClient | None = None


def get_client() -> McpClient:
    """Process-wide singleton. Spawned on first use, kept alive after that."""
    global _client
    with _client_lock:
        if _client is None or _client._closed:
            _client = McpClient()
        return _client


def reset_client() -> None:
    """Close the singleton. Tests call this so each case starts clean."""
    global _client
    with _client_lock:
        client = _client
        _client = None
    if client is not None:
        client.close()


def ready() -> bool:
    """True when the process-wide client already has a live child. Never spawns."""
    with _client_lock:
        client = _client
    return bool(client is not None and client.ready())


def call(name: str, arguments: dict | None = None, timeout: int | None = None,
         *, lock_timeout: float | None = None, spawn: bool = True) -> Any:
    """Call one comfyui-mcp tool on the process-wide client.

    ``spawn=False`` does not create the singleton or handshake. Missing /
    closed / dead client raises ``McpError`` immediately.
    """
    if not spawn:
        with _client_lock:
            client = _client
        if client is None or client._closed:
            raise McpError("MCP client is not started")
        return client.call(name, arguments, timeout=timeout,
                           lock_timeout=lock_timeout, spawn=False)
    return get_client().call(name, arguments, timeout=timeout,
                             lock_timeout=lock_timeout, spawn=True)
