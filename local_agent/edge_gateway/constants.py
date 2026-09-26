"""Caps and bind policy. Duplicated from the Termux contract on purpose so
this package never imports the farm bootstrap package.
"""
from __future__ import annotations

ALLOWED_JOB_KINDS = frozenset({"edge_text_inference"})
MAX_PROMPT_CHARS = 12_000
MAX_RESULT_CHARS = 16_000
MAX_TOKENS = 512
DEFAULT_MAX_TOKENS = 256
DEFAULT_LEASE_SECONDS = 300
MAX_LEASE_SECONDS = 900
MIN_TOKEN_CHARS = 24
MAX_JOB_ID_CHARS = 120
MAX_DEVICE_ID_CHARS = 64
# Worst-case UTF-8 JSON for a 12_000-character prompt or a 16_000-character
# result, including non-ASCII characters. The previous 65_536 cap rejected
# jobs the character caps claimed to allow.
MAX_BODY_BYTES = 262_144
# llama.cpp -c is the whole window, including tokens still to be generated.
CONTEXT_TOKENS = 512
PROMPT_CHARS_PER_TOKEN = 4
MAX_ACTIVE_JOBS = 32
JOB_RETENTION_DAYS = 14
WORKER_HEADER = "termux-powerinfer-contract-v1"
WORKER_HEADER_NAME = "X-Edge-Worker"

# G4: phone HTTPS 8743, admin loopback 8744. Not 6379/8188/11434/11435/8765.
PHONE_BIND_HOST = "10.90.91.1"
PHONE_PORT = 8743
ADMIN_BIND_HOST = "127.0.0.1"
ADMIN_PORT = 8744
PHONE_OVERLAY_CIDR = "10.90.91.0/30"
PHONE_PEER_HOST = "10.90.91.2"

FORBIDDEN_PORTS = frozenset({6379, 8188, 11434, 11435, 8765})
FARM_OVERLAY_PREFIX = "10.90.90."

COMPLETE_STATUSES = frozenset({
    "completed", "timed_out", "runtime_failed", "refused",
})

STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_COMPLETED = "completed"
STATE_REFUSED = "refused"
STATE_EXPIRED = "expired"

CLAIM_RATE_MAX = 20
CLAIM_RATE_WINDOW_SECONDS = 60


def prompt_fits_context(prompt: str, max_tokens: int) -> bool:
    """Reject a prompt that cannot share the fixed phone context with generation."""
    if not isinstance(prompt, str) or not isinstance(max_tokens, int):
        return False
    room = CONTEXT_TOKENS - max_tokens
    if room < 1:
        return False
    return len(prompt) <= room * PROMPT_CHARS_PER_TOKEN
