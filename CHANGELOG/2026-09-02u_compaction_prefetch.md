# 2026-09-02 — compaction_prefetch: proactive pre-compaction trigger

## Scope

Closes the last open item in `TODO.md` Phase 2 item 5 ("Not built: agent.py-side
decision logic that proactively pre-compacts context before the window fills").
Implements the background-trigger design reviewed and confirmed before
implementation in this session. The existing synchronous path (`farm_offload.py`
→ `context_compactor`) is unchanged in behavior; this change only adds a faster
route in front of it.

## Design decisions

**Fingerprint on `summarizable`, not full `msgs`.** The trigger fires with the
current `msgs` as context, but new messages (tool results, model replies) may be
appended before `_trim_context` fires. Fingerprinting on the full `msgs` list
would discard the pre-fetched result even when only the tail grew and the
summarizable slice (the older messages being compacted) is identical.
Fingerprinting on `summarizable` means the result is reused whenever the slice
matches, and discarded correctly when the slice expanded (e.g., more messages
rotated into the "older" section).

**Shared helper `_summarizable_slice(msgs)`** — extracted from `_trim_context`
into a standalone function that both the trigger site (hop loop) and
`_trim_context` call. Without this, the trigger and the consumer would compute
their slices independently with the same algorithm but in separate contexts,
making any drift between them invisible. Using the same function guarantees
identical output for identical input.

**One-slot, ignore-if-busy.** The state machine holds one background result at
a time. If `maybe_start()` is called while a job is in flight, the call returns
immediately and the new slice is dropped. The in-flight result may become stale
(fingerprint mismatch at consume-time) — it will be discarded silently and the
synchronous path handles the overflow. No queueing, no cancellation: daemon
threads with a 25-second farm timeout exit naturally.

**No wait on consume.** `consume()` returns None immediately if the thread is
still running or the fingerprint doesn't match. The caller (`_trim_context`) then
proceeds with the existing synchronous `farm_offload.try_summarize_on_farm()` →
`context_compactor.summarize_old_messages()` chain. The turn is never blocked on
the background thread.

**80 % threshold.** `PROACTIVE_THRESHOLD = 0.80`. The trigger fires when
`prompt_tokens > 0.80 × num_ctx` but context has not yet overflowed. At mac_worker
warm-call latency (~18.5 s), an 80 % trigger gives roughly the time of one short
tool hop for the background job to complete. Cold-load calls (~55 s) will still
fall through to the synchronous path — the synchronous 25 s farm timeout fires
first, then local CPU runs. Lightweight turns skip the trigger entirely (they
don't use compaction).

**Module-level state** — matches the pattern used by `retrieval.py`'s
`_EMBED_CACHE` / `_EMBED_CACHE_LOCK`: mutable state protected by a threading.Lock,
stored at module scope so it persists across `answer()` calls. This is the first
cross-turn background-state pattern in `agent.py`; the design doc noted there was
no prior precedent to follow in the file.

## Files created

**`local_agent/compaction_prefetch.py`** — the state machine module:
- `fingerprint(summarizable) → str` — sha1 of role+first-120-chars per message
- `maybe_start(summarizable) → None` — fires background thread; ignore-if-busy
- `consume(summarizable) → dict | None` — returns ready result or None (no wait)
- `PROACTIVE_THRESHOLD = 0.80`
- Module-level `_state` dict + `_lock`

**`local_agent/test_compaction_prefetch.py`** — 30 tests (all pass):
- `TestFingerprint` (4): identical slices, different content, extra message,
  role change
- `TestMaybeStart` (7): starts thread, empty noop, ignore-if-busy, same
  fingerprint dedup, thread clears after completion, result stored on success,
  result discarded on fingerprint mismatch mid-flight
- `TestConsume` (6): idle returns None, empty returns None, thread in-flight
  returns None (scenario 2), fingerprint mismatch returns None (scenario 4),
  matching fingerprint returns and clears result (scenario 1),
  result not consumed twice
- `TestRoundTrip` (3): result available after thread completes (scenario 1 full),
  farm returns None → consume returns None (scenario 3), farm raises → consume
  returns None
- `TestSummarizableSlice` (5): returns list, only conversational roles,
  current turn excluded, empty for tiny list, consistent fingerprint with
  compaction_prefetch
- `TestTrimContextIntegration` (5): prefetch used when ready (scenario 1),
  synchronous farm called when no prefetch (scenario 2), local fallback when all
  farm paths return None (scenario 5), emit note includes farm model name,
  slice-expanded discard falls through to synchronous path (scenario 4)

## Files modified

**`local_agent/agent.py`**

1. Import added:
```python
import compaction_prefetch           # noqa: E402
```

2. `_summarizable_slice(msgs)` added before `_trim_context`:
```python
def _summarizable_slice(msgs: list[dict]) -> list[dict]:
    if len(msgs) <= 2:
        return []
    system_count = 0
    for m in msgs:
        if m.get("role") != "system":
            break
        system_count += 1
    body = msgs[system_count:]
    tail_start = _protected_tail_start(body)
    older = body[:tail_start]
    return [m for m in older if m.get("role") in {"user", "assistant", "tool"}]
```

3. In `_trim_context` — replaced inline summarizable computation and added
   consume-first logic:

Before:
```python
summarizable = [message for message in older
                 if message.get("role") in {"user", "assistant", "tool"}]
...
if enough_history:
    try:
        import farm_offload
        _fr = farm_offload.try_summarize_on_farm(summarizable)
        ...
    except Exception:
        pass
```

After:
```python
summarizable = _summarizable_slice(msgs)
...
if enough_history:
    _fr = compaction_prefetch.consume(summarizable)
    if _fr is None:
        try:
            import farm_offload
            _fr = farm_offload.try_summarize_on_farm(summarizable)
        except Exception:
            pass
    if _fr and _fr.get("summarized"):
        summary = _fr.get("summary")
        _farm_model = _fr.get("model")
```

4. In the hop loop — proactive trigger added in the `else` branch of the
   context-trim check:

```python
        num_ctx = effective_ctx
        if prompt_tokens > num_ctx:
            msgs = _trim_context(msgs, num_ctx, tool_schemas, emit)
        elif (not lightweight_turn and
              prompt_tokens > compaction_prefetch.PROACTIVE_THRESHOLD * num_ctx):
            _prefetch_sl = _summarizable_slice(msgs)
            if (len(_prefetch_sl) >= 2 and
                    sum(len(str(_m.get("content", ""))) for _m in _prefetch_sl) >= 600):
                compaction_prefetch.maybe_start(_prefetch_sl)
```

## What this does not do

- Does not cancel or replace an in-flight background job when a new slice is seen
  (ignore-if-busy — the stale result is discarded at consume-time).
- Does not wait for the background result under any circumstances. If not ready,
  the synchronous path runs.
- Does not change the behavior of `farm_offload.try_summarize_on_farm` or
  `context_compactor.summarize_old_messages` — those are unchanged.
- Does not pre-emptively decide *how much* to compact — the same summarizable
  slice selection logic (`_protected_tail_start`, role filter) drives the trigger
  and the actual compaction.
