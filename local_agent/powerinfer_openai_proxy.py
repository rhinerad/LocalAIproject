"""Loopback-only OpenAI chat-completions adapter for a local PowerInfer server.

This is intentionally not part of the normal local-agent launcher. It never
downloads a model, starts PowerInfer, or bypasses the GPU permission gateway.
Start it only after a matching sparse PowerInfer model has been verified.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator


LISTEN_HOST = os.environ.get("POWERINFER_PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("POWERINFER_PROXY_PORT", "8091"))
BACKEND_URL = os.environ.get("POWERINFER_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
MODEL_ALIAS = os.environ.get("POWERINFER_MODEL_ALIAS", "powerinfer-local")
API_KEY = os.environ.get("POWERINFER_PROXY_API_KEY", "")
REGISTRY_PATH = os.environ.get("POWERINFER_REGISTRY_PATH", "")
REGISTRY_MODEL_ID = os.environ.get("POWERINFER_REGISTRY_MODEL_ID", "")
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 64 * 1024
MAX_COMPLETION_TOKENS = 2048


class ProxyError(ValueError):
    """A request error safe to expose to a loopback client."""


def _require_registered_bundle() -> None:
    """Refuse an unreviewed sparse backend before exposing a proxy endpoint.

    The proxy never starts PowerInfer itself.  This validates that the already
    selected backend has an explicit, immutable acceptance record before a
    human starts this loopback HTTP adapter.
    """
    if not REGISTRY_PATH or not REGISTRY_MODEL_ID:
        raise SystemExit(
            "PowerInfer proxy requires POWERINFER_REGISTRY_PATH and "
            "POWERINFER_REGISTRY_MODEL_ID for an accepted sparse bundle"
        )
    tools_dir = Path(__file__).resolve().parents[1] / "tools" / "powerinfer"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        from production_registry import RegistryError, load_registered_model
        entry = load_registered_model(Path(REGISTRY_PATH), REGISTRY_MODEL_ID)
    except (ImportError, OSError, ValueError) as exc:
        raise SystemExit(f"PowerInfer proxy refused unverified registry entry: {exc}") from exc
    if entry["alias"] != MODEL_ALIAS:
        raise SystemExit(
            f"POWERINFER_MODEL_ALIAS must match accepted registry alias {entry['alias']!r}"
        )


def _content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # Accept the text part of OpenAI-style content blocks; PowerInfer is
        # text-only, so images and tool calls are intentionally refused below.
        texts = [item.get("text", "") for item in value if isinstance(item, dict) and item.get("type") == "text"]
        if texts:
            return "".join(texts)
    raise ProxyError("message content must be text")


def render_llama2_chat(messages: list[dict[str, Any]]) -> str:
    """Render roles for the supported PowerInfer Llama-2-family sparse models."""
    if not isinstance(messages, list) or not messages:
        raise ProxyError("messages must be a non-empty list")
    system_parts: list[str] = []
    turns: list[tuple[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ProxyError("every message must be an object")
        role = message.get("role")
        text = _content(message.get("content"))
        if role == "system":
            if turns:
                raise ProxyError("system messages must precede conversation turns")
            system_parts.append(text)
        elif role in {"user", "assistant"}:
            turns.append((role, text))
        else:
            raise ProxyError("only system, user, and assistant messages are supported")
    if not turns or turns[0][0] != "user":
        raise ProxyError("the first non-system message must be from the user")
    for index, (role, _) in enumerate(turns):
        expected = "user" if index % 2 == 0 else "assistant"
        if role != expected:
            raise ProxyError("chat messages must alternate user and assistant")
    system = "\n\n".join(system_parts).strip()
    prompt = ""
    for index in range(0, len(turns), 2):
        user_text = turns[index][1]
        assistant_text = turns[index + 1][1] if index + 1 < len(turns) else None
        prefix = f"<<SYS>>\n{system}\n<</SYS>>\n\n" if index == 0 and system else ""
        prompt += f"<s>[INST] {prefix}{user_text} [/INST]"
        if assistant_text is not None:
            prompt += f" {assistant_text}</s>"
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ProxyError("rendered prompt exceeds the loopback proxy limit")
    return prompt


def completion_payload(body: dict[str, Any]) -> dict[str, Any]:
    prompt = render_llama2_chat(body.get("messages"))
    requested = body.get("max_tokens", 512)
    if not isinstance(requested, int) or requested < 1:
        raise ProxyError("max_tokens must be a positive integer")
    payload: dict[str, Any] = {
        "prompt": prompt,
        "n_predict": min(requested, MAX_COMPLETION_TOKENS),
        "n_keep": -1,
        "cache_prompt": True,
        "stream": bool(body.get("stream", False)),
    }
    for name in ("temperature", "top_k", "top_p", "repeat_penalty", "seed", "stop"):
        if name in body:
            payload[name] = body[name]
    if "stop" not in payload:
        # Without defaults a base model can fill the token budget writing EOS characters
        # as text tokens rather than emitting the actual EOS token id.
        payload["stop"] = ["</s>", "[INST]"]
    elif not isinstance(payload["stop"], list):
        raise ProxyError("stop must be a list of strings")
    return payload


def _request(payload: dict[str, Any], *, stream: bool = False):
    request = urllib.request.Request(
        f"{BACKEND_URL}/completion",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        return urllib.request.urlopen(request, timeout=600)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProxyError("PowerInfer backend is unavailable") from exc


class _BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, handler):
        self._slots = threading.BoundedSemaphore(4)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def _finish_reason(result: dict[str, Any]) -> str:
    return "stop" if result.get("stopped_eos") or result.get("stopped_word") else "length"


def _sse_chunks(response, *, request_id: str, created: int) -> Iterator[bytes]:
    first = {"id": request_id, "object": "chat.completion.chunk", "created": created,
             "model": MODEL_ALIAS, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    yield f"data: {json.dumps(first)}\n\n".encode("utf-8")
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        try:
            part = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        content = str(part.get("content", ""))
        choice = {"index": 0, "delta": {"content": content} if content else {},
                  "finish_reason": _finish_reason(part) if part.get("stop") else None}
        chunk = {"id": request_id, "object": "chat.completion.chunk", "created": created,
                 "model": MODEL_ALIAS, "choices": [choice]}
        yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "PowerInferOpenAIProxy/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not write prompts, headers, or API keys to the terminal log.
        return

    def _json(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": {"message": message, "type": "invalid_request_error"}})

    def _authorized(self) -> bool:
        if not API_KEY:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {API_KEY}"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(HTTPStatus.OK, {"status": "proxy_ready", "backend": "not_probed"})
        elif self.path in {"/v1/models", "/models"}:
            self._json(HTTPStatus.OK, {"object": "list", "data": [{"id": MODEL_ALIAS, "object": "model", "owned_by": "local"}]})
        else:
            self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        if self.path not in {"/v1/chat/completions", "/chat/completions"}:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not self._authorized():
            self._error(HTTPStatus.UNAUTHORIZED, "invalid API key")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ProxyError("request size is outside the loopback proxy limit")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ProxyError("request body must be an object")
            payload = completion_payload(body)
            request_id, created = f"chatcmpl-{uuid.uuid4().hex}", int(time.time())
            response = _request(payload, stream=payload["stream"])
            try:
                if payload["stream"]:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    for chunk in _sse_chunks(response, request_id=request_id, created=created):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ProxyError("backend response exceeds the cap")
                result = json.loads(raw.decode("utf-8"))
            finally:
                response.close()
            answer = {
                "id": request_id, "object": "chat.completion", "created": created, "model": MODEL_ALIAS,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": result.get("content", "")},
                             "finish_reason": _finish_reason(result)}],
                "usage": {"prompt_tokens": result.get("tokens_evaluated", 0),
                          "completion_tokens": result.get("tokens_predicted", 0),
                          "total_tokens": result.get("tokens_evaluated", 0) + result.get("tokens_predicted", 0)},
            }
            self._json(HTTPStatus.OK, answer)
        except ProxyError as exc:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE if "unavailable" in str(exc) else HTTPStatus.BAD_REQUEST, str(exc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "request must be valid JSON")


def main() -> None:
    if LISTEN_HOST not in {"127.0.0.1", "localhost"}:
        raise SystemExit("PowerInfer proxy must remain loopback-only")
    _require_registered_bundle()
    server = _BoundedServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"PowerInfer OpenAI proxy listening on http://{LISTEN_HOST}:{LISTEN_PORT}/v1")
    server.serve_forever()


if __name__ == "__main__":
    main()
