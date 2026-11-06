#!/usr/bin/env python3
"""Media-pipeline orchestrator: bucket → physics → dialect → graph → FaceDetailer.

Does not start ComfyUI and does not replace ``work/image_render.py``. The
legacy renderer keeps custom nodes disabled. This dispatcher builds the
unified API payload and can POST it to ``/prompt``, tracking ``prompt_id``
on ComfyUI's ``/ws`` socket (HTTP ``/history`` is the fallback).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from comfy_graph_builder import (
        ComfyGraphBuilder,
        base_txt2img_workflow,
        prompt_requests_human_subject,
    )
    from media_buckets import resolve_latent_bucket
    from prompt_router import format_prompt_for_target
    from temporal_physics import runtime_inject_temporal_physics
except ImportError:
    from local_agent.comfy_graph_builder import (
        ComfyGraphBuilder,
        base_txt2img_workflow,
        prompt_requests_human_subject,
    )
    from local_agent.media_buckets import resolve_latent_bucket
    from local_agent.prompt_router import format_prompt_for_target
    from local_agent.temporal_physics import runtime_inject_temporal_physics

try:
    import mcp_client
    DEFAULT_COMFY_URL = mcp_client.COMFYUI_URL
except Exception:
    DEFAULT_COMFY_URL = os.environ.get("EQUAL_SHARES_COMFYUI_URL", "http://127.0.0.1:8188")

VIDEO_MODEL_TYPES = frozenset({"video", "wan", "minimax", "i2v", "t2v"})
CLIENT_ID_PREFIX = "media-pipeline"
STILL_DEBUG_DIR = Path(__file__).resolve().parent / "runtime" / "dspy_opt" / "still_debug"
_LOG = logging.getLogger("dispatcher")


def archive_flf_stills(
    start_png: str | Path,
    end_png: str | Path,
    *,
    clip_id: str,
    key: str = "",
    dest_dir: Path | None = None,
) -> dict[str, str]:
    """Copy FLF start/end stills to a debug folder before Wan runs.

    Lets an operator inspect whether SDXL already produced noise, independent
    of ComfyUI's output tree.
    """
    dest = Path(dest_dir) if dest_dir is not None else STILL_DEBUG_DIR
    dest.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    safe_clip = "".join(
        ch if ch.isalnum() or ch in "-_" else "_" for ch in str(clip_id)
    ) or "clip"
    suffix = f"{safe_clip}_{key}_{stamp}" if key else f"{safe_clip}_{stamp}"
    copied: dict[str, str] = {"dir": str(dest)}
    for tag, src in (("start", start_png), ("end", end_png)):
        src_path = Path(src)
        target = dest / f"{suffix}_{tag}{src_path.suffix or '.png'}"
        if src_path.is_file():
            shutil.copy2(src_path, target)
            copied[tag] = str(target)
            _LOG.info("FLF still %s archived %s -> %s", tag, src_path, target)
        else:
            copied[tag] = ""
            _LOG.warning("FLF still %s missing at %s", tag, src_path)
    manifest = dest / "stills.jsonl"
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": time.time(),
            "clip_id": clip_id,
            "key": key,
            "start_src": str(start_png),
            "end_src": str(end_png),
            "start_debug": copied.get("start", ""),
            "end_debug": copied.get("end", ""),
        }, ensure_ascii=True) + "\n")
    return copied


class PipelineDispatchError(RuntimeError):
    """ComfyUI /prompt or WebSocket tracking failed."""


def _http_to_ws(url: str) -> str:
    parsed = urlparse(url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or "127.0.0.1:8188"
    return f"{scheme}://{netloc}"


class PipelineOrchestrator:
    """Strict-order media pipeline. Legacy image_render startup is untouched."""

    def __init__(self, comfy_url: str | None = None, client_id: str | None = None):
        self.comfy_url = (comfy_url or DEFAULT_COMFY_URL).rstrip("/")
        self.client_id = client_id or f"{CLIENT_ID_PREFIX}-{uuid.uuid4().hex[:12]}"

    def websocket_url(self) -> str:
        return (
            f"{_http_to_ws(self.comfy_url)}/ws?"
            f"{urllib.parse.urlencode({'clientId': self.client_id})}"
        )

    def build_and_dispatch_payload(
        self,
        base_prompt: str,
        target_aspect: str,
        model_type: str,
        style: str = "default",
    ) -> dict[str, Any]:
        """Build the finalized ComfyUI ``prompt`` graph. Does not POST.

        Order: latent bucket → Backrooms temporal physics → dialect formatter
        → base API JSON → size/prompt injection → FaceDetailer if human.
        """
        width, height = resolve_latent_bucket(target_aspect)
        model_key = str(model_type or "").strip().lower()
        style_key = str(style or "default").strip().lower() or "default"
        prompt = str(base_prompt or "")

        # Video+backrooms is the spec. style=backrooms on SDXL stills also
        # expands physics so the integration path (woman / 16:9 / sdxl /
        # backrooms) carries camcorder language in the CLIP payload.
        if style_key == "backrooms" or (
                model_key in VIDEO_MODEL_TYPES and style_key == "backrooms"):
            prompt = runtime_inject_temporal_physics(prompt, style="backrooms")

        formatted = format_prompt_for_target(prompt, model_key or "sdxl")
        positive = str(formatted.get("prompt") or prompt)
        negative = str(formatted.get("negative_prompt") or "")

        graph = base_txt2img_workflow(
            prompt=positive,
            negative_prompt=negative,
            width=width,
            height=height,
        )
        builder = ComfyGraphBuilder(graph)
        builder.apply_size_and_prompts(
            prompt=positive,
            negative_prompt=negative,
            width=width,
            height=height,
        )
        check_text = f"{base_prompt}\n{positive}"
        if prompt_requests_human_subject(check_text):
            builder.inject_face_detailer(
                prompt=positive,
                negative_prompt=negative,
            )
        return builder.to_prompt()

    def submit_prompt(self, graph: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
        """POST the graph to ComfyUI ``/prompt``. Returns the queued ``prompt_id``."""
        body = json.dumps({
            "prompt": graph,
            "client_id": self.client_id,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.comfy_url}/prompt",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                queued = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise PipelineDispatchError(
                f"ComfyUI /prompt HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise PipelineDispatchError(f"ComfyUI /prompt failed: {exc}") from exc
        if not queued.get("prompt_id"):
            raise PipelineDispatchError(f"ComfyUI /prompt returned no prompt_id: {queued!r}")
        queued["client_id"] = self.client_id
        queued["websocket_url"] = self.websocket_url()
        return queued

    def track_prompt_id(
        self,
        prompt_id: str,
        *,
        timeout_s: float = 60.0,
        websocket_connect: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        """Follow ``prompt_id`` on ``/ws`` until executed, then confirm ``/history``.

        ``websocket_connect`` is injectable so tests never open a live socket.
        Default: stdlib RFC6455 client to ``/ws?clientId=...``.
        """
        prompt_id = str(prompt_id)
        deadline = time.monotonic() + max(1.0, float(timeout_s))
        ws_error = None
        connect = websocket_connect or _connect_comfy_websocket
        try:
            session = connect(self.websocket_url(), timeout=min(10.0, timeout_s))
            try:
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    raw = session.recv_text(timeout=min(5.0, remaining))
                    if raw is None:
                        continue
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    kind = str(message.get("type") or "")
                    data = message.get("data") if isinstance(message.get("data"), dict) else {}
                    msg_prompt = str(data.get("prompt_id") or "")
                    if msg_prompt and msg_prompt != prompt_id:
                        continue
                    # Per-node ``executed`` is not job completion. Live runs
                    # must wait for ``execution_success``, or the classic
                    # ``executing`` frame with node=null.
                    node = data.get("node")
                    job_done = kind == "execution_success" or (
                        kind == "executing" and node is None and msg_prompt == prompt_id
                    )
                    if job_done:
                        return {
                            "state": "complete",
                            "prompt_id": prompt_id,
                            "source": "websocket",
                            "type": kind,
                        }
                    if kind in {"execution_error", "execution_interrupted"}:
                        return {
                            "state": "error",
                            "prompt_id": prompt_id,
                            "source": "websocket",
                            "type": kind,
                            "data": data,
                        }
            finally:
                session.close()
        except Exception as exc:
            ws_error = exc
        history = _fetch_history_state(prompt_id, url=self.comfy_url)
        if history.get("state") in {"complete", "error"}:
            history["websocket_error"] = None if ws_error is None else str(ws_error)
            return history
        raise PipelineDispatchError(
            f"prompt_id {prompt_id} not finished within {timeout_s:.0f}s"
            + (f" (websocket: {ws_error})" if ws_error else "")
        )


class _StdlibWebSocket:
    """Minimal client for ComfyUI's unmasked JSON text frames."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._lock = threading.Lock()

    def recv_text(self, timeout: float = 5.0) -> str | None:
        self._sock.settimeout(max(0.1, float(timeout)))
        try:
            header = _recv_exact(self._sock, 2)
        except (TimeoutError, socket.timeout, OSError):
            return None
        if not header:
            return None
        opcode = header[0] & 0x0F
        length = header[1] & 0x7F
        if header[1] & 0x80:
            raise PipelineDispatchError("unexpected masked server frame")
        if length == 126:
            length = struct.unpack("!H", _recv_exact(self._sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exact(self._sock, 8))[0]
        payload = _recv_exact(self._sock, length) if length else b""
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            return None
        if opcode != 0x1:
            return None
        return payload.decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < n:
        piece = sock.recv(n - len(chunks))
        if not piece:
            raise PipelineDispatchError("websocket closed")
        chunks.extend(piece)
    return bytes(chunks)


def _connect_comfy_websocket(url: str, timeout: float = 10.0) -> _StdlibWebSocket:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/ws"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    key = __import__("base64").b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.sendall(req.encode("ascii"))
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise PipelineDispatchError("websocket handshake closed")
        buffer += chunk
    header = buffer.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    if "101" not in header.split("\r\n", 1)[0]:
        sock.close()
        raise PipelineDispatchError(f"websocket handshake failed: {header.splitlines()[0]}")
    return _StdlibWebSocket(sock)


def _fetch_history_state(prompt_id: str, *, url: str) -> dict[str, Any]:
    try:
        import comfy_api
    except ImportError:
        import local_agent.comfy_api as comfy_api
    payload = comfy_api._fetch_history(prompt_id, url=url)
    parsed = comfy_api.parse_history(payload, prompt_id)
    parsed["source"] = "history"
    return parsed
