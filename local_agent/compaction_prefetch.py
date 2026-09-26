"""Proactive compaction prefetch — fire a background farm summarize job
when context approaches the threshold, so _trim_context can consume the
result instead of summarizing on the operator turn.

Farm summarize is prefetch-only. Overflow does not wait on Celery: consume()
returns a ready result or None, and _trim_context then uses the local CPU
summarizer. A down/stale farm_status.json snapshot makes try_summarize_on_farm
return None immediately (no helper wait). A farm timeout/None result
clears the fingerprint so the same slice can retry.

State machine (one slot, ignore-if-busy):

    IDLE
      → 80 % threshold crossed, no thread running → PREFETCHING

    PREFETCHING
      → farm returns result, fingerprint still matches → READY
      → farm returns None / errors / times out → IDLE
      → new call with different fingerprint while in-flight: ignored,
        result stored with original fingerprint (discarded at consume-time)

    READY
      → consume() called with matching fingerprint → IDLE (result returned)
      → consume() called with different fingerprint → IDLE (result discarded)

Both maybe_start() and consume() accept the summarizable slice directly,
not the full msgs list, so their fingerprints match even when the tail
grows between the trigger and the overflow.
"""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

PROACTIVE_THRESHOLD: float = 0.80

_state: dict[str, Any] = {
    "thread": None,      # threading.Thread | None — None means idle or done
    "result": None,      # dict | None — the raw farm result when ready
    "fingerprint": None, # str | None — sha1 of the slice it was built for
}
_lock = threading.Lock()


def fingerprint(summarizable: list[dict]) -> str:
    blob = json.dumps(
        [(m.get("role"), str(m.get("content", ""))[:120]) for m in summarizable],
        sort_keys=True,
    )
    return hashlib.sha1(blob.encode()).hexdigest()


def maybe_start(summarizable: list[dict]) -> None:
    """Fire a background farm summarize job if not already in flight.

    Returns immediately in all cases. Ignores the call if:
    - a job is already in flight (ignore-if-busy — no queueing)
    - the same fingerprint was already computed (deduplication)
    """
    if not summarizable:
        return
    fp = fingerprint(summarizable)

    def _bg() -> None:
        try:
            import farm_offload
            result = farm_offload.try_summarize_on_farm(summarizable)
            with _lock:
                if _state["fingerprint"] == fp:
                    if result is None:
                        # Timeout/unreachable: free the slot so a later
                        # maybe_start can retry this slice. Storing None
                        # used to pin the fingerprint forever.
                        _state["result"] = None
                        _state["fingerprint"] = None
                    else:
                        _state["result"] = result
        except Exception:
            with _lock:
                if _state["fingerprint"] == fp:
                    _state["result"] = None
                    _state["fingerprint"] = None
        finally:
            with _lock:
                _state["thread"] = None

    # Reserve the slot and publish the Thread object in the same critical
    # section. Releasing the lock before `_state["thread"] = t` let a second
    # maybe_start with a different fingerprint slip through and start a
    # second farm job (ignore-if-busy was not atomic).
    #
    # Thread() is object construction only (the OS thread is created in
    # start()). If either step raises — MemoryError on construction, or
    # RuntimeError from start() under thread exhaustion — roll the slot
    # back so later maybe_start/consume calls are not stuck behind a
    # reservation that will never complete. start() stays outside the
    # lock: a fast farm completion must not deadlock on _lock.
    t = None
    with _lock:
        if _state["thread"] is not None or _state["fingerprint"] == fp:
            return
        _state["fingerprint"] = fp
        _state["result"] = None
        try:
            t = threading.Thread(target=_bg, daemon=True, name="compaction-prefetch")
        except Exception:
            _state["fingerprint"] = None
            _state["result"] = None
            return
        _state["thread"] = t
    try:
        t.start()
    except Exception:
        with _lock:
            if _state["thread"] is t:
                _state["thread"] = None
                if _state["fingerprint"] == fp:
                    _state["fingerprint"] = None
                    _state["result"] = None


def consume(summarizable: list[dict]) -> dict | None:
    """Return and clear the ready result if the fingerprint matches, else None.

    Does not wait. If the background job is still in flight, or the
    fingerprint does not match (slice expanded since the prefetch fired),
    returns None immediately so the caller falls through to local CPU
    summarization. Overflow must not block on a farm round-trip.
    """
    if not summarizable:
        return None
    fp = fingerprint(summarizable)
    with _lock:
        if (
            _state["fingerprint"] == fp
            and _state["result"] is not None
            and _state["thread"] is None
        ):
            result = _state["result"]
            _state["result"] = None
            _state["fingerprint"] = None
            return result
    return None
