#!/usr/bin/env python3
"""CPU-only Ollama client. Standard library only — nothing to install.

TWO HARD CONSTRAINTS THIS FILE EXISTS TO ENFORCE
------------------------------------------------
1. **It must never touch the GPU.** The whole point is that this agent stays
   usable while a render owns the card. `CUDA_VISIBLE_DEVICES=-1` plus
   `OLLAMA_VULKAN=false` is set on the server process (Ollama 0.32.15 still
   Vulkan-discovers the GPU if only CUDA is hidden; ollama#16508), `num_gpu: 0`
   is sent with every request, and the client talks
   to port **11435** — a second Ollama instance, deliberately not the default
   11434, so it cannot accidentally attach to a GPU-enabled server someone else
   started.

2. **It must not require a download.** The operator is on a phone hotspot and the
   standing rule is to state the size and ask first. So: no `requests`, no
   `ollama` package, no web framework. `urllib` and `json` from the standard
   library. The only thing that must already be on disk is Ollama itself and one
   pulled model.

THERMAL
-------
`num_thread: 4` matches the existing cap in `work/run_open_interpreter_handoff.py`
— four of the host's sixteen logical processors. CLAUDE.md makes that cap and the
ban on a second concurrent local model the CPU safeguards, because Windows does
not expose a usable package-temperature sensor on this machine. Do not raise it,
and do not run two models side by side.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from typing import Iterator, Union

import router

HOST = os.environ.get("EQUAL_SHARES_OLLAMA_HOST", "127.0.0.1:11435")
MODEL = os.environ.get("EQUAL_SHARES_OLLAMA_MODEL", "equal-shares")
FALLBACK_MODELS = ["qwen2.5-coder:14b", "qwen2.5:14b", "llama3.1:8b", "mistral:7b"]

# CPU-only, thread-capped, deterministic-ish. temperature stays low because this
# agent's job is to follow a fixed format, not to be interesting.
DEFAULT_OPTIONS = {
    "num_gpu": 0,
    "num_thread": router.CPU_THREAD_CAP,
    "temperature": 0.2,
    "top_p": 0.9,
    "repeat_penalty": 1.05,
    # Router policy is the source of truth.  The tool schemas and always-on
    # policy exceed 8k by themselves, so a CPU fallback needs this full window.
    "num_ctx": router.CPU_OPTIONS["num_ctx"],
}


class OllamaUnavailable(RuntimeError):
    """Raised when the local model cannot be reached. Callers must degrade."""


class OllamaModelFailure(OllamaUnavailable):
    """A retryable server/model failure, including HTTP 5xx and GPU OOM.

    The router may retry this exact category on the small GPU model.  A normal
    validation/tool error must not be mistaken for an OOM and retried blindly.
    """


def is_failover_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in (
        "out of memory", "oom", "cuda", "allocation", "gpu", "timed out",
        "timeout", "http 500", "http 502", "http 503", "http 504",
        "connection reset", "connection refused",
    ))


class ToolCall:
    """Yielded at the end of chat_stream when the model invokes tools.

    A turn that is purely tool calls produces no text tokens before this object.
    The caller checks `isinstance(piece, ToolCall)` to separate content from calls.

    `calls` mirrors Ollama's format: [{"function": {"name": "...", "arguments": {...}}}]
    `arguments` is always a dict here — string JSON is parsed before yielding.
    """
    __slots__ = ("calls",)

    def __init__(self, calls: list[dict]):
        self.calls = calls

    def __repr__(self) -> str:
        names = [c.get("function", {}).get("name", "?") for c in self.calls]
        return f"ToolCall({names})"


class StreamEnd:
    """Always the last yield on the Ollama ``chat_stream`` path.

    Carries the four token/duration fields from the final ``done=True``
    NDJSON chunk (same keys ``chat()`` already copies), plus the
    thinking/visible character counts already tracked for the empty-
    completion stderr breadcrumb. Hop-loop callers must treat this as a
    trailer, not as text — ``str(StreamEnd(...))`` must never be stored
    as the assistant reply.

    ``unclosed_think_chars`` is nonzero only when a ``<think>`` tag opened in
    ``message.content`` and the stream ended (``done`` or a cooperative stop)
    before a matching ``</think>`` ever arrived. That buffered reasoning text
    is never surfaced as visible content — it is discarded, same as before —
    but its length is folded into ``thinking_chars`` here so a turn that
    genuinely generated tokens (just never got past its own reasoning) is
    distinguishable in telemetry from a truly silent model. Without this, a
    template that ignores ``think=False`` and opens ``<think>`` inside
    ``content`` and then exhausts its budget mid-block produces
    ``visible_chars=0`` and ``thinking_chars=0`` with no trace of the ~50s
    and hundreds of tokens actually spent (2026-09-05, conversation
    e40fa885d6134050, `huihui_ai/qwen3-abliterated:14b`).

    PowerInfer ``chat_stream`` does not yield this type.
    """
    __slots__ = ("telemetry", "thinking_chars", "visible_chars",
                 "unclosed_think_chars", "raw_content_chars")

    def __init__(self, telemetry: dict | None = None, *,
                 thinking_chars: int = 0, visible_chars: int = 0,
                 unclosed_think_chars: int = 0,
                 raw_content_chars: int = 0):
        self.telemetry = dict(telemetry or {})
        self.thinking_chars = int(thinking_chars)
        self.visible_chars = int(visible_chars)
        self.unclosed_think_chars = int(unclosed_think_chars)
        # Chars seen in message.content before _VisibleTextFilter. Distinguishes
        # "filter swallowed real text" from "Ollama returned empty content while
        # still reporting a nonzero eval_count" (2026-09-06 live, post-ee).
        self.raw_content_chars = int(raw_content_chars)

    def __repr__(self) -> str:
        return (f"StreamEnd(thinking_chars={self.thinking_chars}, "
                f"visible_chars={self.visible_chars}, "
                f"unclosed_think_chars={self.unclosed_think_chars}, "
                f"raw_content_chars={self.raw_content_chars}, "
                f"telemetry={self.telemetry!r})")


CHAT_TELEMETRY_KEYS = (
    "eval_count",
    "prompt_eval_count",
    "total_duration",
    "eval_duration",
)


class ChatResult(tuple):
    """``(text, tool_calls)`` plus captured Ollama token/duration telemetry.

    Unpacks as a 2-tuple so existing ``text, calls = chat()`` sites stay valid.
    Future tracing/token-ledger work reads ``result.telemetry`` for the four
    fields Ollama already returns (and that ``chat()`` used to discard).
    """

    def __new__(cls, text: str, tool_calls: list, telemetry: dict | None = None):
        obj = tuple.__new__(cls, (text, tool_calls))
        obj.telemetry = dict(telemetry or {})
        return obj


def chat_telemetry(response: dict | None) -> dict[str, int]:
    """Copy Ollama token/duration fields off an ``/api/chat`` response.

    Missing or non-numeric values are omitted so an empty dict means "no
    telemetry" (PowerInfer proxy, truncated replies, older servers).
    """
    data = response if isinstance(response, dict) else {}
    out: dict[str, int] = {}
    for key in CHAT_TELEMETRY_KEYS:
        value = data.get(key)
        # bool is a subclass of int; a true/false flag is not a token count.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[key] = int(value)
    return out


class _VisibleTextFilter:
    """Suppress optional Qwen-style thinking blocks from visible streaming text.

    Ollama versions/models differ: some put reasoning in ``message.thinking``;
    others place ``<think>…</think>`` directly in ``message.content``. The latter
    must not reach a GUI or Sideband message. The filter only treats a thinking
    marker at the beginning of a model turn specially, so normal prose streams
    immediately after at most a partial tag (eight characters).
    """
    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self.state = "prefix"
        self.pending = ""
        # Running count of chars fed while hidden, independent of `pending`
        # (which is capped defensively so a never-closing block can't grow
        # unbounded). Only meaningful — i.e. only reflects a real dangling
        # block — when the stream ends with state still "hidden"; see
        # `unclosed_hidden_chars()`.
        self.hidden_chars = 0

    def feed(self, piece: str) -> str:
        if not piece:
            return ""
        if self.state == "visible":
            return piece
        if self.state == "hidden":
            self.hidden_chars += len(piece)
        self.pending += piece
        leading = self.pending.lstrip()

        if self.state == "prefix":
            # Hold a partial leading marker, otherwise ordinary prose can pass.
            if leading and (self.OPEN.startswith(leading) or self.CLOSE.startswith(leading)):
                return ""
            if not leading:
                # Nothing but whitespace fed so far. `"<think>".startswith("")`
                # is trivially True in Python, so the check above would hold
                # an all-whitespace `pending` forever if it ran unguarded — a
                # model that streams only whitespace tokens never produces a
                # non-empty `leading` to test, so the genuine-prefix check
                # never gets a chance to fail on its own. Both markers are
                # entirely non-whitespace, so whitespace can never grow into
                # one; once we've held more of it than either marker is long,
                # no tag is coming and further holding would grow `pending`
                # unboundedly (unlike the "hidden" state, which caps itself).
                max_marker = max(len(self.OPEN), len(self.CLOSE))
                if len(self.pending) <= max_marker:
                    return ""
                self.state = "visible"
                text, self.pending = self.pending, ""
                return text
            open_at = leading.find(self.OPEN)
            close_at = leading.find(self.CLOSE)
            if open_at == 0:
                self.state = "hidden"
                self.pending = leading[len(self.OPEN):]
                self.hidden_chars += len(self.pending)
            elif close_at >= 0:
                # A few Qwen templates leak a preamble then a dangling close.
                # Treat only this initial close marker as hidden reasoning.
                self.state = "visible"
                text = leading[close_at + len(self.CLOSE):].lstrip()
                self.pending = ""
                return text
            else:
                self.state = "visible"
                text, self.pending = self.pending, ""
                return text

        if self.state == "hidden":
            end = self.pending.find(self.CLOSE)
            if end < 0:
                # Cap retained internal reasoning defensively; it is never
                # rendered, and a malformed never-closing block must not grow.
                self.pending = self.pending[-len(self.CLOSE):]
                return ""
            text = self.pending[end + len(self.CLOSE):].lstrip()
            self.pending = ""
            self.state = "visible"
            return text
        return ""

    def unclosed_hidden_chars(self) -> int:
        """Chars fed while hidden, if the stream ended without a ``</think>``.

        Returns 0 once a close tag has actually been seen (state moved to
        ``visible``) — a normal, correctly-closed think block is unaffected.
        Call this only after the stream has ended (or on a cooperative stop);
        it is not meaningful mid-stream.
        """
        return self.hidden_chars if self.state == "hidden" else 0

    def finish(self) -> str:
        """Flush any leftover ``prefix`` hold when the stream ends.

        Mid-stream, ``prefix`` may legitimately hold up to one marker's worth
        of text while deciding whether a ``<think>``/``</think>`` is forming.
        If the iterator ends (or Stop fires) while still in that hold, those
        chars were previously discarded with no telemetry — a short silent
        gap on top of the whitespace/unclosed shapes. Hidden state is left
        alone (``unclosed_hidden_chars`` already accounts for it). Visible
        state has nothing buffered.
        """
        if self.state != "prefix" or not self.pending:
            return ""
        text, self.pending = self.pending, ""
        self.state = "visible"
        return text


def _visible_text(text: str) -> str:
    """Non-streaming equivalent of _VisibleTextFilter for /api/chat replies."""
    value = str(text or "")
    value = re.sub(r"^\s*<think>.*?</think>\s*", "", value,
                   flags=re.IGNORECASE | re.DOTALL)
    if "</think>" in value:
        value = value.split("</think>", 1)[1].lstrip()
    return value


def _post(path: str, payload: dict, timeout: int = 600,
          host: str | None = None) -> dict:
    host = host or HOST
    req = urllib.request.Request(
        f"http://{host}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code >= 500 or exc.code in (408, 429):
            raise OllamaModelFailure(f"Ollama HTTP {exc.code} at {host}: {detail}") from exc
        raise OllamaUnavailable(f"Ollama HTTP {exc.code} at {host}: {detail}") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise OllamaUnavailable(
            f"cannot reach Ollama at {host}: {exc}. Start it with "
            f"local_agent\\START_LOCAL_AGENT_GUI.ps1, which launches a CPU-only "
            f"server on that port."
        ) from exc


def available() -> bool:
    try:
        with urllib.request.urlopen(f"http://{HOST}/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def models() -> list[str]:
    try:
        with urllib.request.urlopen(f"http://{HOST}/api/tags", timeout=10) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:
        return []


def pick_model() -> str:
    """Prefer the project model; otherwise the best thing actually installed.

    Never pulls. A missing model is reported, not downloaded — see the hotspot
    rule above.
    """
    have = models()
    if not have:
        raise OllamaUnavailable(
            f"Ollama is reachable at {HOST} but has no models. Pull one on a real "
            f"connection first, e.g. `ollama pull qwen2.5-coder:14b` (~9 GB)."
        )
    if MODEL in have:
        return MODEL
    for m in FALLBACK_MODELS:
        for h in have:
            if h.split(":")[0] == m.split(":")[0]:
                return h
    return have[0]


def _is_powerinfer_host(host: str | None) -> bool:
    return (host or HOST) == router.POWERINFER_PROXY_HOST


def chat(messages: list[dict], model: str | None = None,
         options: dict | None = None, timeout: int = 900,
         host: str | None = None,
         tools: list | None = None,
         response_format: dict | str | None = None,
         keep_alive: str | int | None = None) -> ChatResult:
    """One non-streaming turn. Returns (text, tool_calls).

    tool_calls is [] when the model generates prose instead of calling tools.
    Pass tools=tools.schemas() to enable native function calling.
    `host` lets router.py aim this at either Ollama instance per turn.
    `response_format` is Ollama's ``format`` field (``json`` or a JSON Schema)
    for narrow internal structured outputs such as a task-plan proposal.

    The return value unpacks as ``(text, tool_calls)`` and also carries
    ``.telemetry``: ``eval_count``, ``prompt_eval_count``, ``total_duration``,
    and ``eval_duration`` copied from Ollama when present.
    """
    if _is_powerinfer_host(host):
        import powerinfer_client
        text, calls = powerinfer_client.chat(
            messages, host=host or router.POWERINFER_PROXY_HOST,
            model=model or router.POWERINFER_MODEL_ALIAS,
            timeout=timeout, options=options)
        return ChatResult(text, calls, {})
    opts = dict(DEFAULT_OPTIONS)
    opts.update(options or {})
    payload: dict = {
        "model": model or pick_model(),
        "messages": messages,
        "stream": False,
        "options": opts,
    }
    if tools:
        payload["tools"] = tools
    if response_format:
        payload["format"] = response_format
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    data = _post("/api/chat", payload, timeout=timeout, host=host)
    if data.get("error"):
        raise OllamaModelFailure(f"Ollama model error at {host or HOST}: {data['error']}")
    msg = data.get("message") or {}
    return ChatResult(
        _visible_text(msg.get("content", "")),
        msg.get("tool_calls") or [],
        chat_telemetry(data),
    )


def embed(inputs: list[str] | str, *, model: str = "nomic-embed-text:latest",
          host: str | None = None, timeout: int = 120) -> list[list[float]]:
    """Create local embeddings on the CPU-only Ollama endpoint.

    Embeddings are intentionally a separate capability from chat: they always
    retain the four-thread/no-GPU cap and immediately unload after the request.
    They must never claim the GPU merely to search a small local exemplar store.
    """
    values = [str(inputs)] if isinstance(inputs, str) else [str(value) for value in inputs]
    if not values:
        return []
    payload = {"model": model, "input": values, "options": dict(DEFAULT_OPTIONS),
               "keep_alive": "0"}
    data = _post("/api/embed", payload, timeout=timeout, host=host or HOST)
    vectors = data.get("embeddings") or []
    if len(vectors) != len(values) or any(not isinstance(vector, list) for vector in vectors):
        raise OllamaModelFailure("Ollama returned an invalid embedding response")
    return vectors


def _log_empty_thinking(thinking_chars: int, *, think, model,
                         unclosed_think_chars: int = 0) -> None:
    """Stderr breadcrumb when Ollama spent tokens only in message.thinking.

    ``unclosed_think_chars`` is nonzero when the "thinking" in question was a
    ``<think>`` block embedded in ``message.content`` that never closed
    (rather than, or in addition to, native ``message.thinking``), so the
    breadcrumb names the actual failure shape instead of looking identical to
    a genuinely silent model.
    """
    if unclosed_think_chars:
        print(
            f"ollama_client: empty visible content after {thinking_chars} thinking "
            f"char(s) ({unclosed_think_chars} of them an unclosed <think> block in "
            f"content that never saw </think>); think={think!r} model={model!r}",
            file=sys.stderr,
            flush=True,
        )
        return
    print(
        f"ollama_client: empty visible content after {thinking_chars} thinking "
        f"char(s); think={think!r} model={model!r}",
        file=sys.stderr,
        flush=True,
    )


def chat_stream(messages: list[dict], model: str | None = None,
                options: dict | None = None, timeout: int = 900,
                host: str | None = None, should_stop=None,
                tools: list | None = None,
                keep_alive: str | int | None = None,
                think: bool | None = None) -> Iterator[Union[str, ToolCall, StreamEnd]]:
    """Token stream for the GUI's live display.

    Yields strings (content tokens) during generation, then a single ToolCall
    object at the end if the model invoked tools instead of (or after) generating
    text, then exactly one ``StreamEnd`` trailer on the Ollama path. A turn that
    is purely tool calls produces no string tokens before the ToolCall —
    callers must handle an empty text accumulator in that case.

    ``ToolCall`` is yielded only when the model actually invoked tools.
    Never yield ``ToolCall(calls=[])`` as a telemetry trailer.

    ``think=False`` disables Qwen's optional thinking channel (same reason
    ``measure_ollama_kv_cache`` already sends it). Omit ``think`` to leave the
    server default.

    Stop is cooperative: the GUI's Stop button sets a flag; we check it after
    each chunk so the server thread actually exits instead of streaming into void.
    On Stop the Ollama path still yields one ``StreamEnd`` with best-effort
    counts so far (and ``chat_telemetry`` from the last parsed chunk if any),
    then returns — it does not wait for ``done=True``.
    """
    if _is_powerinfer_host(host):
        import powerinfer_client
        yield from powerinfer_client.chat_stream(
            messages, host=host or router.POWERINFER_PROXY_HOST,
            model=model or router.POWERINFER_MODEL_ALIAS,
            timeout=timeout, options=options, should_stop=should_stop)
        return
    opts = dict(DEFAULT_OPTIONS)
    opts.update(options or {})
    host = host or HOST
    payload: dict = {
        "model": model or pick_model(),
        "messages": messages,
        "stream": True,
        "options": opts,
    }
    if tools:
        payload["tools"] = tools
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    if think is not None:
        payload["think"] = think
    req = urllib.request.Request(
        f"http://{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    accumulated_calls: list[dict] = []
    visible_filter = _VisibleTextFilter()
    thinking_chars = 0
    visible_chars = 0
    raw_content_chars = 0
    last_chunk: dict | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise OllamaModelFailure(
                        f"Ollama model error at {host}: {chunk['error']}")
                last_chunk = chunk
                msg = chunk.get("message") or {}
                # Accumulate tool calls from any chunk. Most models emit them in
                # the final (done=True) chunk, but we handle early emission too.
                for tc in msg.get("tool_calls") or []:
                    # Normalise arguments to dict now so callers never see strings.
                    fn = tc.get("function") or {}
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"__invalid_tool_arguments__": args}
                    if not isinstance(args, dict):
                        args = {"__invalid_tool_arguments__": repr(args)}
                    accumulated_calls.append(
                        {"function": {"name": fn.get("name", ""), "arguments": args}})
                thinking_piece = msg.get("thinking") or ""
                if thinking_piece:
                    thinking_chars += len(thinking_piece)
                # ``content: null`` must not slip through as None (dict.get default
                # only applies when the key is missing). Count raw chars before the
                # visible filter so empty-content+nonzero-eval is distinguishable
                # from a filter swallow.
                content_piece = msg.get("content") or ""
                if not isinstance(content_piece, str):
                    content_piece = str(content_piece)
                raw_content_chars += len(content_piece)
                piece = visible_filter.feed(content_piece)
                if piece:
                    visible_chars += len(piece)
                    yield piece
                if should_stop is not None and should_stop():
                    flushed = visible_filter.finish()
                    if flushed:
                        visible_chars += len(flushed)
                        yield flushed
                    stop_unclosed = visible_filter.unclosed_hidden_chars()
                    yield StreamEnd(
                        chat_telemetry(last_chunk),
                        thinking_chars=thinking_chars + stop_unclosed,
                        visible_chars=visible_chars,
                        unclosed_think_chars=stop_unclosed,
                        raw_content_chars=raw_content_chars,
                    )
                    return
                if chunk.get("done"):
                    break
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code >= 500 or exc.code in (408, 429):
            raise OllamaModelFailure(f"Ollama HTTP {exc.code} at {host}: {detail}") from exc
        raise OllamaUnavailable(f"Ollama HTTP {exc.code} at {host}: {detail}") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise OllamaUnavailable(f"cannot reach Ollama at {host}: {exc}") from exc

    flushed = visible_filter.finish()
    if flushed:
        visible_chars += len(flushed)
        yield flushed

    unclosed_think_chars = visible_filter.unclosed_hidden_chars()
    if unclosed_think_chars:
        # A <think> opened in message.content and the stream ended (done=True
        # or the response iterator was exhausted) with no </think> ever seen.
        # Fold it into thinking_chars so this shape is not indistinguishable
        # from a truly silent model (0/0/0) — see StreamEnd's docstring.
        thinking_chars += unclosed_think_chars

    if thinking_chars and not visible_chars and not accumulated_calls:
        _log_empty_thinking(thinking_chars, think=think, model=payload.get("model"),
                             unclosed_think_chars=unclosed_think_chars)
    elif (not thinking_chars and not visible_chars and not accumulated_calls
          and raw_content_chars == 0):
        # Ollama reported generation (caller sees eval_count via StreamEnd
        # telemetry) but every message.content field was empty/null. Not a
        # filter bug — surface it so the operator path can tell "silent
        # content" from "swallowed content".
        tel = chat_telemetry(last_chunk)
        eval_count = tel.get("eval_count", 0)
        if eval_count:
            print(
                f"[ollama_client] empty content with eval_count={eval_count} "
                f"model={payload.get('model')!r} think={think!r} "
                f"raw_content_chars=0 filter_state={visible_filter.state!r}",
                file=sys.stderr,
                flush=True,
            )

    if accumulated_calls:
        yield ToolCall(accumulated_calls)
    yield StreamEnd(
        chat_telemetry(last_chunk),
        thinking_chars=thinking_chars,
        visible_chars=visible_chars,
        unclosed_think_chars=unclosed_think_chars,
        raw_content_chars=raw_content_chars,
    )


if __name__ == "__main__":
    print(f"host   : {HOST}")
    print(f"up     : {available()}")
    if available():
        print(f"models : {', '.join(models()) or '(none)'}")
        try:
            print(f"using  : {pick_model()}")
        except OllamaUnavailable as e:
            print(f"using  : ERROR {e}")
