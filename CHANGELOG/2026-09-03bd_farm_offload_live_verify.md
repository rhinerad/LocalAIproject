# 2026-09-03bd — Live farm_offload routing verify (real Mac worker)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately
before write: **2026-09-03bd**.

Live-verify of `farm_offload.should_route` / prefetch / embed / stale
fallback against `celery@Louises-MBP`, not the 90 unit tests. Four
scenarios, reported separately.

## Results

| scenario | result | evidence |
|---|---|---|
| D healthy consistency | **PASS** | `farm_reachable()=True` and dashboard `is_farm_degraded()=False` on the live `farm_status.json` (`status=ok`, `celery@Louises-MBP`) |
| B embed blocking | **PASS** | `EmbeddingScorer.vectors_for` submitted `embed_chunks`; local `_embed` not called; **0.953s** wall clock; `nomic-embed-text:latest`; 768-dim. Farm-task ~0.58s plus helper subprocess |
| A prefetch consume-win | **PASS** (after timeout fix) | Hop loop fired at **0.817×num_ctx** (2042/2500). Background `summarize_conversation` completed in **117.3s**, model `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`. `_trim_context` emit: `farm CPU summary (model: …)`. Local summarizer **0** calls |
| C failure injection | **PASS** | Stopped `\local-agent-farm-status-daemon`, wrote `checked_at` 91s old. Prefetch did not start. Helper **0** calls. Overflow used local CPU summary in **0.0s**. Embed used local `_embed` in **0.0s**. No exception. Prefetch slot `thread is None` |
| D stale consistency | **PASS** | Same moment as C: `farm_reachable()=False` and `is_farm_degraded()=True`. Daemon restore: Start-ScheduledTask rc=0, snapshot reachable again |

Command:

```
python -m unittest local_agent.test_farm_offload_live -v
```

4/4 OK in 121.5s (system Python 3.12.10). Worker `max-concurrency=1` — summarize and embed share one prefork child.

## Gap found and fixed

First live prefetch (25s caller ceiling from 2026-09-02s) fired at 0.817 then overflow ran local at **25.6s**. Helper returned `None`. Mac cold/slow summarize is ~90–117s, not the 18.5s warm-inference figure from `2026-09-02r` (that was inference-only after load). A 25s ceiling makes every first-of-session prefetch miss.

Prefetch is a background thread and must not use the old blocking cutoff. `PREFETCH_SUMMARIZE_TIMEOUT_S = 135` (above `worker_farm.tasks._SUMMARIZE_TIMEOUT_S = 120`). Overflow still does not wait.

With 135s, the consume-win path succeeded at 117s. Client-side timeouts while the worker is still running leave `summarize_conversation` active (`concurrency=1`); later calls queue behind it. Drain before a live re-run.

## Tests that would have caught it

- `TestTrySummarizeOnFarm.test_prefetch_timeout_covers_mac_cold_start` — default non-blocking helper `timeout_s >= 120` and equals `PREFETCH_SUMMARIZE_TIMEOUT_S`.
- `local_agent/test_farm_offload_live.py` — real Mac worker; skips if `farm_status.json` is not reachable.

Unit suite after the fix: `test_farm_offload` + `test_compaction_prefetch` **82/82 OK** in 4.7s.

## Files

- `local_agent/farm_offload.py` — `PREFETCH_SUMMARIZE_TIMEOUT_S = 135`
- `local_agent/test_farm_offload.py` — timeout regression
- `local_agent/test_farm_offload_live.py` — live scenarios
- `docs/ARCHITECTURE.md`

No GPU. `APP_REVISION` unchanged. Farm-status daemon left writing (`farm_status.json` `status=ok` after restore).
