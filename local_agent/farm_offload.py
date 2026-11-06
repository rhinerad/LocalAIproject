"""Workstation-side routing to the optional worker farm.

HARNESS_OPTIMIZATION.md §4a classifier + Celery submit wrappers.

farm_reachable() / should_route() are the decision point. They read the same
farm_status.json snapshot the dashboard uses (written by farm_status_daemon
from farm_health.check_farm_health). They never call Celery inspect live —
that takes 1–5s and needs the farm venv. A stale or non-ok snapshot means
"run locally," matching is_farm_degraded() on the dashboard overall block.

try_summarize_on_farm() / try_embed_on_farm() submit via the farm venv's
Python (worker_farm/.venv) running _farm_submit_wait.py. The main agent env
does not install celery[redis]. Both return None on any problem and never
raise. Callers treat None as "run locally."

Latency (CHANGELOG/2026-09-02r, mac_worker 2019 Intel CPU):
  summarize warm ~18.5s, cold ~55s (mistral-nemo-abliterated 6.8 GB load)
  local summarize timeout 12s (context_compactor)
  embed warm ~0.58s

So: farm summarize is prefetch-only (background, not on the operator turn).
should_route("summarize", blocking=True) is always False. Overflow in
agent._trim_context consumes a ready prefetch or goes local immediately.
Prefetch waits up to PREFETCH_SUMMARIZE_TIMEOUT_S (135s, above the worker's
120s Ollama ceiling) so a slow Mac call can finish in the background;
overflow still does not wait.
Farm embed may block the search_docs turn when reachable (0.58s); a down
farm skips the 30s timeout and goes local immediately.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from worker_farm.dashboard.collect import (
    STALE_AFTER_S as STATUS_STALE_AFTER_S,
    is_stale as snapshot_is_stale,
)

_log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
# Farm venv Python — platform-specific Scripts/bin path.
if platform.system() == "Windows":
    _FARM_VENV_PYTHON = _HERE / "worker_farm" / ".venv" / "Scripts" / "python.exe"
else:
    _FARM_VENV_PYTHON = _HERE / "worker_farm" / ".venv" / "bin" / "python"
_SUBMIT_HELPER = _HERE / "worker_farm" / "_farm_submit_wait.py"
_DEFAULT_STATUS_PATH = _HERE / "worker_farm" / "farm_status.json"

# Same 90s bound as the dashboard overall block (imported, not copied).
STATUS_PATH_ENV = "FARM_STATUS_PATH"

KIND_SUMMARIZE = "summarize"
KIND_EMBED = "embed"
KIND_QWYTHOS = "qwythos"

# Caller-side timeout ceilings (the farm task itself has a longer internal
# ceiling — 120s for summarize). These are how long we wait before giving up
# and falling back to the local path.
#
# Blocking summarize never routes (should_route(..., blocking=True) is False)
# because warm ~18.5s / cold ~55s would stall the operator turn. Prefetch is
# a background thread, so it MUST outlast a Mac cold load — a 25s ceiling
# (the old blocking cutoff) times out the first call of a session and the
# overflow path never sees a farm result. Live 2026-09-03: prefetch fired at
# 0.817×num_ctx, helper returned None at 25.6s, _trim_context ran local.
SUMMARIZE_TIMEOUT_S: float = 25.0  # blocking ceiling; not used for prefetch
# Must exceed worker_farm.tasks._SUMMARIZE_TIMEOUT_S (120). Live 2026-09-03:
# warmup summarize returned at 90.3s; a 90s caller ceiling then timed out
# the prefetch helper (none=true at 91s) and overflow ran local.
PREFETCH_SUMMARIZE_TIMEOUT_S: float = 135.0
# Embed: warm 2-chunk is ~0.58s; 30s absorbs model load on first call.
EMBED_TIMEOUT_S: float = 30.0
# Qwythos-9B on the 2019 Intel Mac: allow a cold load. Same worker queue as
# summarize so concurrency=1 cannot hold Qwythos and mistral-nemo together.
QWYTHOS_TIMEOUT_S: float = 90.0
# Interactive search_docs: farm at most this many stale chunks; the rest
# stay local. Submitting the whole retrieval corpus occupied mac_worker
# for minutes after the 30s caller timeout (live 2026-09-03).
FARM_EMBED_MAX_CHUNKS: int = 8


def status_path() -> Path:
    """farm_status.json path. Honors FARM_STATUS_PATH, same env as the daemon."""
    raw = (os.environ.get(STATUS_PATH_ENV) or "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_STATUS_PATH


def read_status_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    """Load farm_status.json. None on missing/unreadable/non-object. Never raises."""
    dest = Path(path) if path is not None else status_path()
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def farm_reachable(path: Path | None = None, now: datetime | None = None) -> bool:
    """True when the dashboard overall block would be healthy.

    Healthy = snapshot exists, not stale (90s), status == "ok".
    Same rule as dashboard.collect.is_farm_degraded inverted: the only
    healthy case is status=="ok" and not stale. Does not add a latency
    cutoff or a missing-task check (dashboard explicitly does not).
    """
    data = read_status_snapshot(path)
    if not data:
        return False
    if snapshot_is_stale(data.get("checked_at"), now=now):
        return False
    status = str(data.get("status") or "").strip().lower()
    return status == "ok"


def should_route(
    kind: str,
    *,
    blocking: bool = False,
    path: Path | None = None,
    now: datetime | None = None,
) -> bool:
    """HARNESS §4a classifier: farm-eligible vs local.

    Farm-eligible when:
      - kind is summarize or embed (CPU-only, no live-turn GPU/state)
      - farm_reachable()
      - not a blocking summarize (warm ~18.5s / cold ~55s would stall
        the operator turn; local summarizer is a 12s CPU call)

    blocking=True means the caller would wait on the farm before continuing
    the operator turn. Prefetch passes blocking=False. Embed on search_docs
    is blocking but cheap when warm (~0.58s), so it may route.
    """
    if kind not in {KIND_SUMMARIZE, KIND_EMBED, KIND_QWYTHOS}:
        return False
    if kind == KIND_SUMMARIZE and blocking:
        return False
    return farm_reachable(path=path, now=now)


def _farm_venv_present() -> bool:
    return _FARM_VENV_PYTHON.is_file() and _SUBMIT_HELPER.is_file()


def _run_helper(request: dict[str, Any], timeout_s: float) -> dict | None:
    """Spawn the farm-venv helper, feed it a JSON request, return parsed response.

    Returns None on any error: missing venv, subprocess failure, parse error,
    or timeout. Always safe to call — never raises.
    """
    if not _farm_venv_present():
        return None
    try:
        proc = subprocess.run(
            [str(_FARM_VENV_PYTHON), str(_SUBMIT_HELPER)],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout_s + 15,  # outer shell timeout; inner Celery timeout is timeout_s
        )
    except subprocess.TimeoutExpired:
        _log.debug("farm_offload: subprocess timed out (%s)", request.get("task"))
        return None
    except OSError as exc:
        _log.debug("farm_offload: subprocess launch failed: %s", exc)
        return None
    if proc.returncode != 0:
        _log.debug("farm_offload: helper exited %d stderr=%s",
                   proc.returncode, proc.stderr[:300])
        return None
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _log.debug("farm_offload: stdout not JSON: %r", proc.stdout[:200])
        return None
    if "error" in result:
        _log.debug("farm_offload: helper error: %s", result["error"])
        return None
    return result


def try_summarize_on_farm(
    messages: list[dict],
    timeout_s: float | None = None,
    *,
    blocking: bool = False,
) -> dict | None:
    """Submit messages to the farm's summarize queue; return the task result or None.

    Prefetch-only by default (blocking=False). agent._trim_context must not
    call this on the operator turn — should_route(summarize, blocking=True)
    is False even when the farm is healthy.

    Result shape on success: {"summarized": True, "summary": {...}, "model": "..."}.
    Result shape when the worker has no model: {"summarized": False,
    "model_expected": "...", "note": "..."}.
    Returns None on farm errors/timeouts/unhealthy snapshot (not on
    model-not-installed results). Callers must check result["summarized"]
    to know whether a usable summary was actually produced.
    """
    if not messages:
        return None
    if not should_route(KIND_SUMMARIZE, blocking=blocking):
        return None
    if timeout_s is None:
        timeout_s = (
            SUMMARIZE_TIMEOUT_S if blocking else PREFETCH_SUMMARIZE_TIMEOUT_S
        )
    return _run_helper(
        {
            "task": "local_agent.worker_farm.tasks.summarize_conversation",
            "queue": "summarize",
            "envelope": {"messages": messages},
            "timeout_s": timeout_s,
        },
        timeout_s,
    )


def try_embed_on_farm(
    chunks: list[dict],
    timeout_s: float = EMBED_TIMEOUT_S,
) -> dict[str, list[float]] | None:
    """Submit chunks to the farm's embed queue; return {chunk_id: vector} or None.

    Chunks must be a list of {"id": str, "text": str} dicts. Returns None on any
    farm problem (unreachable snapshot, venv missing, broker down, timeout,
    task error). Never raises. Skips the Celery wait entirely when
    farm_reachable() is False so a down farm does not stall search_docs.
    """
    if not chunks:
        return None
    if not should_route(KIND_EMBED, blocking=True):
        return None
    result = _run_helper(
        {
            "task": "local_agent.worker_farm.tasks.embed_chunks",
            "queue": "embed",
            "envelope": {"chunks": chunks},
            "timeout_s": timeout_s,
        },
        timeout_s,
    )
    if result is None:
        return None
    vectors = result.get("vectors")
    if not isinstance(vectors, dict):
        return None
    return vectors or None


def try_qwythos_on_farm(
    messages: list[dict],
    tools: list | None = None,
    timeout_s: float | None = None,
) -> dict | None:
    """One lightweight evaluation turn on Mac Qwythos via existing Celery.

    Uses the live ``summarize`` queue so the Mac worker (concurrency=1) cannot
    run Qwythos beside mistral-nemo. Returns None on any farm problem; callers
    fall back to local CPU. Success shape: {content, tool_calls, model}.
    """
    if not messages:
        return None
    if not should_route(KIND_QWYTHOS, blocking=True):
        return None
    if timeout_s is None:
        timeout_s = QWYTHOS_TIMEOUT_S
    return _run_helper(
        {
            "task": "local_agent.worker_farm.tasks.qwythos_evaluate",
            "queue": "summarize",
            "envelope": {"messages": messages, "tools": tools or []},
            "timeout_s": timeout_s,
        },
        timeout_s,
    )
