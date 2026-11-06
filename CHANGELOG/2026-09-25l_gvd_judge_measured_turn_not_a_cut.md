# 2026-09-25l — GVD judge: a measured camera turn is not a cut (estimator readings over the sampled-frame gaps, marked in the user prompt)

Follows 2026-09-25g/h/k. The open item those three entries share: **c038**
(good, held-out) is a Backrooms walk whose brief says "turns to confirm …
walks towards the wall"; since 25g the VLM described F4–F8 as "close-up of
wallpaper, no hallway" and answered abrupt cut / different place / subject
absent, and 25h's prompt rule alone did not move it. 25h named the fix:
feed the measured camera-motion estimator (`camera_motion.py`, 2026-09-25c/e)
into the judge's user prompt the way `dark_spans_s` marks a lighting dip.
Built, measured first on all 87 labeled clips without the VLM, then judged
on both labeled sets and the phase C renders. `camera_motion.py` itself is
**not modified**; its output is consumed.

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
≤ 70 °C at start; owner held; 82 °C check before every clip; release and
cool-down after each run). Four llama-server launches: a 2-clip probe (GPU
30 °C at start, 11:04–11:05) and the three full runs (35 / 47 / 48 °C at
start, 11:05:34–11:21:52 local). 0 connection resets, 0 crashes, 2 retries
(below), GPU 44 °C / 39 MiB afterwards, 8188 and 11436 closed, owner
released. About 10 s per clip (25k's 8.5 s plus the estimator's ~1 s grey
decode). No ComfyUI, no renders; existing files only.

Backups: `local_agent/{video_judge.py,dspy_orchestrator.py,test_video_judge.py}.bak_camturn_20260925T110204`,
`TODO.md.bak_gvd_judge_camturn_20260925T112349`. Edits applied by
`local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_camturn.py` (code and
tests) and `_edit_todo_camturn.py` (TODO, CRLF kept: 2657 → 2670 CR, 0 bare
LF); both refuse a second run. The three Python files were LF (0 CR) before
and after. Measurement and summary scripts: `_measure_camturn.py`
(`camera_gaps_v3e.{json,txt}`), `_summarize_camturn.py`
(`summary_camturn_v3e.txt`), plus `compare_results.py` outputs
`compare_v3{c,d}_v3e_{tuning,heldout}.txt`.

## 1. Measure first: what the estimator says over the judge's own gaps (CPU only)

For every labeled clip and the 8 phase C renders, the judge's 8 sampled frame
times (`extract_eval_frames`, cached) define 7 gaps; `estimate_camera_motion`
was run over those gaps and the per-gap label and summed pan / tilt
fraction recorded (`camera_gaps_v3e.txt`). Two things decided the gates:

- The bare label marks far too much: 32 of 87 clips (109 frames), among them
  the 25c creek confounder M03 `1216` (good: water flowing down the frame
  reads tilt-up on all 7 gaps at 0.13–0.15 of the frame) and 23 rejects,
  because cuts, morphs and drift are also large global shifts.
- c038's turn is large and rigid: pan-left at **0.46** (F3→F4) and **0.32**
  (F4→F5) of the frame width with the estimator's `subject_motion` flag off
  (centre excess 0.1–0.3 px). c030 (reject, a cut-and-return the brief also
  calls a turn) swings at 0.27 / 0.27 / 0.48 but **every swing carries the
  flag** (excess 2.4–4.4 px), as do both of D01 `086a`'s (late drift), both
  of D04 `3f0c`'s, and D02 `7d15`'s single pan (phase C).

