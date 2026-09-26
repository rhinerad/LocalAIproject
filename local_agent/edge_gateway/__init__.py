"""Workstation-only PowerInfer-2 edge gateway (Phase D v1).

Stdlib HTTP + SQLite. Does not load worker-farm broker or cipher material.
Disabled unless invoked with --listen. The Termux client is not started here.
"""

from .constants import (
    ADMIN_BIND_HOST,
    ADMIN_PORT,
    PHONE_BIND_HOST,
    PHONE_OVERLAY_CIDR,
    PHONE_PORT,
)

__all__ = [
    "ADMIN_BIND_HOST",
    "ADMIN_PORT",
    "PHONE_BIND_HOST",
    "PHONE_OVERLAY_CIDR",
    "PHONE_PORT",
]
