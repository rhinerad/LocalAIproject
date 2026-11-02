"""Adapter contract. One class per provider; the dispatcher picks by name."""
from __future__ import annotations

from typing import Callable, Iterator, Protocol, runtime_checkable

from ..events import Done, TextDelta, ToolCalls

StreamPiece = TextDelta | ToolCalls | Done


@runtime_checkable
class ChatBackend(Protocol):
    """A provider the gateway can route a turn to.

    ``stream`` takes Ollama-shaped inputs (the same ``messages`` / ``tools`` /
    ``response_format`` / ``options`` that ``ollama_client.chat_stream``
    receives) and yields provider-neutral events. It must raise
    ``CloudUnavailable`` for any failure the local router should recover
    from, and must never raise a provider SDK exception.
    """

    name: str

    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | str | None = None,
        options: dict | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[StreamPiece]: ...

    def health(self) -> dict: ...
