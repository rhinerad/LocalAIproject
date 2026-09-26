"""OpenAI-compat client for the loopback PowerInfer proxy.

The proxy contract is unchanged: POST /v1/chat/completions and GET /v1/models.
This module never starts server.exe or the proxy. Callers must already have a
runnable router Decision pointing at POWERINFER_PROXY_HOST.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Iterator, Union

import ollama_client as oll


def proxy_host() -> str:
    host = os.environ.get("POWERINFER_PROXY_BIND", "127.0.0.1")
    port = os.environ.get("POWERINFER_PROXY_PORT", "8091")
    return f"{host}:{port}"


def api_key() -> str:
    return os.environ.get("POWERINFER_PROXY_API_KEY", "")


def flatten_messages(messages: list[dict]) -> list[dict]:
    """Render local-agent history as text-only system/user/assistant turns.

    The PowerInfer proxy refuses tool roles, images, and native tool calls.
    Consecutive same-role messages are merged so the Llama-2 renderer still
    sees alternating user/assistant turns after a tool hop.
    """
    flat: list[dict] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        text = str(content)
        if role == "tool":
            name = str(message.get("name") or "tool")
            role = "user"
            text = f"Tool {name} result:\n{text}"
        elif role not in {"system", "user", "assistant"}:
            continue
        if flat and flat[-1]["role"] == role:
            flat[-1]["content"] = flat[-1]["content"] + "\n\n" + text
        else:
            flat.append({"role": role, "content": text})
    return flat


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


_MAX_HTTP_BYTES = 2_000_000


def _raise_http(exc: urllib.error.HTTPError, host: str) -> None:
    detail = exc.read(8000).decode("utf-8", errors="replace")[:1000]
    message = f"PowerInfer proxy HTTP {exc.code} at {host}: {detail}"
    if exc.code >= 500 or exc.code in (408, 429):
        raise oll.OllamaModelFailure(message) from exc
    raise oll.OllamaUnavailable(message) from exc


def chat(messages: list[dict], *, host: str, model: str, timeout: int = 900,
         options: dict | None = None, **_ignored) -> tuple[str, list]:
    """One non-streaming PowerInfer turn. Tool schemas are ignored."""
    opts = options or {}
    body = {
        "model": model,
        "messages": flatten_messages(messages),
        "stream": False,
        "temperature": float(opts.get("temperature", 0.3)),
        "top_p": float(opts.get("top_p", 0.9)),
        "max_tokens": int(opts.get("num_predict", opts.get("max_tokens", 512))),
    }
    request = urllib.request.Request(
        f"http://{host}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            blob = response.read(_MAX_HTTP_BYTES + 1)
        if len(blob) > _MAX_HTTP_BYTES:
            raise oll.OllamaUnavailable(f"PowerInfer proxy response exceeds the cap at {host}")
        raw = json.loads(blob)
    except urllib.error.HTTPError as exc:
        _raise_http(exc, host)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise oll.OllamaUnavailable(
            f"cannot reach PowerInfer proxy at {host}: {exc}. "
            "Start server.exe and local_agent\\powerinfer_openai_proxy.py; "
            "the router does not start them."
        ) from exc
    choices = raw.get("choices") or []
    if not choices:
        raise oll.OllamaUnavailable(f"PowerInfer proxy returned no choices: {raw!r}")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str):
        raise oll.OllamaUnavailable(f"PowerInfer proxy response has no text content: {raw!r}")
    return oll._visible_text(content), []


def chat_stream(messages: list[dict], *, host: str, model: str,
                timeout: int = 900, options: dict | None = None,
                should_stop=None, **_ignored) -> Iterator[Union[str, oll.ToolCall]]:
    """OpenAI SSE stream from the PowerInfer proxy. Never yields ToolCall."""
    opts = options or {}
    body = {
        "model": model,
        "messages": flatten_messages(messages),
        "stream": True,
        "temperature": float(opts.get("temperature", 0.3)),
        "top_p": float(opts.get("top_p", 0.9)),
        "max_tokens": int(opts.get("num_predict", opts.get("max_tokens", 512))),
    }
    request = urllib.request.Request(
        f"http://{host}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(), method="POST")
    visible_filter = oll._VisibleTextFilter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            seen = 0
            for raw in response:
                seen += len(raw)
                if seen > _MAX_HTTP_BYTES:
                    raise oll.OllamaUnavailable(
                        f"PowerInfer proxy stream exceeds the cap at {host}")
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise oll.OllamaModelFailure(
                        f"PowerInfer proxy error at {host}: {chunk['error']}")
                choices = chunk.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                piece = visible_filter.feed(str(delta.get("content") or ""))
                if piece:
                    yield piece
                if should_stop is not None and should_stop():
                    return
    except urllib.error.HTTPError as exc:
        _raise_http(exc, host)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise oll.OllamaUnavailable(
            f"cannot reach PowerInfer proxy at {host}: {exc}. "
            "Start server.exe and local_agent\\powerinfer_openai_proxy.py; "
            "the router does not start them."
        ) from exc
