"""Provider-neutral stream events.

The adapters yield these; ``local_agent/ollama_client.py`` converts them to its
own ``str`` / ``ToolCall`` / ``StreamEnd`` objects so ``agent.py`` never sees a
provider type. Keeping the gateway free of ``local_agent`` imports is what lets
a second adapter (another vendor, a local proxy) be dropped in later.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCalls:
    """Ollama-shaped calls: ``[{"id": ..., "function": {"name", "arguments"}}]``.

    ``arguments`` is always a dict. ``id`` is the provider's tool_use id and is
    kept on the call so a later hop can pair tool results to it.
    """
    calls: list[dict]


@dataclass
class Done:
    model: str
    stop_reason: str | None
    telemetry: dict = field(default_factory=dict)   # Ollama-named keys + "gateway"
    stopped: bool = False                           # cooperative stop fired


class CloudUnavailable(RuntimeError):
    """The cloud tier cannot serve this request. Callers fall back locally.

    ``kind`` is one of: offline, timeout, auth, rate_limit, server, refusal,
    bad_request, translation, sdk_missing, disabled.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.detail = message