Gates, both on the estimator's own output: the picture must have slid by at
least **`TURN_MIN_FRAC = 0.20`** of the frame across the gap (the creek's
0.15 stays under it), and **`subject_motion` must be off** (a rigid turn, not
a moving subject, a morph or a drift). Marked clips under both gates: **9 of
79 labeled, 0 of 8 phase C**: goods c038 (F4, F5) and br_c002 (F8, its "turn
toward the floor"); tuning rejects M05 `c6a5` (F3–F5, tilt-down), D01 `3032`
(F6, F7, tilt-up), c009 (F3, F5); held-out rejects c026 (F6), D04 `5ac6` (F5,
F6, the frames after its 3.04 s cut), D04 `cc43` (F8), M01 `d9e1` (F3). No
partial. Every marked reject except M05 was already held by a cap that no
temporal answer can lift (rig 0.25, text 0.30/0.40, subject absent 0.20, CPU
hard cut 0.25), and M05 was a false pass, so the worst case for the rejects
was "no change". The gates were chosen with c038's readings in view, so the
held-out numbers below are not a blind test of this change.

## 2. Change

- `local_agent/video_judge.py`: `TURN_MIN_FRAC`, `TURN_LABELS`;
  `measured_camera_moves(video, frame_times)` (gap windows keyed by the later
  frame's 1-based index → `estimate_camera_motion`, one compact record per
  gap: frame, start, end, camera, dx_frac, dy_frac, scale, response, pairs,
  low_response_pairs, subject_motion); `turn_amount`; `measured_turns(moves)`
  (the two gates → `{later frame: "turned left" | "turned right" | "tilted up"
  | "tilted down"}`). `build_judge_user_prompt` marks the later frame of each
  rigid turn, `F4=4.4s (camera turned left between F3 and F4, measured)`, on
  the same line a dip mark would share (`dim: …; camera turned …`), and when
  any frame is marked appends one line, `TURN_RULE`: a measured turn is an
  instrument reading, the whole picture slid between those two frames as it
  does when the camera pans or tilts within one continuous shot; a wall,
  floor, ceiling or object of the same room or scene filling the later frame
  after a turn is that camera move, not a cut, not a new place, and still the
  BRIEF's setting; answer abrupt_cut "yes" or same_place "no" across a
  measured turn **only if the setting itself is somewhere else** (another
  room, landscape or set). With no rigid turn, or no measurement, the prompt
  is byte-identical to 25h's. The system prompt, checks, caps table and CPU
  detector are unchanged; a turn caps nothing.
- `local_agent/dspy_orchestrator.py`: `judge_rendered_clip` extracts the
  frames, then, on the production path (no injected `signals_fn`), calls
  `video_judge.measured_camera_moves` and stores the result as
  `signals["camera_moves"]`, so it reaches the user prompt, the feedback row
  and the eval records; a failed estimate is printed and skipped. New
  `camera_fn` hook on `judge_rendered_clip` and `evaluate_live_candidate`
  (an injected `signals_fn` gets no measurement unless `camera_fn` is
  injected too, so every existing test is unchanged and none runs ffmpeg).
- `gvd_judge_eval.py`: no change needed; result records already carry
  `signals`, now with `camera_moves`.

## 3. The named clips (first wording, no second one tried)

Probe `results_heldout_v3e_probe.jsonl` (`--only c038 br_c002`), then the
full runs.

| clip | label | v3d (25k, shipped before) | **v3e** | probe |
|---|---|---|---|---|
| **c038** | good, medium | 0.00 / 0.00 / 0.50, min **0.00**: subject "no", same place "no", cut "yes", time "no", count "no" | 0.95 / 0.95 / 0.85, min **0.85**, all eight checks clean; frame lines "camera turned left, showing left wall with door" for F4–F8 | same |
| br_c002 | good, medium | 1.00 / 1.00 / 0.80 | 1.00 / 1.00 / 0.80 ("the camera has turned to the right, showing a different angle of the wall") | 1.00 / 0.95 / 0.85 (±0.05 run noise, 25h §5) |
| c030 | reject, high | 0.90 / 0.95 / 0.85 (false pass since 24q) | **unmarked, identical** | — |

c038 clears the 0.80 strict bar, on the first wording, in the probe and again
in the full run. The 25g open item "c038 false fail" is closed.

## 4. Full sets, final code, against 25k's v3d (verdict-identical to 25h's v3c)

Reports: `runtime/dspy_opt/judge_eval/report_{v3e,heldout_v3e}.json`,
`phaseC_20260925/report_phaseC_v3e.json`. FP = reject clips that pass, FF =
good clips that fail, hc = high-confidence labels.

| set | bar | FP v3d → v3e | FF v3d → v3e | hc FP | hc FF | partial pass | AUC | distinct triples |
|---|---|---|---|---|---|---|---|---|
| tuning (50) | 0.60 = 0.80 | 8/35 → **7/35** | 0/8 → 0/8 | 4/27 → **3/27** | 0/4 → 0/4 | 6/7 → 6/7 | 0.843 → **0.864** | 25 → 25 |
| held-out (29) | 0.60 | 2/12 → 2/12 | 2/12 → **1/12** | 1/7 → 1/7 | 0/5 → 0/5 | 2/5 → 2/5 | 0.833 → **0.872** | 16 → 16 |
| held-out | 0.80 | 2/12 → 2/12 | 3/12 → **2/12** | 1/7 → 1/7 | 0/5 → 0/5 | 2/5 → 2/5 | | |
| phase C (8) | 0.60 = 0.80 | 1/5 → 1/5 | 1/3 → 1/3 | 0/1 → 0/1 | 0/1 → 0/1 | — | 0.733 → 0.733 | 8 → 8 |

Verdict flips, both bars: **two**, both right. Held-out c038 FAIL → PASS
(above). Tuning **M05 `c6a5` PASS → FAIL** (reject, high: single raindrop on
a hosta leaf, requested_action_absent + scene_change; the 24q catch that 25g
lost to prompt sensitivity): its 7 gaps read tilt-down at 0.09–0.26 (F3–F5
marked); the VLM now writes "the camera has tilted down … showing a different
leaf with water droplets. The original leaf is not visible" for F5–F8 and
answers subject "no", same place "no", cut "yes" (1.00 / 1.00 / 0.90 → 0.00 /
0.00 / 0.50). A turn mark drew its attention to the change instead of
excusing it, and the rule's reservation ("only if the setting itself is
somewhere else") was applied as written. The remaining tuning false passes
are the six 25g/25h left (D02 `614e`, M04 `15e7`, S01, S05, B01 `93fb`, M04
`cfa7`) plus c030; held-out c021 and M04 `4c83`; held-out false fails c035
(disputed label, near-black cap) and, at 0.80 only, c028 (aesthetic 0.75,
25h's noise case).

Other marked clips, no verdict change: D01 `3032` temporal 0.50 → 0.90 and
aesthetic 0.50 → 0.95 with the rig cap still holding alignment at 0.25
(rationale: "a continuous aerial shot … with only a measured turn between
frames"; its late drift was not called in v3d either); c026 (reject, subtitle
text) same place "no" → "yes" and cut "yes" → "no", min 0.00 → 0.20, still
capped by text (0.30 / 0.40) and subject absent (0.20), and its labeled fault
is `text_or_logo` alone; D04 `5ac6` unchanged at 0.00 with turn marks on the
two frames after its cut, the VLM still writing "now in a different location,
a swampy area" and answering cut "yes" (time-of-day flipped "yes" → "no", a
halo); c009, D04 `cc43`, M01 `d9e1` identical.

**Every unmarked clip's prompt was byte-identical to v3d and every unmarked
verdict reproduced**: 47/47 tuning, 23/23 held-out, 8/8 phase C, no min-axis
change on any of them (`summary_camturn_v3e.txt`). Two runaways recurred
and 25k's retry recovered both, the same two clips as in 25k (D03 `5c73`
→ 0.00 / 0.00 / 0.00; D02 `53ae` → 0.50 / 0.00 / 0.75). No-score answers 0
on all three sets.

