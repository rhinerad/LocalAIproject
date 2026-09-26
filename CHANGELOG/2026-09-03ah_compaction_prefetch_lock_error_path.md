# 2026-09-03ah — compaction_prefetch: lock-cost recheck and start() rollback

Follow-up to 2026-09-03af. The atomic ignore-if-busy fix holds the lock across `Thread()` construction. This session checked whether that larger critical section has a hidden cost, and whether a `Thread()` / `start()` failure can deadlock or brick the slot.

## Concurrent load — not a lucky 8/8

40 bursts of the 6-way DelayedThread test (50 ms `Thread.__init__`, the widened critical section) and 40 bursts of an 8-way no-delay test:

| burst | n | farm_calls | fails | elapsed |
|---|---|---|---|---|
| 6-way, 50 ms init | 40 | always 1 | 0/40 | p50 78 ms, max 891 ms (one scheduler outlier; still 1 farm job) |
| 8-way, no delay | 40 | always 1 | 0/40 | p50 16 ms, max 32 ms |

`consume()` overlapping a realistic `maybe_start()` (real `Thread()`, 30 trials, 8 consumers each): consume wait **p50 = 0.0 ms, max = 0.0 ms**. `maybe_start` itself p50 0.0 ms, mean 0.5 ms, max 15 ms (one outlier). No new contention under realistic load.

The 50 ms DelayedThread *does* block `consume()` for ~47 ms — that is the test's artificial `__init__` sleep, not production. `Thread()` is object construction only; the OS thread is created in `start()`, which stays outside the lock.

Encoded as `test_concurrent_six_and_eight_way_bursts_are_stable`.

## Error path — lock released, slot was not

`Thread.__init__` almost never raises. Resource exhaustion (`can't start new thread`) is `Thread.start()`.

- **`Thread()` raises under the lock:** `with` releases it. Probe: lock re-acquired in 0.0 ms. No deadlock. But the fingerprint was already stored, so a same-slice retry would no-op forever, and the exception escaped `maybe_start()` (the hop loop does not catch that).
- **`start()` raises after the slot is published:** lock not held. The unpublished/unstarted `Thread` stayed in `_state["thread"]`. Every later `maybe_start()` saw busy and returned. Probe: second start with a different slice → 0 farm calls, never idle. This is the realistic exhaustion path, and it bricked the one-slot machine for the rest of the process.

## Fix

`local_agent/compaction_prefetch.py` `maybe_start()`:

- `Thread()` failure inside the lock: roll back fingerprint/result, return. Does not raise.
- `start()` failure outside the lock: if `_state["thread"]` is still this object, clear thread/fingerprint/result. Does not raise.

`start()` remains outside the lock so a fast farm completion cannot deadlock on `_lock`.

## Tests

`python -m unittest local_agent.test_compaction_prefetch -v` — 36 tests (was 33), all pass.

New:

- `test_concurrent_six_and_eight_way_bursts_are_stable` (40×6-way + 40×8-way)
- `test_thread_init_failure_releases_lock_and_does_not_stick_the_slot`
- `test_thread_start_failure_releases_slot_so_later_maybe_start_can_run`

`TestMaybeStart` alone: 11/11 in 4.2 s.

## Scope

`APP_REVISION` unchanged. Happy-path prefetch/consume behaviour unchanged. Failures that used to raise or pin the slot now fall through to the existing synchronous farm path on the next overflow.
