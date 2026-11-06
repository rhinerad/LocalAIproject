# 2026-09-02 — farm_offload: workstation-side routing to summarize/embed queues

## Scope

Implements the "lightweight classifier" described in `HARNESS_OPTIMIZATION.md`
§4a: "a decision point in `agent.py` (or a small new module it calls into) that
chooses, for a given compaction or embedding need, whether to dispatch to the farm
or fall back to the existing local/CPU path." Closes the last open item in
`TODO.md` Phase 2 item 5 (Swarm offload to The Farm).

## Design decisions

**Subprocess, not a direct Celery import.** The main local-agent Python
environment does not have `celery[redis]` installed — only the farm venv does.
Rather than adding Celery as a dependency to the agent, `farm_offload.py` spawns
the farm venv's Python (`worker_farm/.venv/Scripts/python.exe`) running a thin
helper script (`_farm_submit_wait.py`) that handles the Celery import, task
submission, and result polling. Result JSON is returned via stdout. This keeps
the agent's dependency surface unchanged.

**Return None, never raise.** Both `try_summarize_on_farm()` and
`try_embed_on_farm()` are designed to be called unconditionally — any farm
problem (venv missing, broker down, Redis not running, timeout, task failure,
parse error) silently returns None. The caller treats None as "run locally."
This satisfies §4a's "never block a turn waiting on a farm round trip for
something the workstation can already do instantly."

**Caller-side timeouts.** Configured conservatively: 25s for summarize (enough
for a warm mac_worker call at ~18.5s; cold model load at ~55s triggers local
fallback), 30s for embed (warm embed is ~0.58s). These are the *caller's*
ceiling; the farm task's own `_SUMMARIZE_TIMEOUT_S = 120` is irrelevant from
the caller's perspective.

**3-pass lock restructure in `EmbeddingScorer.vectors_for`.** The original code
held `_EMBED_CACHE_LOCK` throughout the embedding computation (including during
blocking Ollama network calls). Adding a 30s farm call while holding the lock
would be worse. The new structure: (1) read cache + identify stale chunks under
lock; (2) call farm/local `_embed` outside the lock; (3) write new vectors back
under lock. Two concurrent calls may now both embed the same stale chunks, but
the second write is idempotent (same hash → same vector), so this is correct.

## Files created

**`local_agent/farm_offload.py`** — main module imported by `agent.py` and
`retrieval.py`. Provides:
- `try_summarize_on_farm(messages, timeout_s=25.0) → dict | None`
- `try_embed_on_farm(chunks, timeout_s=30.0) → dict[str, list[float]] | None`
- `_run_helper(request, timeout_s) → dict | None` — common subprocess driver
- `_farm_venv_present() → bool` — guard before attempting subprocess

**`local_agent/worker_farm/_farm_submit_wait.py`** — farm-venv helper script.
Protocol: reads `{"task", "queue", "envelope", "timeout_s"}` from stdin; loads
`FARM_BROKER_URL` etc. from the sibling `.env` file; imports and uses Celery to
submit and wait; prints result JSON to stdout (exit 0) or `{"error": "..."}` to
stdout (exit 0, so the caller falls back gracefully); exits 1 only for fatal
configuration/import failures.

**`local_agent/test_farm_offload.py`** — 22 tests (all pass):
- `TestTrySummarizeOnFarm` (8): success, subprocess failure, timeout, venv
  missing, non-JSON stdout, error-key passthrough, model-not-installed result
  passthrough, empty input, correct task/queue in request
- `TestTryEmbedOnFarm` (5): success, subprocess failure, missing vectors key,
  empty input, correct task/queue/envelope in request
- `TestEmbeddingScorerFarmRouting` (4): farm used for stale chunks, local
  fallback on None, farm called only for stale (cache-hit chunks skip it),
  partial-farm-miss falls through to local — all with mocked `_load_embedding_cache`
  and `_save_embedding_cache` so disk state doesn't pollute tests
- `TestTrimContextFarmRouting` (4): farm summary used when available, local
  fallback on None, local fallback on `summarized: false`, local fallback on
  `ImportError`

## Files modified

**`local_agent/test_retrieval_embeddings.py`** — `_TempCache` context manager
updated to also patch `farm_offload.try_embed_on_farm` → None. Required because
`vectors_for()` now tries the farm before local `_embed()`, and when mac_worker
is live it returns real nomic-embed-text vectors that don't match the fixed mock
values the existing tests set up via `ollama_client.embed`. `_TempCache` was
already the right place for this: it's already responsible for isolating all
other embedding state (temp file, cache pointer). Adding the farm patch here
keeps all 15 existing retrieval tests hermetic with no per-test changes needed.

**`local_agent/agent.py`** — `_trim_context` (line ~939):

Before:
```python
summary = context_compactor.summarize_old_messages(summarizable) if enough_history else None
...
method = "a CPU summary" if summary else "a short continuity record"
```

After:
```python
summary = None
_farm_model: str | None = None
if enough_history:
    try:
        import farm_offload
        _fr = farm_offload.try_summarize_on_farm(summarizable)
        if _fr and _fr.get("summarized"):
            summary = _fr.get("summary")
            _farm_model = _fr.get("model")
    except Exception:
        pass
    if summary is None:
        summary = context_compactor.summarize_old_messages(summarizable)
...
if _farm_model:
    method = f"a farm CPU summary (model: {_farm_model})"
elif summary:
    method = "a local CPU summary"
else:
    method = "a short continuity record"
```

**`local_agent/retrieval.py`** — `EmbeddingScorer.vectors_for`: restructured
from a single lock-held block to a 3-pass pattern. The new pass 2:
```python
try:
    import farm_offload
    fv = farm_offload.try_embed_on_farm(stale)
    if fv:
        new_vectors.update(fv)
except ImportError:
    pass
local_stale = [ch for ch in stale if ch["id"] not in new_vectors]
# ... local _embed for local_stale ...
```

## What this does not do

- Does not check which workers are online before submitting — the helper script
  handles connection failure transparently via the error-key return path.
- Does not pre-emptively compact context before the window fills. Compaction is
  still reactive (triggered at overflow). Farm routing is therefore synchronous
  from the turn's perspective — it only helps when the warm-call latency
  (~18.5s on mac_worker) is acceptable as part of a blocking compaction event.
  A proactive pre-compaction path is noted in `TODO.md` as a separate, larger
  design.
- Does not add any new dependency to the agent's own Python environment.
