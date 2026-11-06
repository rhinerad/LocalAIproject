# 2026-09-03aw — agent.py farm-routing caller (farm_status.json gate)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately
before write: **2026-09-03aw** (`au` is WSL delayed-login watchdog; `av`
already claimed by a parallel session).

The 2026-09-02 handoff's remaining gap: summarize/embed queues were live on
`mac_worker`, but docs still said nothing in `agent.py` decided farm vs local,
and `ARCHITECTURE.md` / the runbooks still said the hot path did not consult
`farm_status.json`. Submit wrappers (`farm_offload.try_*`, prefetch, embed
3-pass lock) already existed (`2026-09-02s` / `2026-09-02u`). This pass is
the classifier and the latency rule, plus making that the documented source
of truth.

## Architecture decision

HARNESS_OPTIMIZATION.md §4a asked for a lightweight classifier and "never
block a turn waiting on a farm round trip for something the workstation can
already do instantly." Live Celery `inspect.ping()` is 1–5s and needs the
farm venv, so the hot path does **not** call `farm_health.check_farm_health`.
It reads `farm_status.json` — the same snapshot the dashboard overall block
uses, written by `farm_status_daemon` from `check_farm_health`.

Reachable = snapshot exists, `checked_at` not older than 90s, `status=="ok"`.
That is the inverse of `dashboard.collect.is_farm_degraded`. Missing, stale,
or non-ok → run locally immediately (no 25–30s helper timeout).

Latency (CHANGELOG/2026-09-02r, 2019 Intel Mac CPU):

| path | farm | local |
|---|---|---|
| summarize | warm ~18.5s, cold ~55s | 12s CPU timeout |
| embed | warm ~0.58s | workstation nomic-embed-text |

Therefore:

- **summarize** is prefetch-only. `should_route("summarize", blocking=True)`
  is always False. Overflow in `_trim_context` consumes a ready prefetch or
  goes local; it never submits to Celery.
- **embed** may block `search_docs` when reachable (0.58s warm). A down farm
  skips Celery and `_embed()` runs locally.

`None` / `{"summarized": false}` / any exception still fall back locally —
same graceful-degradation pattern as the rest of this tree.

## What changed this pass

- `farm_offload.py` — `STALE_AFTER_S` / `is_stale` imported from
  `worker_farm.dashboard.collect` (one definition, not a copy).
- `agent.py` — named decision helper `_maybe_start_farm_summary_prefetch`
  (slice size + `should_route(summarize, blocking=False)` +
  `compaction_prefetch.maybe_start`). Hop loop calls it at 80% ctx.
- Tests: hop-loop skip when farm unreachable; `vectors_for` skip when
  `should_route` is false; `farm_reachable()` agrees with dashboard
  `is_farm_degraded` inverted.
- Docs that still said "not wired" / "not built yet" corrected:
  `docs/ARCHITECTURE.md`, `docs/FARM_HEALTH_RUNBOOK.md`, `docs/RUNBOOK.md`,
  `worker_farm/README.md`, `farm_health.py` / `tasks.py` docstrings,
  `TODO.md` Phase 2 item 5 header.

No live Celery job submitted this pass. No GPU. `APP_REVISION` unchanged.

## Tests

From the repository root, system Python 3.12.10 (not farm venv):

```
python -m unittest local_agent.test_farm_offload local_agent.test_compaction_prefetch local_agent.test_retrieval_embeddings -v
```

**90 ran, 0 failed** in 5.344s (was 87 before this pass). New:

- `TestLiveHopLoop.test_prefetch_skipped_when_farm_unreachable`
- `TestEmbeddingScorerFarmRouting.test_skips_farm_when_should_route_false`
- `TestFarmReachable.test_reachable_matches_dashboard_overall_not_degraded`

## Files

- `local_agent/farm_offload.py`
- `local_agent/agent.py`
- `local_agent/test_farm_offload.py`
- `local_agent/test_compaction_prefetch.py`
- `local_agent/worker_farm/farm_health.py`
- `local_agent/worker_farm/tasks.py`
- `local_agent/worker_farm/README.md`
- `docs/ARCHITECTURE.md`
- `docs/FARM_HEALTH_RUNBOOK.md`
- `docs/RUNBOOK.md`
- `TODO.md`
- `CHANGELOG/README.md`
