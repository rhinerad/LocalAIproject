"""Adapter registry. ``get_backend("anthropic")`` is the only entry point."""
from __future__ import annotations

from typing import Callable

from ..config import GatewayConfig
from .base import ChatBackend

_FACTORIES: dict[str, Callable[[GatewayConfig], ChatBackend]] = {}


def register(name: str, factory: Callable[[GatewayConfig], ChatBackend]) -> None:
    _FACTORIES[name] = factory


def get_backend(name: str, config: GatewayConfig) -> ChatBackend:
    if name not in _FACTORIES:
        if name == "anthropic":
            from .anthropic_backend import AnthropicBackend
            register("anthropic", AnthropicBackend)
        else:
            raise KeyError(f"no gateway adapter registered for backend {name!r}")
    return _FACTORIES[name](config)


def registered() -> list[str]:
    return sorted(set(_FACTORIES) | {"anthropic"})
