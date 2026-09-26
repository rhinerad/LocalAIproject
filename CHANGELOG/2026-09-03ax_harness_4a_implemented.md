# 2026-09-03ax — HARNESS_OPTIMIZATION.md §4a marked implemented

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write:
**2026-09-03ax**.

## Why

The farm-routing caller this document originally proposed is already in
`agent.py` / `farm_offload.py` (`CHANGELOG/2026-09-03aw_farm_routing_caller.md`).
The 2026-09-02 spec still said "nothing in agent.py decides farm vs local"
and "does not implement anything," which is how this task got re-issued.
No new routing code — the live picture is `docs/ARCHITECTURE.md`.

Independently re-ran from the repository root (system Python 3.12):

```
python -m unittest local_agent.test_farm_offload local_agent.test_compaction_prefetch local_agent.test_retrieval_embeddings -v
```

**90 ran, 0 failed** in 5.387s. Farm-available and farm-unavailable paths
both covered (`should_route` true/false, prefetch skip when unreachable,
`vectors_for` skip when `should_route` is false, overflow never waits on
Celery).

## Decision (unchanged from 2026-09-03aw)

Mac cold-start ~55s / warm summarize ~18.5s vs local 12s: **summarize is
prefetch-only**. `should_route("summarize", blocking=True)` is always
False. Overflow consumes a ready `compaction_prefetch` result or goes
local. Embed may block `search_docs` when reachable (warm ~0.58s); a down
`farm_status.json` skips Celery and `_embed()` runs locally.

## Files

- `HARNESS_OPTIMIZATION.md` (status banner, gap 1 closed, audit row, footer)
- `CHANGELOG/README.md`

No `outputs/equal_shares/`. APP_REVISION unchanged. GUI/GPU/farm not started.
