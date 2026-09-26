# 2026-09-03bc — Live farm-routing verify (prefetch consume, embed cap, stale fallback)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write:
**2026-09-03bc**.

Live-drive of `should_route`, `_maybe_start_farm_summary_prefetch`,
`try_summarize_on_farm`, and `EmbeddingScorer.vectors_for` →
`try_embed_on_farm` against `celery@Louises-MBP`. Unit tests were already
green; this is the first pass that actually submitted to the Mac worker
from this session. Evidence:
`local_agent/runtime/live_farm_routing_verify.json`.

Prefetch caller ceiling was already raised to 135s in
`CHANGELOG/2026-09-03bd_farm_offload_live_verify.md` (25s/90s both too
short vs worker 120s). This pass found two more live bugs behind those
passing unit tests.

## Results (second live run, after the fixes below)

| scenario | result | evidence |
|---|---|---|
| Prefetch, farm up | **PASS** | Hop loop fired prefetch. `try_summarize_on_farm` **120.05s**, `summarized=true`, model `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`. `_trim_context` **0.000s**, emit `farm CPU summary (model: …)`. One farm call; overflow did not wait on Celery. |
| Embed, farm up | **PASS** | `search_docs` with two real index ids dropped from cache. Farm returned **8** vectors in **12.88s** (cap, not the whole corpus). `n_results=3`. Not the 0.58s 2-chunk warm figure — nomic ran after a 120s summarize on the same `concurrency=1` worker. |
| Failure injection | **PASS** | Temp `FARM_STATUS_PATH` with `checked_at` 180s old (production daemon left running). Prefetch fired `farm-not-reachable`. Helper **0** calls. `search_docs` **0.99s**, no exception. Slot idle. |
| Reachability timing | **PASS** | `farm_reachable()` mean **0.123ms**, max **3.5ms** healthy; max **2.78ms** when stale. Snapshot `latency_ms` (Celery inspect in the daemon) **~2300ms**. `farm_health` was not imported on the hot path. |

First live run (before the two fixes): prefetch helper **None at 90.56s**; overflow continuity digest after local 12s; `search_docs` submitted the retrieval corpus, farm **TimeoutError at 30.68s**, then **279s** local embed (13 `_embed` batches). Inspect showed `embed_chunks` still active on the Mac with hundreds of chunks, `acknowledged=false`. Revoked `b137b91c-…`.

## Gaps that unit tests had not caught

1. **Unbounded farm embed.** `vectors_for` passed every stale chunk to
   `try_embed_on_farm`. A cold or hash-mismatched cache is ~1000 chunks.
   The 30s caller timeout returns `None` but the Celery task keeps running
   on `max-concurrency=1`, so later summarize/embed queue behind it.
   **Fix:** `FARM_EMBED_MAX_CHUNKS = 8`; only `{id, text}` is sent; the rest
   stay on local `_embed`.
2. **Failed prefetch pinned the fingerprint.** `try_summarize_on_farm`
   returning `None` stored `result=None` and left the fingerprint, so
   `maybe_start` never retried that slice.
   **Fix:** clear fingerprint on `None` / exception.

## Tests that would have caught them

- `TestEmbeddingScorerFarmRouting.test_caps_farm_embed_payload`
- `TestMaybeStart.test_farm_none_clears_fingerprint_so_same_slice_can_retry`

`python -m unittest local_agent.test_farm_offload local_agent.test_compaction_prefetch -v`
→ **82/82 OK** in 4.720s.

Re-run after fixes: `python local_agent/runtime/live_farm_routing_verify.py`
→ **all_pass=true** in 136.7s.

## Files

- `local_agent/farm_offload.py` — `FARM_EMBED_MAX_CHUNKS = 8`
- `local_agent/retrieval.py` — cap farm slice; send id+text only
- `local_agent/compaction_prefetch.py` — clear slot on None/exception
- `local_agent/test_farm_offload.py`
- `local_agent/test_compaction_prefetch.py`
- `local_agent/runtime/live_farm_routing_verify.py`
- `local_agent/runtime/live_farm_routing_verify.json`

Did not stop the production farm-status daemon. Did not start GPU/GUI.
`APP_REVISION` unchanged.
