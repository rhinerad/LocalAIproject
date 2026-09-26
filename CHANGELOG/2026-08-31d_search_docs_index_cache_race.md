# 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution

## What changed

Found during a follow-up audit of the same-day parallel-tool-execution
change (`CHANGELOG/2026-08-31c_...md`), specifically auditing every tool
newly reachable from concurrent threads for thread-safety.

`retrieval._get_index()` did an unlocked check-then-build on the
module-level `_INDEX_CACHE` global:

```python
def _get_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = load_index()
    return _INDEX_CACHE
```

`search_docs` (which calls this) is in `tools.CONCURRENCY_SAFE_TOOLS`, so as
of yesterday's change it can now genuinely be called from several threads
at once in the same hop. With a cold cache, two threads could both see
`_INDEX_CACHE is None` and both call `load_index()`. `load_index()`, when
it detects changed source files, writes the rebuilt index to
`knowledge/retrieval_index.json` via `atomic_write_text()`
(`atomic_io.py`), which writes to a **fixed** temp path
(`retrieval_index.json.tmp`) and then `os.replace()`s it — not a
per-call-unique temp file. Two threads independently opening and writing
that same fixed temp path can interleave their writes and corrupt it
before either `os.replace()` fires, or at minimum "last `os.replace()`
wins" silently discards one thread's rebuilt index. `rebuild()` (used by
the `run_build` tool, sequential/not in the safe set) had the same
unlocked pattern and could race against a concurrent `search_docs` call
landing in the same hop, since the safe tools run in background threads
while sequential tools run on the main thread *at the same time*, not
before or after.

This is a genuine regression risk introduced by yesterday's parallel-tool
change, not a pre-existing bug — before that change, `search_docs` could
only ever be called once at a time (the hop loop was fully sequential), so
the race was structurally impossible.

## Fix

Added `retrieval._INDEX_LOCK = threading.Lock()`. `_get_index()` now does
proper double-checked locking (fast unlocked read when the cache is warm,
lock-protected check-and-build when cold), and `rebuild()` wraps its
reset-and-rebuild in the same lock, so a sequential `run_build("rebuild")`
call and concurrent `search_docs` calls always serialize against each
other rather than racing on `_INDEX_CACHE` or the on-disk index file.

## What was verified

- `python3 -m py_compile retrieval.py` — clean.
- `test_retrieval_relevance.py`'s existing 2 tests still pass unchanged.
- Standalone reproduction: 8 threads calling `_get_index()` concurrently
  against a cold cache and an artificially slowed `load_index()` — before
  the fix this would call the slow/racy build path up to 8 times with
  overlapping execution; after the fix it built exactly once, with no two
  threads ever inside the build section simultaneously (confirmed with an
  explicit overlap-detection counter, not just a call count).
- Added 2 permanent regression tests to `test_retrieval_relevance.py`
  (`RetrievalIndexConcurrencyTests`):
  `test_concurrent_get_index_builds_only_once` (8 concurrent callers on a
  cold cache, asserts exactly 1 build and no overlapping execution), and
  `test_rebuild_serializes_against_concurrent_get_index` (starts a slow
  `rebuild()` on a background thread, calls `_get_index()` from the main
  thread while it's mid-build holding the lock, and asserts the main
  thread blocks and then reuses `rebuild()`'s result rather than racing
  past it and rebuilding again with stale/fallback data).
- Full suite re-run after the fix: `test_retrieval_relevance` 4/4,
  `test_native_tool_calling` 38/38, `test_router_switching` 41/41,
  `test_subtask_dispatch` 8/8, `test_deep_research` 6/6, `test_run_code`
  14/14, `test_agentic_state` 11/11 — 122 tests total, 0 failures, 0
  errors.

## Audit note

The same pass checked the other 19 tools in `CONCURRENCY_SAFE_TOOLS` for
the same class of bug (unlocked lazy cache, shared temp file, global
mutation). All 19 were confirmed safe by reading the actual implementation:
`list_phone_schedules` and any writer it could race against already share
`phone_scheduler._LOCK`; `memory.py`'s reads/writes already go through
`atomic_write_text` so a reader never sees a torn file; `capabilities`'s
internal caches are either a thread-safe `lru_cache` or an idempotent
unlocked dict (redundant recomputation at worst, never corruption); the
remainder are pure file/JSON readers with no shared mutable state. Only
`search_docs` had a real hazard, now fixed.

## What is still unverified

Not yet run on the real Windows workstation.