## 5. The rows the task said to watch

Reject faults still passing at 0.60, v3d → v3e: tuning **hard_cut 1/10 →
1/10**, **location_drift 1/4 → 1/4**, scene_change 1/4 → **0/4** (M05),
time_of_day_jump 0/3 → 0/3, black_frames 0/1 → 0/1, color_or_location_drift
0/1 → 0/1, wrong_viewpoint 1/3 → 1/3; held-out hard_cut 0/3 → 0/3,
**location_drift 0/4 → 0/4**, black_frames 0/2 → 0/2, color_or_location_drift
1/1 → 1/1 (c021, as before). Nothing 24q or 25h fixed came back. c030 was
not marked (section 1) and is unchanged; D01 `086a` (24q's late drift, caught
in 25h) was not marked and is unchanged at 0.40 / 0.30 / 0.80.

## Tests

- `test_video_judge.py` +6 (`CameraTurnTests`): gap windows and the compact
  record from a patched estimator (one frame time → no call); the two gates
  (0.10 pan, a flagged pan and an `uncertain` gap are not turns; 0.46 / 0.32
  / a 0.24 tilt are; the creek's 0.15 is under `TURN_MIN_FRAC`); the mark on
  the later frame, the rule line only when marked, and the byte-identical
  plain prompt for push-in / flagged / uncertain / empty moves; a dip mark
  and a turn mark on one frame; the orchestrator measures on the production
  path only (patched estimator called once with the frame times, not called
  with an injected `signals_fn`, called via `camera_fn`, and a `ValueError`
  from it is skipped with the plain prompt and a passing verdict); the
  feedback row carries `signals.camera_moves` and a turn caps nothing.
- `python -m unittest test_video_judge test_dspy_orchestrator test_media_accuracy_gate test_generalized_video_director test_llama_cpp_client test_camera_motion`: 169 OK.
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`
  on the final files, after the VLM was released: **1582 OK (2 skipped)**,
  385 s, exit 0 (2026-09-25 11:22:10–11:28:48 local,
  `runtime/dspy_opt/judge_eval/full_suite_20260925_camturn.log`); 25k's run
  was 1576, +6 here.

## Housekeeping

- `gvd_vlm_raw.jsonl` 1050 → 1144: 2 probe answers, 87 first answers and 2
  retries (`attempt: 2`) from the chain, and the pre-existing test's one row
  per unit-test run. `gvd_live_metric_history.jsonl` untouched (269 rows).
- Results: `runtime/dspy_opt/judge_eval/results_{v3e,heldout_v3e,heldout_v3e_probe}.jsonl`
  (+ `.llama_server.log` each), `phaseC_20260925/results_phaseC_v3e.jsonl`;
  logs `judge_eval_20260925/run_v3e_{probe,chain}.log`.
- `TODO.md` (CRLF): the c038 item closed with these numbers in the judge
  section; the "judge misses still open" item reworded (D02 `614e`, D02
  `53ae` on the retry path, stylized medium, c030); 25l added to the
  evidence list.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
- Id claims: `scripts/next_changelog_id.py` was called twice in this session,
  so `CHANGELOG/.id_claims/2026-09-25m` is a stray claim with no entry (this
  entry is 25l, the first claim). Removing it was denied by the session's
  permission classifier and it is left in place; the next id will be 25n
  unless the operator deletes that one file.

## Open

- D02 `614e` (rig read as viewpoint) unchanged. D02 `53ae`'s retry answer
  (25k) reads the climb out of the canopy as a cut; its gaps are all push-in,
  so no turn mark applies; a push-in / pull-back reading is not fed (it is
  the norm for every walk and flight and would change most prompts).
- c030 stays a false pass: its swings carry `subject_motion`, so it gets no
  mark, and the VLM sees "yellow wall" in all eight frames anyway.
- The estimator's stated limits (25c/e) now reach the prompt: a subject
  spanning the whole frame with no centre excess reads as a camera move, and
  only `TURN_MIN_FRAC` keeps the creek out (0.15 vs 0.20; a faster flow
  would be marked "tilted down"). The drone clips' tilt-up marks (D01
  `3032`, `cc43`) are real climbs and read correctly.
- Gates chosen with c038 in view (section 1); held-out is not blind for
  this change. The next fresh renders (a live pass, or new labels) are the
  test of it. `camera_moves` in every judged history row from now on will
  show what was marked.
- 25h §5 run noise stands (br_c002 0.80 / 0.85 between probe and full run);
  the curriculum and the 0.80 bar are unchanged.
