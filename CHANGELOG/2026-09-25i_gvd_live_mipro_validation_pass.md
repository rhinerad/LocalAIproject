# 2026-09-25i — first live MIPRO pass with every 24q–25h judge change active (4 rows, 0.80 bar, 0.10 floor)

Follows 2026-09-25g/h. TODO's "the next real MIPRO run is the first under the
0.80 bar and the 0.10 floor" had not been run: 24q (fault-checked judge), 24ac
(strict bar 0.80), 24ad (judged floor 0.10), 24ae (repeat_penalty plumbing,
judge pinned at 1.0), 25g (camera-rig check) and 25h (flicker fixes) had each
landed and been tested alone. This entry is the end-to-end check: a real,
live MIPROv2 pass through `dspy_orchestrator.compile_director` with the
production metric, real FLUX + MiniMax renders and the real judge, then the
rows compared with the last real pass in the history file (rows 245–261,
2026-09-24o, old judge). Runner: `local_agent/_gvd_live_phaseC_20260925.py`
(modelled on 24o's `_recompile_gvd_director_20260924.py`; kept). It is a
validation pass, not a production recompile: it saved to
`models/dspy_compiled/generalized_video_director_mipro_phaseC_20260925.json`
and left `generalized_video_director_mipro.json` untouched (mtime 2026-09-24
15:26 before and after).

## Preconditions and guards, as run

- Before start: port 8188 closed, `batch_render_queue_owner.json` released,
  GPU 31 °C, port 11436 closed, Ollama on 11434 with `qwen2.5:1.5b`
  (student) and `llama3.1:8b` (proposer), `XAI_API_KEY` removed from the
  environment. The wrapper asserted at import: `curriculum_threshold(6) ==
  0.80`, `JUDGED_SCORE_FLOOR == 0.10`, 8 check keys, the 25h dip rule present.
- Owner held for the whole run (pid 48924, 03:37:01–05:31:50). Sanctioned
  Rockernow backend via `restart_comfy_rockernow.ps1`, `/system_stats` up
  after 2:53, one listener, stopped by `stop_rockernow()` at the end
  (Rockernow-only check), owner released, GPU 36 °C / 39 MiB afterwards.
- Every render wrapped in `thermal_guard.wait_before_render` (start ≤ 70 °C;
  every start was 31–39 °C) and `wait_after_render` (≤ 58 °C). Watchdog
  thread sampling every 5 s: **no trip**, no telemetry failure; peak **77 °C
  on all eight renders**. Renders took 677–787 s each; the whole pass 114.8 min
  (`runtime/dspy_opt/phaseC_20260925/status.json`, `run.out.log`).
- `GVD_CURRICULUM_ITERATION=6` in the wrapper's environment, so every judged
  row carries `threshold 0.8, iteration 6` (the strict bar from 24ac).

## Settings

Slice GVD-B01, GVD-D01, GVD-D02, GVD-M03 (the Backrooms row for the bar and
the flicker rules, two drone rows for the rig check, the row that was 24o's
false pass). `num_candidates=1, num_trials=1`, 0 demos, the `--compile`
defaults; as in 24o MIPRO ran the baseline evaluation plus "Trial 2 / 1", so
each row rendered twice (student at temperature 0.4 gives a different prompt
the second time). With one candidate the trial re-evaluates the same program,
so the saved artifact is the original instructions (1490 chars) and "Best
score so far: 51.87" is the baseline mean × 100. This pass validates the
metric path; it does not choose between programs.

## The eight rows (`gvd_live_metric_history.jsonl` 262–269)

Sheets of the judge's own 8 frames: `runtime/dspy_opt/phaseC_20260925/sheets/`.
"Label" is my review of those sheets after the scores were seen
(`phaseC_render_labels.json`, not blind). "Offline" is the same clip judged
again through `gvd_judge_eval.py run --variant production` after the backend
was down (`results_phaseC_renders.jsonl`), i.e. the same prompt a second time.

| row | pass | clip | live scores (align / temporal / aesthetic) | what fired | mipro (raw) | ≥ 0.80 | label | offline re-judge |
|---|---|---|---|---|---|---|---|---|
| 262 | base | D01 `167c` | 0.00 / 1.00 / 0.75 | subject absent ("no birds visible") → cap 0.20 | 0.175 | no | reject (drifts from the cliffs to open sea; birds at most specks) | identical |
| 263 | base | D02 `53ae` | 1.00 / 1.00 / 0.90 | nothing; rig "no" | 0.920 | **yes** | good (true FPV up through pines, out over the canopy) | **parse failure**: runaway repetition, truncated at the token budget |
| 264 | base | M03 `4110` | 1.00 / 1.00 / 0.95 | nothing | 0.960 | **yes** | good (creek, fern frond, caustics) | identical |
| 265 | base | B01 `644b` | not judged | `mechanical video check failed: backrooms clip missing a motion keyword` **after** the 757 s render | 0.02 | no | good (continuous camcorder hallway walk) | **1.00 / 1.00 / 0.80, min 0.80, passes the bar** |
| 266 | trial | D01 `8a4d` | 0.00 / 0.00 / 0.50 | CPU hard cuts at 0.88 s and 4.5 s → cap 0.25; VLM cut "yes"; subject absent | **0.100 (raw 0.050)** | no | reject (three shots) | same scores |
| 267 | trial | D02 `7d15` | 0.40 / 0.25 / 0.75 | same place "no", cut "yes", time of day "no", constraint quoted | 0.315 | no | reject (drone-like object in F1, then morphing blur) | **flipped: 0.95 / 0.95 / 0.80, all checks clean** |
| 268 | trial | M03 `1dad` | 0.25 / 0.80 / 0.70 | **rig check "yes"** (a hand reaches into the creek in F1–F2) → cap 0.25; subject count "no" | 0.350 | no | reject (hand; constraints allow nothing larger than an insect) | same scores |
| 269 | trial | B01 `d959` | 0.30 / 0.95 / 0.40 | text/logo "yes" (vertical yellow VHS text down the right edge) → caps 0.30 / 0.40 | 0.375 | no | reject (text overlay) | same scores |

Baseline mean 0.519 (0.175, 0.920, 0.960, 0.02); trial mean 0.285.

## Against the last real pass (rows 245–261, 24o, old judge, bar 0.60)

Same four clip ids, one pass each, old judge, with today's labels for those
renders from `gvd_judge_labels.json`:

| clip id | 24o row, render | old judge | label (24q) | this pass |
|---|---|---|---|---|
| D01 | 246, `8358` | 0.85 / 0.95 / 0.90, mipro 0.865, **pass** | reject (hard cut, time-of-day jump) | `167c` 0.175 fail, `8a4d` 0.100 fail, both rejects by review |
| D02 | 247, `614e` | 0.95 / 0.98 / 0.85, mipro 0.873, **pass** | reject (drone in frame) | `53ae` 0.920 pass (good by review), `7d15` 0.315 fail (reject by review) |
| M03 | 253, `371a` | 0.85 / 0.95 / 0.90, mipro 0.865, **pass** | reject (no water, hard cut) | `4110` 0.960 pass (good by review), `1dad` 0.350 fail (reject by review) |
| B01 | 261, `93fb` | 0.85 / 0.95 / 0.70, mipro 0.740, **pass** | reject (wall wobble, medium) | `644b` gated 0.02 (good by review; 0.80 offline), `d959` 0.375 fail (reject by review) |

In 24o's pass all four of these clip ids passed and three of the four
renders are labeled rejects. In this pass every one of the seven live-judged
rows agrees with my review label (7/7), and the eighth, never judged live,
would have passed correctly. The scores are also no longer the two default
triples: eight rows, seven distinct triples.

## The three questions

**(a) Do good Backrooms clips clear the 0.80 bar?** Yes, at the edge. The
only good B01 render (`644b`) was never judged live (next section); judged
offline it scores 1.00 / 1.00 / 0.80 and passes at exactly 0.80, which is
where 24ac showed every correct Backrooms clip sits. The live-judged B01
(`d959`) failed at 0.30 for a real text overlay, correctly. Two non-Backrooms
good rows cleared the bar live (D02 0.90, M03 0.95). Caveat from 25h: the
judge's run-to-run noise is ±0.05 on the aesthetic axis, so a clip at 0.80
can land at 0.75 on another run; the bar has no margin for Backrooms clips.

**(b) Does a judged reject outrank a timeout / mechanical fail?** Yes, by
construction and now in a real row: row 266's raw scalar is **0.050**, which
is exactly the timeout penalty and would have tied it (and sat below it with
one fewer frame), and the floor made it 0.100; row 265's mechanical fail is
0.02; row 262's judged reject is 0.175. Ordering in the history: 0.960 >
0.920 > 0.375 > 0.350 > 0.315 > 0.175 > 0.100 (judged) > 0.02 (mechanical).

**(c) Are Phase A / B visible in real rankings?** Partly.
- 25g rig check: fired once, on row 268, where a human hand reaches into
  frame; the verdict is right (the constraints forbid it) and the category
  is a stretch (a hand is "operator" only if it is the operator's). It
  correctly stayed "no" on the true FPV row 263. It **missed** row 267's
  F1, where the VLM's own frame line says "a black object (likely drone)"
  and the check still answered "no": the 614e anchoring miss, seen live.
- 25h: the CPU dip rule had nothing to suppress (no false cuts on eight
  renders); the two real cuts in row 266 were detected and capped. Only row
  267 had a sampled frame inside a measured dip (F2, dim) and it was
  annotated. No flicker Backrooms clip reached the judge live because `644b`
  was gated, and `644b` has no dark span anyway, so the flicker rules were
  **not exercised** by this pass. A negative result, not a failure.

## Problems this pass surfaced (outside A/B scope; documented, not fixed)

1. **The mechanical gate runs after the render and rejects on prompt text.**
   Row 265: 757 s of GPU for a clip the review calls good, then
   `_fail_result` 0.02 because the student's `video_prompt` said
   "gradually moves … panning" instead of walk / push in / tracking / dolly.
   `mechanical_director_gate` is called after `generate_minimax_clip` in
   `evaluate_live_candidate`; its keyword test needs only `pred` and could
   run before the GPU like 24o's `instruction_echo` check. Pre-existing
   (15l saw it), but it is why the Backrooms bar question needed the offline
   re-judge. Operator decision: move the keyword test pre-render, or relax
   it (the prompt it rejected rendered a good clip).
2. **Runaway repetition in the judge.** Two in 87 scorings this session:
   D03 `5c73` (25h) and row 263's clip offline ("more motion blur,
   approaching a break in the canopy, slight upward tilt, …" until the
   budget). `repeat_penalty=1.0` (24ae) is what permits the loop; 24ae
   measured 1.08 as harmful to the checklist. In production a runaway is
   `VLM scores rejected` → 0.01, below the floor and below a mechanical
   fail, for a clip the same judge scored 0.92 live. A retry on
   `missing or invalid float score` (with the penalty on for the retry only,
   or a smaller value) is the obvious fix; not done here.
3. **Non-determinism confirmed on live renders** (25h §5): row 267 is a
   reject at 0.315 live and a clean 0.80 pass on the byte-identical offline
   prompt; row 263 parsed live and looped offline. Chaotic clips are a coin
   flip; clean clips (262, 264, 266, 268, 269) repeat.

## Housekeeping

- History rows 262–269 appended by `_store()`; rows ≤ 261 untouched. 24q's
  caveat stands: these rows are not comparable with rows ≤ 260.
- `gvd_vlm_raw.jsonl` gained 16 debug rows (8 live, 8 offline).
- Renders in `ComfyUI-Shared\output\dspy_opt\gvd_GVD-{D01_167c72dc3f,
  D02_53aed93a64, M03_4110b9ef85, B01_644b2f57ad, D01_8a4d088b69,
  D02_7d152c1013, M03_1dad247a4d, B01_d959d6ff17}_00001_.mp4`, kept.
- No code changed in this entry beyond the new runner script. The full
  non-live suite from 25h (1563 OK, 2 skipped) stands.
- `TODO.md`: the "next real MIPRO run" item closed with this outcome; two
  open items for the gate order and the runaway retry.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
