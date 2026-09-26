#!/usr/bin/env python3
"""Tiny OpenAI-compatible client for the loopback-only CUDA llama.cpp vision server."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def up(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


# (option key, cast) pairs copied verbatim into the request body when present.
# Ollama-only keys (num_gpu, num_ctx, json_mode, num_predict) are handled or
# dropped separately; llama-server rejects nothing here but ignores unknown keys.
_SAMPLER_FIELDS = (
    ("repeat_penalty", float),
    ("repeat_last_n", int),
    ("presence_penalty", float),
    ("frequency_penalty", float),
    ("top_k", int),
    ("top_p", float),
    ("min_p", float),
    ("seed", int),
    ("stop", list),
    # 2026-09-25n/o: llama-server keeps the previous request's shared prefix
    # (the system prompt's KV) unless told not to, and the answer depends on
    # that state. The GVD judge sends False so every judgement is the cold
    # prefill the live metric gets. None (unset) keeps the server default.
    ("cache_prompt", bool),
)


def chat(messages: list[dict], *, host: str, model: str, timeout: int = 1200,
         options: dict | None = None) -> tuple[str, dict]:
    """Call llama.cpp's OpenAI endpoint with Qwen2.5-VL image content.

    ``messages`` uses the local agent's normal system/user structure. Image
    values are base64 strings and become OpenAI-compatible data URLs here; the
    llama.cpp server applies Qwen2.5-VL's native image-token template.
    """
    wire_messages = []
    for message in messages:
        images = list(message.get("images") or [])
        if images:
            content = [{"type": "text", "text": str(message.get("content") or "")}]
            content.extend({"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{image}"}} for image in images)
        else:
            content = str(message.get("content") or "")
        wire_messages.append({"role": str(message.get("role") or "user"), "content": content})
    opts = options or {}
    body = {
        "model": model,
        "messages": wire_messages,
        "stream": False,
        "temperature": float(opts.get("temperature", 0.0)),
        "max_tokens": int(opts.get("num_predict", 2048)),
    }
    # llama-server's OpenAI endpoint also accepts its native sampler fields in
    # the body. Until 2026-09-24 only temperature and max_tokens were sent, so
    # callers' repeat_penalty (media_tools: 1.08) was silently ignored and the
    # judge could run away into list repetition (CHANGELOG 2026-09-24r).
    # Forwarded only when the caller set them; nothing is invented here.
    for key, cast in _SAMPLER_FIELDS:
        if opts.get(key) is not None:
            body[key] = cast(opts[key])
    if opts.get("json_mode"):
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        f"http://{host}/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"llama.cpp vision server HTTP {exc.code}: {detail}") from exc
    choices = raw.get("choices") or []
    if not choices:
        raise RuntimeError(f"llama.cpp vision server returned no choices: {raw!r}")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"llama.cpp vision response has no text content: {raw!r}")
    return content, raw
