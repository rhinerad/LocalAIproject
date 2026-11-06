# 2026-09-25h — GVD judge: a requested flicker is not a cut (CPU dip rule, dark-frame annotation, prompt rule)

Follows 2026-09-25g (camera-rig check, same `video_judge.py`). 24r's main
open false-fail mode: "requested flicker or lighting change read as a
location change or cut", with two named held-out good clips: **c004** (the VLM
called one dark frame "a different dark hallway", `same_place_in_all_frames`
= no, temporal capped at 0.30) and **c018** (CPU cut-detector false positive at
1.83 s; "Detector left unchanged"). Both are fixed and measured; the
mechanism, the numbers on both sets and the two things that did not work are
below.

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
34–48 °C at start, 82 °C check before every clip, release and cool-down after
each run). Four llama-server launches (two 50-clip, two 29-clip), **1
connection reset** (D05 in the first tuning pass, the 24q "cause unknown"
mode; the runner's single retry succeeded), 0 crashes, ~8.3 s per clip, GPU
38 °C after. No ComfyUI, no renders.

Backups: `local_agent/{video_judge.py,test_video_judge.py}.bak_flicker_20260925T025853`,
`local_agent/{video_judge.py,dspy_orchestrator.py}.bak_darkframes_20260925T031452`.
Edits applied by `local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_flicker.py`
and `_edit_darkframes.py` (kept as the record; asserts refuse a second run).
All files LF; `dspy_orchestrator.py` verified 0 CR before and after.

## 1. What c018 actually is (measured before changing anything)

Mean luma per frame (64×36 decode): frames 0–12 lit at 76, 13–23 dimmed to
29, 24–34 **near-black at 3**, 35–43 **dim at 20**, 44 at 56, 45+ lit at 80.
So the flagged step at 1.83 s is dim → lit at the *end* of a 1.3 s dip, not
a two-frame blink. Every existing rule misses it for a stated reason: the
dark side (19 luma) is above the 16 near-black guard; the histogram never
"returns" because a lights-off frame never histogram-matches a lights-on
frame; and the adjacent-frame layout correlation is 0.63 because the panels
themselves are off (the lighting pattern changed, not just the gain), which
is why 24r's before/after correlation "did not separate it".

What does separate it: the lit picture **on the far side of the dip**. Frame
45 (luma 79) correlates with frames 0–12 (luma 76) at **0.86–0.91**. The same
comparison across every labeled real cut: D01 `8358` 0.56, c008 0.36, D04
`5ac6` −0.25, M03 `371a` 0.16–0.21 (a cut *into* a dark scene that brightens),
D03 `5c73` −0.12, D03 `ffd4` 0.03–0.10. Prototype run over all 79 clips
before touching the file: exactly one cut list changed (c018), all six
detected real cuts unchanged.

## 2. Change (`local_agent/video_judge.py`)

- **CPU detector, dip rule** (`_dip_returns_same_picture`, constants
  `CUT_DIP_FRACTION = 0.5`, `CUT_DIP_MAX_FRAMES = 48`): for a candidate step
  that survived every older test, take the brighter frame as the lit side;
  walk away from the step on the dark side over frames at least 2× darker
  than the lit frame (at most 2 s); the first frame beyond that stretch is
  the far reference. If its layout correlation with the lit frame is ≥
  `CUT_MAX_CORR` (0.70, the same threshold the adjacent-frame test uses),
  the step is one edge of a lighting dip on an unchanged picture and is not
  a cut. With no dip the reference is the adjacent frame, which already
  failed the correlation test, so a plain cut is never rescued; a cut into a
  dark scene that brightens (M03) walks 2 frames and finds a different
  picture (0.18). Exposure-invariant, so it covers dim stretches that the
  near-black guard cannot, without raising that guard (M03's post-cut frame
  at 17.2 luma is still a cut).
- Re-measured on the real file, all 79 clips: **1 change (c018: [1.83] →
  []), the six real cuts and every `blank_fraction` unchanged**
  (`judge_eval_20260925/frame_signals_v3b.json`).
- **Dark-frame annotation** (second iteration, after the prompt rule alone
  did not fix c004): `frame_signals` now returns `dark_spans_s`
  (`[[start_s, end_s, "near-black"|"dim"], …]`: runs below 16 luma, and runs
  below `DIM_FRACTION = 0.5` × the median lit luma), and
  `build_judge_user_prompt(..., signals=)` marks each sampled frame that
  falls in a span: `F2=1.6s (near-black: lights down in this frame,
  measured)`, followed by one line: a near-black or dim frame is a lighting
  dip in the same shot, not a new place and not a cut; judge place, cuts and
  the subject from the lit frames. Without a dip the user prompt is byte-
  identical to before. `dspy_orchestrator.judge_rendered_clip` passes its
  `signals` into the user prompt (three-line change). This is the 25d
  pattern: an instrument reading fed to the VLM instead of asking it to
  infer exposure from a JPEG. On the labeled sets it marks 62 sampled frames
  in 19 of 79 clips (c004 F2 near-black, c018 F2 dim, c017/c019/c033 flicker
  frames, and the all-black rejects, which the 25 % near-black aesthetic cap
  still holds at 0.20 whatever the VLM answers).
- **Prompt rule** (`VIDEO_JUDGE_SYSTEM_PROMPT`, "Lighting and camera moves"):
  a requested flicker / strobe / lights-out / dead tube / lighting change
  makes a merely darker or brighter frame with the same layout that effect,
  not a place change or a cut; a requested turn / approach / look at a wall,
  floor or object makes a later close-up of that surface in the same room
  that move, not a cut; answer `same_place_in_all_frames` "no" or
  `abrupt_cut_between_frames` "yes" only when the setting itself changes to
  somewhere else, never for the light level or the framing alone. The turn
  clause was added for c038, the new 25g false fail (see below). Measured
  alone (v3b) the rule fixed neither c004 nor c038; it is kept because it
  cost nothing measurable and states the intended reading.

## 3. The two named clips

| clip | label | v2b (shipped) | v3b (dip rule + prompt rule) | **v3c (+ dark-frame annotation, shipped)** |
|---|---|---|---|---|
| c018 | good, high | 1.0 / **0.25** / 0.80, cap "hard cut detected at [1.83] s" | 1.0 / 1.0 / 0.80, no cap, min **0.80** | 1.0 / 1.0 / 0.80, min **0.80** |
| c004 | good, high | 0.5 / **0.0** / 0.5, "F2 shows a different dark hallway", cap 0.30 | unchanged (still "different dark hallway") | 0.95 / 0.95 / 0.85, min **0.85**, all checks clean |

Both now clear the 0.80 strict bar. c018 is the detector; c004 is the
annotation (F2 at 1.59 s has mean luma 2 and is marked near-black).

## 4. Full sets, final code, against the shipped judge

Reports: `runtime/dspy_opt/judge_eval/report_{v3b,heldout_v3b,v3c,heldout_v3c}.json`;
per-clip diffs via `judge_eval_20260925/compare_results.py`. v3a is the 25g
state. FP = reject clips that pass, FF = good clips that fail, hc =
high-confidence labels.

| set | bar | v2b | v3a (25g) | v3b | **v3c** |
|---|---|---|---|---|---|
| tuning (50) FP | 0.60 = 0.80 | 10/35 | 8/35 | 8/35 | **8/35** |
| tuning FF | 0.60 = 0.80 | 0/8 | 0/8 | 0/8 | **0/8** |
| tuning hc FP / hc FF | 0.60 | 4/27 / 0/4 | 4/27 / 0/4 | 4/27 / 0/4 | 4/27 / 0/4 |
| tuning AUC | | 0.821 | 0.836 | 0.843 | **0.843** |
| tuning parse failures | | 0 | 0 | 1 | 1 (D03 `5c73`) |
| held-out (29) FP | 0.60 = 0.80 | 2/12 | 1/12 | 2/12 | **2/12** |
| held-out FF | 0.60 | 3/12 | 4/12 | 3/12 | **2/12** |
| held-out FF | 0.80 | 3/12 | 4/12 | 3/12 | 3/12 |
| held-out hc FP / hc FF | 0.60 | 1/7 / 2/5 | 0/7 / 2/5 | 1/7 / 1/5 | 1/7 / **0/5** |
| held-out AUC | | 0.809 | 0.806 | 0.799 | **0.833** |
| held-out parse failures | | 0 | 1 | 0 | 0 |

Genuine cuts and location changes, the thing 24q fixed and this entry must
not trade back: reject faults still passing at 0.60, tuning, v2b → v3c:
hard_cut **1/10 → 1/10**, location_drift **3/4 → 1/4** (D01 `086a`, 24q's
"late drift" miss, is now caught: "no birds visible in later frames",
same place "no"), time_of_day_jump 0/3 → 0/3, black_frames 0/1 → 0/1;
held-out hard_cut 0/3 → 0/3, location_drift 0/4 → 0/4, black_frames 0/2 →
0/2. The one loss on a temporal fault is scene_change 0/4 → 1/4: M05 `c6a5`
(reject, high: single raindrop on a hosta leaf; requested_action_absent +
scene_change), which flipped in v3a (25g's prompt change; the VLM now calls
the drop visible) and stayed there; it is not a lighting clip and the dip
rule and annotation do not touch it. wrong_viewpoint stays 1/3 (25g).

Held-out false fails, final: c035 (disputed label, 51 % near-black
aesthetic cap, as in 24r) and **c038** (good, medium: the brief asks the
camera to turn to the wall; since 25g the VLM describes F4–F8 as "close-up
of wallpaper, no hallway" and answers cut / different place / subject
absent). The turn clause did not fix it. At 0.80 only, c028 (good, medium)
also fails on aesthetic 0.75, which is run-to-run noise (next section), not
a check.

Verdict flips, tuning, v2b → v3c: caught D01 `3032`, c036 (25g rig check),
D01 `086a` (drift); lost M05 `c6a5`; partials M02 `b5ed` → pass, S03 → fail
("no torii visible", which is that partial's labeled fault). Held-out:
caught nothing new beyond c004/c018; M04 `4c83` (reject, high) failed in
v3a and passes again in v3b/v3c, as in v2b.

## 5. The judge is not bit-deterministic (measured here, matters for 24q's claim)

Between v3b and v3c only the 19 annotated clips received a different prompt.
Of the 60 clips whose system and user prompts were **byte-identical**, 4
came back different: tuning D01 `3032` (constraint_broken text only), D01
`b028` (alignment 0.0 → 0.2, a reject either way), D03 `ffd4` (two checks
flipped, scores identical), and held-out **c028** (aesthetic 0.80 → 0.75,
checks identical, raw text differs). 25a found the same on the action log's
batched image calls and attributed it to the server's batched decode /
flash-attn; the 8-image judge call is evidently not exempt, only less
affected (56 of 60 identical). Consequences: single-clip flips between runs
of ±0.05 or one check are within noise; 24ae's "13 re-judged clips
identical" was luck-compatible, not proof of determinism; and a good clip
sitting exactly at 0.80 (most Backrooms clips, 24ac) can land at 0.75 on a
re-run and fail the strict bar. Not fixed here; noted for the curriculum.

## 6. Parse failures (production would score these 0.01, not judge them)

- v3b/v3c tuning D03 `5c73` (reject, CPU cut at 1.08 s): the VLM wrote
  long, run-on frame lines and hit `num_predict=1536` before the scores
  ("VLM did not return a JSON object with float scores"). 24r's runaway
  mode, 0 of 79 then at 8 frames; 1 of 79 now with the longer checklist and
  the per-frame rig question. The clip is a reject, so the verdict is right
  by accident; in production a `_fail_result` (0.01) sorts below every
  judged clip (24ad floor 0.10), which for a real reject is the wrong
  order. 25g's br_c001 `32ce` early-close did not recur in v3b/v3c.
- Open: a retry with a shorter `frames` instruction (or a higher budget) on
  `missing or invalid float score` in `run_qwen_director_scores`.

## Tests

- `test_video_judge.py` +7 (`LightingDipTests`): a dim stretch on the same
  picture is not a cut, and is two cuts again when `CUT_DIP_MAX_FRAMES` is
  patched below its length (the older flash rules cannot see a 21-frame
  dip); a cut into a dark scene that brightens (M03 shape) is still a cut;
  the rule needs a real dip; `dark_spans` on c018's luma shape and on the
  synthetic dip; the user prompt marks frames inside a dip and is byte-
  identical without one; the orchestrator passes `signals` through; the
  prompt rule text. The synthetic shots are `_static()` (one picture
  repeated): `_scene()` pans 1 px/frame over white noise, which has no
  spatial coherence, so a 1 s pan of it never correlates the way real
  footage does.
- `python -m unittest test_video_judge test_dspy_orchestrator test_media_accuracy_gate test_generalized_video_director test_llama_cpp_client`: 136 OK.
- Full non-live suite on the final files (Phase A and B together),
  `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
  **1563 OK (2 skipped)**, 321 s, exit 0 (2026-09-25 03:29–03:35 local,
  `runtime/dspy_opt/judge_eval/full_suite_20260925_flicker.log`). Baseline
  before this session's edits was 1550 OK (2 skipped); +6 tests from 25g,
  +7 from this entry. This is also the clean run 25g refers to.

## Open

- c038: a requested turn to a wall read as a cut; the measured camera-motion
  estimator (25c/e) could mark a pan/turn window the way `dark_spans_s`
  marks a dip. Not started.
- Run-to-run noise (section 5) and the runaway / early-close parse failures
  (section 6).
- D02 `614e` (25g) unchanged.
- `gvd_vlm_raw.jsonl` gained 158 debug rows (2 × 79);
  `gvd_live_metric_history.jsonl` untouched (261 rows).
