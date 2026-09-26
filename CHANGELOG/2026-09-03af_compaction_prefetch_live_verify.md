# 2026-09-03af — compaction_prefetch live-verified past 0.80; ignore-if-busy made atomic

## What this session did

`compaction_prefetch.py` had 30 unit tests and no hop-loop / `agent.answer()` drive past `PROACTIVE_THRESHOLD = 0.80`. This session ran the real trim/prefetch fork (and a mocked `agent.answer()` long conversation) through that band, then overflow.

## What held

- **Threshold.** The hop-loop fires `maybe_start()` on `prompt_tokens > 0.80 * num_ctx`, not `>=`. A growing user/assistant transcript at `num_ctx=2500` was `tokens=2000 ratio=0.800 → below-threshold`, then `tokens=2198 ratio=0.879 → prefetch`. First trigger is in `(0.80, 1.0]`.
- **Stable-slice consume.** When token growth is a tool result in the protected tail (`_protected_tail_start` already pointing at a `tool_calls` assistant), the summarizable fingerprint does not move. Prefetch at 80% is consumed by `_trim_context` at overflow: one farm call, emit note `context compacted: ... farm CPU summary (model: live-farm-model)`, local compactor not called. Encoded as `test_stable_tool_tail_prefetch_is_consumed_on_overflow`.
- **Sequential ignore-if-busy.** Two `maybe_start()` calls with different fingerprints while the first job is in flight → one farm call. Already covered by `test_ignore_if_busy`; reconfirmed live.
- **`agent.answer()` e2e (mocked model, real system prompt + schemas).** System+tools estimate: **14364** tokens. With `ctx_ceiling=20520` (80% = 16416), a 12-turn history reached `tokens=18258 ratio=0.889` on hop 0: `maybe_start()` ran, background farm stored a ready result. Confirmed by reading module state after the turn (`result_ready=True`).

## Real gap found and fixed

**`maybe_start()` ignore-if-busy was not atomic.** The lock was released after reserving the fingerprint and *before* `_state["thread"] = t`. A second caller with a different fingerprint could pass `thread is None` in that window and start a second farm job.

Live reproduction: patch `threading.Thread.__init__` to sleep 50 ms (widens the window without changing the contract) and fire 6 concurrent `maybe_start()` calls at a barrier. **Before the fix: 6 farm calls / 6 fingerprints. After: 1 farm call.** Sequential close-together and an undelayed 8-way concurrent burst were both 1 even before the fix — the window is small, which is why the 30 unit tests never saw it (`test_ignore_if_busy` is strictly sequential).

**Fix** in `local_agent/compaction_prefetch.py`: construct the `Thread` and publish it on `_state["thread"]` in the same critical section as the fingerprint reservation. `t.start()` stays outside the lock so a fast farm completion cannot deadlock on `_lock`.

**Test that would have caught it:** `test_concurrent_different_fingerprints_start_only_one_farm_job`. 8 independent repeats, 8/8.

## Observed, not a correctness bug

Growing user/assistant turns (no in-flight `tool_calls`) change `_summarizable_slice` every hop because the tail is “last 4 messages.” Prefetch at 80% therefore mismatches at overflow and `_trim_context` falls through to the synchronous farm path. Probe counts: 2 prefetch hops + 1 overflow trim → 3 farm calls, 0 local. Same pattern on `agent.answer()` turn B (slice grew; 2 farm calls, emit used the sync farm summary). This matches the 2026-09-02u fingerprint-on-summarizable rule. Consuming a prefix summary would drop the messages that just rotated out of the tail, so the mismatch is the correct fallback.

A first tool hop also changes `_protected_tail_start` from “last 4” to “last tool-call assistant,” so a prefetch taken on a no-tool hop will not match the post-tool overflow slice. Sync farm covers it. The consume-win path is a later hop that is already in tool-tail mode, which is what the new stable-slice test drives.

Jumping the 80–100% band in one step (probe 2b: `0.738 → 1.680`) never calls `maybe_start()`; overflow uses the existing sync farm path.

## Tests

`python -m unittest local_agent.test_compaction_prefetch -v`

30 → 33. All 33 pass.

New:

- `test_concurrent_different_fingerprints_start_only_one_farm_job`
- `test_prefetch_fires_strictly_between_80_and_overflow`
- `test_stable_tool_tail_prefetch_is_consumed_on_overflow`

The 3 new tests alone: 3/3. Concurrent test: 8/8 repeats.

## Scope

`APP_REVISION` unchanged — no transport-visible behaviour. Prefetch still ignore-if-busy, still no wait on `consume()`, still falls through to farm → local when the slot is empty or the fingerprint moved.
