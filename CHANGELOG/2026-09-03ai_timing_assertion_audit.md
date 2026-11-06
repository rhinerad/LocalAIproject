# 2026-09-03ai — Timing-assertion audit (no code change)

Follow-up to `2026-09-03ag_parallel_hop_timing_assertion.md`. Searched every
`test_*.py` under `local_agent/`, `local_agent/worker_farm/`, `work/`, and
`tools/powerinfer/` for wall-clock concurrency/performance assertions
(`time.monotonic`, `perf_counter`, `assertLess(elapsed, …)`). Did not change
production or test code: the only same-class failure was the one already
rewritten in 2026-09-03ag.

## What counts as the bug class

A test that claims to verify concurrency or a tight latency property by
timing a wrapper that also pays unrelated work (GPU telemetry, prefetch,
prompt assembly, live HTTP), so the bound can fail while the behavior under
test is fine — or pass a serialized implementation if the bound is loosened
past the sequential floor.

Join timeouts, `Event.wait`, mocked clocks, and data-age checks are not
that class.

## Tests that actually time wall-clock

### 1. `test_native_tool_calling.test_concurrency_safe_tools_run_in_parallel_within_one_hop`

Already fixed in 2026-09-03ag. Timed `answer()` end-to-end (`< 0.55`) instead
of the two 0.3s tool bodies. Not revisited.

### 2. `test_subtask_dispatch.test_workers_run_concurrently_and_preserve_order`

Same *shape* (elapsed bound + overlap): three 0.2s mocked `oll.chat` calls,
`assertLess(elapsed, 0.4)` around `sd.dispatch()`, plus
`min(ends) > max(starts)`.

Not the same mismatch. `dispatch()` is the concurrency primitive. The test
mocks `_installed` (the `/api/tags` probe) and `oll.chat`. The timed span is
validation + `ThreadPoolExecutor` + the three sleeps — no GPU, no prefetch,
no `answer()`.

Measured 40 isolated runs on DuranGamingPC:

| | min | p50 | max |
|---|---|---|---|
| `dispatch()` elapsed | 0.187s | 0.203s | 0.266s |
| worker window | 0.187s | 0.203s | 0.250s |
| overlap | 40/40 | | |
| `elapsed >= 0.4` | 0/40 | | |

Overhead over the 0.2s sleep is at most 66ms; the 0.4s bound still sits
134ms above the worst sample and 200ms below sequential (0.6s). Left as-is.

### 3. `test_native_tool_calling.test_varying_exception_args_sig_hits_max_tool_hops_instead_of_hanging`

`assertLess(elapsed, 5.0)` around `answer()`. This is a hang detector, not a
concurrency discriminator. The real checks are hop counts
(`MAX_TOOL_HOPS + 1` model turns, `MAX_TOOL_HOPS` tool raises) and a
"hop limit" note. Measuring `answer()` is the property (did the loop
return).

8 runs: first 3.829s (cold `answer()` / GPU telemetry), then 0.125–0.188s.
All under 5.0. Not rewritten: a first-run 3.8s against a 5s hang ceiling is
not the 0.55-vs-overlap failure mode.

## Timed but not this class

| test | what the clock is for |
|---|---|
| `test_status_cache` | `monotonic` is **mocked** (100 vs 101 / 103) to prove TTL; probe counts, not duration |
| `test_compaction_prefetch._wait_for_idle` | poll until the background slot clears; join bound |
| `test_powerinfer_chat_route.test_unreachable_proxy_raises_without_hanging` | `urlopen` is patched to raise immediately; `timeout=1` is an argument, not measured |
| `test_powerinfer_chat_route.test_tcp_probe_timeout_does_not_wait_on_inference` | asserts the **passed** connect timeout `<= 0.4`, not elapsed runtime |
| `test_farm_dashboard.test_age_over_90s_is_stale` | snapshot age vs a frozen `datetime`; not test duration |
| `test_unsafe_tool_stays_sequential_even_alongside_a_safe_one` | sleeps to create a race window; asserts `write_file` start/end order, no elapsed bound |
| `test_parallel_tool_results_keep_original_call_order_in_the_transcript` | 0.2s vs 0.01s sleeps; asserts transcript order, no elapsed bound |
| `test_phone_scheduler.test_concurrent_dispatchers_claim_one_message_once` | `Event.wait` / `join` so the lease is held; asserts send-once |
| `test_retrieval_relevance.test_concurrent_get_index_builds_only_once` | in-function overlap flag + build count; sleeps only to widen the race |
| `test_exemplar_embeddings_concurrency` | `join(timeout=10)` that the threads finished; asserts no exception |
| `test_render_story_image.test_concurrent_calls_are_serialized_…` | `join(timeout=5)` + owner-claim assertions |
| farm `async_result.get(timeout=…)` / subprocess `timeout=30` | I/O deadlines, not performance claims |

No other `assertLess(elapsed, …)` exists in the scanned tree.

## Scope

Changelog only. No `agent.py` / test-file edit, `APP_REVISION` unchanged.
