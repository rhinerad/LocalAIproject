"""G9: structured logs are ids and sizes only. Prompt/result keys are refused."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

ALLOWED_LOG_KEYS = frozenset({
    "event",
    "device_id",
    "job_id",
    "status",
    "state",
    "prompt_chars",
    "result_chars",
    "peer_ip",
    "http_status",
    "path",
    "reason",
})

_FORBIDDEN_VALUE_KEYS = frozenset({"prompt", "result", "token", "untrusted_result"})


class EdgeLogError(ValueError):
    """Raised when a caller tries to log a forbidden field."""


def edge_log(event: str, **fields) -> str:
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat()}
    for key, value in fields.items():
        if key in _FORBIDDEN_VALUE_KEYS or key not in ALLOWED_LOG_KEYS:
            raise EdgeLogError(f"log field not allowed: {key}")
        if key in {"prompt_chars", "result_chars", "http_status"}:
            payload[key] = int(value)
        else:
            payload[key] = "" if value is None else str(value)
    line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sys.stderr.write(line + "\n")
    sys.stderr.flush()
    return line
