"""Anthropic Messages API adapter built on the official ``anthropic`` SDK.

The SDK is imported lazily so the rest of the gateway (config, policy,
translation) and the router hooks keep working on a machine where it is not
installed; ``health()`` reports that state instead of raising.

Credentials: the SDK resolves ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN``
itself. A custom ``base_url`` that is not the official endpoint (for example
Ollama's own ``/v1/messages`` on ``http://127.0.0.1:11435``) gets a placeholder
key when none is set, because such proxies accept but ignore the header.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Iterator

from .. import translate
from ..config import GatewayConfig
from ..events import CloudUnavailable, Done, TextDelta, ToolCalls

_THINKING_HINTS = ("thinking", "signature", "block_binding", "prefix")


class AnthropicBackend:
    name = "anthropic"

    def __init__(self, config: GatewayConfig):
        self.config = config
        self._client: Any = None

    # ── construction ─────────────────────────────────────────────────────

    def _sdk(self):
        try:
            import anthropic  # noqa: WPS433  (lazy on purpose)
        except ImportError as exc:
            raise CloudUnavailable(
                "sdk_missing",
                "the anthropic package is not installed; run "
                "`pip install -r model_gateway/requirements.txt`") from exc
        return anthropic

    def client(self):
        if self._client is None:
            anthropic = self._sdk()
            kwargs: dict[str, Any] = {
                "timeout": self.config.timeout_s,
                "max_retries": self.config.max_retries,
            }
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            if not self.config.credential_present and not self.config.is_official_endpoint:
                kwargs["api_key"] = "local-proxy"
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def health(self) -> dict:
        try:
            anthropic = self._sdk()
            version = getattr(anthropic, "__version__", "?")
            installed = True
        except CloudUnavailable:
            version, installed = None, False
        return {
            "backend": self.name,
            "sdk_installed": installed,
            "sdk_version": version,
            "endpoint": self.config.netloc,
            "credential_present": self.config.credential_present,
        }

    # ── request shaping (pure; unit-tested) ──────────────────────────────

    def build_request(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        response_format: dict | str | None,
        options: dict | None,
    ) -> dict:
        cfg = self.config
        opts = dict(options or {})
        try:
            system_text, msgs = translate.ollama_messages_to_anthropic(messages)
        except ValueError as exc:
            raise CloudUnavailable("translation", str(exc)) from exc
        if not msgs:
            raise CloudUnavailable("translation", "no user content to send")

        output_config: dict = {}
        fmt, note = translate.response_format_to_output_config(response_format)
        if fmt:
            output_config.update(fmt)
        if note:
            system_text = (system_text + "\n\n" + note).strip()

        effort = str(opts.get("effort") or cfg.heavy.effort)
        if cfg.send_effort and effort:
            output_config["effort"] = effort

        max_tokens = cfg.max_tokens
        for key in ("max_tokens", "num_predict"):
            try:
                requested = int(opts.get(key) or 0)
            except (TypeError, ValueError):
                requested = 0
            if requested > 0:
                max_tokens = max(256, min(cfg.max_tokens, requested))
                break

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }
        if system_text:
            block: dict = {"type": "text", "text": system_text}
            if cfg.prompt_cache:
                block["cache_control"] = {"type": "ephemeral"}
            params["system"] = [block]
        tool_defs = translate.ollama_tools_to_anthropic(tools, cache_last=cfg.prompt_cache)
        if tool_defs:
            params["tools"] = tool_defs
        if output_config:
            params["output_config"] = output_config
        # Ollama-only knobs (num_gpu, num_ctx, temperature, top_p, keep_alive,
        # think) are intentionally not forwarded: temperature/top_p are 400s on
        # the current API version and thinking is governed by effort.
        return params

    # ── streaming ────────────────────────────────────────────────────────

    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | str | None = None,
        options: dict | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[TextDelta | ToolCalls | Done]:
        anthropic = self._sdk()
        params = self.build_request(model=model, messages=messages, tools=tools,
                                    response_format=response_format, options=options)
        attempt = 0
        while True:
            attempt += 1
            try:
                yield from self._stream_once(anthropic, params, should_stop)
                return
            except anthropic.BadRequestError as exc:
                text = str(exc)
                lowered = text.lower()
                # A replayed thinking block the API no longer accepts (history
                # edited since it was produced). Retry once without the cached
                # raw blocks; nothing was yielded yet because 400s are decided
                # before any output.
                if attempt == 1 and any(h in lowered for h in _THINKING_HINTS):
                    translate.forget_raw_blocks()
                    params = self.build_request(model=model, messages=messages, tools=tools,
                                                response_format=response_format, options=options)
                    continue
                raise CloudUnavailable("bad_request", text[:500]) from exc

    def _stream_once(self, anthropic, params: dict, should_stop) -> Iterator[TextDelta | ToolCalls | Done]:
        client = self.client()
        started = time.monotonic_ns()
        first_delta: int | None = None
        stopped = False
        final = None
        try:
            with client.messages.stream(**params) as stream:
                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "text":
                        if first_delta is None:
                            first_delta = time.monotonic_ns()
                        yield TextDelta(str(getattr(event, "text", "") or ""))
                    if should_stop is not None and should_stop():
                        stopped = True
                        stream.close()
                        break
                if stopped:
                    final = stream.current_message_snapshot
                else:
                    final = stream.get_final_message()
        except anthropic.APITimeoutError as exc:
            raise CloudUnavailable("timeout", str(exc)[:300]) from exc
        except anthropic.APIConnectionError as exc:
            raise CloudUnavailable("offline", str(exc)[:300]) from exc
        except anthropic.AuthenticationError as exc:
            raise CloudUnavailable("auth", str(exc)[:300]) from exc
        except anthropic.PermissionDeniedError as exc:
            raise CloudUnavailable("auth", str(exc)[:300]) from exc
        except anthropic.RateLimitError as exc:
            raise CloudUnavailable("rate_limit", str(exc)[:300]) from exc
        except anthropic.BadRequestError:
            raise
        except anthropic.APIStatusError as exc:
            kind = "server" if getattr(exc, "status_code", 500) >= 500 else "bad_request"
            raise CloudUnavailable(kind, str(exc)[:300]) from exc

        ended = time.monotonic_ns()
        content = list(getattr(final, "content", None) or [])
        stop_reason = getattr(final, "stop_reason", None)
        model_used = str(getattr(final, "model", None) or params["model"])

        if stop_reason == "refusal":
            details = getattr(final, "stop_details", None)
            category = translate._get(details, "category") if details is not None else None
            raise CloudUnavailable("refusal", f"the cloud model declined this request"
                                              f"{f' ({category})' if category else ''}")

        calls = translate.blocks_to_ollama_calls(content)
        if calls:
            translate.remember_raw_blocks([c["id"] for c in calls], translate.serialize_blocks(content))
            yield ToolCalls(calls)

        telemetry = translate.usage_to_telemetry(
            getattr(final, "usage", None),
            total_ns=ended - started,
            eval_ns=(ended - first_delta) if first_delta else 0,
            model=model_used,
            stop_reason=stop_reason,
        )
        yield Done(model=model_used, stop_reason=stop_reason, telemetry=telemetry, stopped=stopped)
