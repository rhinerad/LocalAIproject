# 2026-09-03ag — Parallel-hop test times the tool window, not answer() wall-clock

## What changed

**`local_agent/test_native_tool_calling.py` only.** `agent.py` not touched.

`test_concurrency_safe_tools_run_in_parallel_within_one_hop` no longer uses
`elapsed = time.monotonic() around answer(); assertLess(elapsed, 0.55)` as the
parallelism check. That bound mixed two 0.3s concurrent tool sleeps with the
rest of `answer()` (GPU telemetry, context prefetch, prompt assembly). The
tools were already overlapping; the bound was not.

The test now asserts:

1. the two tool bodies overlap (`min(ends) > max(starts)` — unchanged)
2. the tool window `max(ends) - min(starts) < 0.45` (the sequential-vs-parallel
   discriminator, now measured on the calls themselves)
3. `answer()` returns in under 5s (hang detector only, same ceiling as the
   hop-limit test; not a parallelism check)

## Why this is not a latency regression

Ran on DuranGamingPC, Python 3.12.10, live ComfyUI on 8188, GPU telemetry
unmocked unless noted.

Isolated `answer()` loop (same patches as the test):

| config | n | overlap | tool window | answer() elapsed | `elapsed >= 0.55` |
|---|---|---|---|---|---|
| live GPU, 0.3s sleeps | 40 | 40/40 | 0.296–0.313s | 0.390–0.469s | 0/40 |
| mocked `gpu_busy`, 0.3s | 40 | 40/40 | 0.296–0.313s | 0.297–0.360s | 0/40 |
| live GPU, sleep 0 | 20 | n/a | ~0 | 0.093–0.141s | 0/20 |

Second pass, printing overlap even on slow `answer()`:

| config | n | overlap | tool window | `elapsed >= 0.55` | slow `answer()` samples |
|---|---|---|---|---|---|
| live | 60 | 60/60 | 0.297–0.313s | 4/60 | 1.000, 1.563, 0.844, 1.922s (`gpu_busy` 0.09–0.11s on each) |
| mocked `gpu_busy` | 40 | 40/40 | 0.296–0.313s | 1/40 | 1.562s with `gpu_busy` = 0 |

Real unittest method, pre-fix (still `elapsed < 0.55`): **2/30 failed**
(0.609s, 0.812s). Post-fix: **0/30 failed**, including runs whose
`answer()` wall-clock was 0.610s and 0.703s — those would have failed the old
bound.

`gpu_busy()` itself is 0.078–0.110s while Comfy is listening (short-circuit).
`router._running_models` / `up()` were observed up to 0.42s / 0.28s in
isolation. That does **not** explain the 0.84–1.92s `answer()` tails: those
happened with `gpu_busy` at ~0.1s **and** with `gpu_busy` fully mocked. The
variable cost is the rest of `answer()`, not the thread pool.

Start stagger of the two tool bodies was 0.000s whenever measured. The two
calls are not serializing.

A GIL-hog CPU-burner in the same interpreter stretched `answer()` to 13–18s;
that is interpreter starvation, not hop-loop regression, and was not used to
choose the new bound.

Historical reports of this flake (same assertion, tools still the parallelism
path): 2026-09-03g 0.91–0.94s; 2026-09-03ad 0.56–0.70s.

## Why 0.45, not a looser `elapsed` ceiling

Sequential execution of two 0.3s calls makes the tool window `>= 0.6s`.
Raising `elapsed < 0.55` to something that survives 1.92s of `answer()`
overhead (about 2.5–5s) would pass a serialized hop. The 0.55 figure was
trying to be a sequential discriminator and no longer can be, once hop
overhead exceeds 0.25s.

0.45 on the tool window sits ~140ms above the observed concurrent max
(0.313s) and 150ms below sequential (0.6s). That is the margin that actually
tests parallelism.

The 5.0s `answer()` ceiling is only a hang detector.

## Evidence

- Pre-fix unittest loop: 2/30 fail, `0.609` and `0.812` vs `< 0.55`.
- Post-fix unittest loop: 0/30 fail, min 0.406 / p50 0.422 / max 0.703.
- Overlap 140/140 across the isolated loops; tool window never left
  0.296–0.313s.
- `python -m unittest local_agent.test_native_tool_calling -v`: **65 ran, OK**
  in 10.635s, including the rewritten parallel-hop test.

`APP_REVISION` unchanged. No hop-loop code change.

## Scope

Test-file + this changelog. Probe scripts used for the loops are not kept.
