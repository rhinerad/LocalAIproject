# 2026-09-25c — deterministic camera-motion estimator beside the action log's cam= claim

Follows 2026-09-25b: the action-log VLM writes `cam=static` for every frame
of every clip, so the field carries no information. Operator asked for the
deterministic estimator. Built, unit-tested on synthetic motion, run over all
79 labeled clips (CPU only, no VLM, no ComfyUI, no renders), and wired into
`extract_video_actions` as a separate measured field next to the model's
claim.

Backups: `local_agent/{media_tools.py,test_media_analysis.py}.bak_cammotion_20260925T013000`.
The wiring edit was applied by
`local_agent/runtime/dspy_opt/judge_eval_20260924/_edit_cammotion.py` (kept
as the record; its asserts refuse a second run).

## New module `local_agent/camera_motion.py` (LF, numpy only)

- `decode_gray(video)`: every frame via ffmpeg, 256×144 grey. `video_fps`.
- `phase_shift(a, b)`: Hann-windowed phase correlation, sub-pixel by
  parabolic fit, returns `(dx, dy, response)`. Response is the normalised
  cross-power peak: ~0.95 for a pure shift, 0.06–0.09 across a real cut.
- `pair_motion(a, b)`: 3×3 block grid, one shift per block, weighted by its
  response, fitted to `v_i = t + s·c_i` (translation plus isotropic scale
  about the frame centre). Blank frames (mean luma < 16, the judge's value)
  and block shifts over a quarter of the block are discarded.
- `estimate_from_frames(frames, fps, windows)` /
  `estimate_camera_motion(video, windows)`: pairs are summed per
  observation window (`start < t(i+1) ≤ end`), pairs with response < 0.10
  are excluded and counted; a window with more than half its pairs unusable
  is `uncertain`. `classify` picks the dominant axis against thresholds of
  2% of frame width/height (pan/tilt) or 2% summed scale (push/pull),
  otherwise `static`. Vocabulary is exactly the `cam=` slot's.
- `compare_with_claims(estimates, camera_labels)`: agree count and a
  disagree list; `uncertain` windows and unclaimed frames are skipped.
- Sign convention, pinned by tests: content moving right = `pan-left`;
  content moving down = `tilt-up`; content moving outward = `push-in`.
- Stated limits (module docstring): this is global image motion, not camera
  motion. A subject filling the frame or flowing water registers as a move;
  dolly and zoom both read as scale; rotation is not modelled.

`test_camera_motion.py` (11): signed roll recovery, unrelated pictures low
response, pan/push/pull/blank pair motion, a five-window synthetic clip
(static → pan-left → tilt-up → push-in → cut), a mostly-cuts window is
`uncertain`, a black clip is `uncertain`, threshold and vocabulary table,
claim comparison. Two things the tests taught: smooth synthetic textures
correlate spuriously in small blocks (the cut test uses white-noise frames),
and gradient pre-filtering was tried and bought nothing on real footage
(adjacent-frame response 0.47–0.78 either way, cut 0.06–0.09), so it is not
used.

## Real footage: all 79 labeled clips, one-second windows

`runtime/dspy_opt/judge_eval_20260924/camera_motion_labeled_clips.{txt,json}`;
67 s for 656 windows (ffmpeg decode dominates; ~0.85 s per clip).

| label | windows |
|---|---|
| push-in | 293 |
| static | 169 |
| pan-left / pan-right | 43 / 28 |
| pull-back | 38 |
| tilt-up / tilt-down | 26 / 16 |
| uncertain | 43 |

Against the briefs (no ground truth beyond them):
- Forward flight and walks read as push-in on every window: D01 `8358`
  (drone toward cliffs), D02 `614e` (FPV through pines), D03 `1adb`
  (tracking beside a motorcycle), every B01 handheld camcorder walk, and the
  good Backrooms hallway walks (c005, c017, c028, c029, c033). The VLM had
  called all of these `static`.
- Locked macros read as static on every window: M01 `4f74` (dew on silk,
  good), M04 `cfa7`/`4c83` (butterfly), M02 `9562`/`9405`.
- Black/logo clips read as uncertain: D01 `6609` (7/8 windows), M01 `5329`
  (8/8), br_c007 (7/8).
- Drift and multi-shot rejects show it: c030 (location drift) `PR PR PR PL
  PL PL Z+ …`, D01 `086a` (late drift) `PL PL TD PR Z- Z- Z- Z-`, c036
  (operator in frame, lighting swings) mixed labels.
- The stated limit shows too: M03 `1216` (creek, good) reads `tilt-up` on
  all 8 windows, which is the water flowing down the frame, not the camera.
  D01 `8358`'s cut at 0.88 s is one excluded pair inside a push-in window,
  so a single cut does not flip a window; sustained cuts do.

## Wiring (`media_tools.extract_video_actions`)

After the VLM batches: `camera_motion = estimate_camera_motion(video,
observation_windows)` and `camera_motion_vs_model = compare_with_claims(…,
coverage.camera_labels)` are added to the result; an estimator failure is
recorded in `camera_motion_error` and never fails the tool. The `note` now
says to prefer the measured field over the model's claim and what the
measurement cannot tell apart. The model's `cam=` slot is unchanged and is
**not** overwritten by the measurement: the two are reported side by side so
a disagreement is visible. `test_media_analysis.py`'s action-job test now
patches the estimator and asserts the measured field, the claim, the
disagreement list and no error.

## Tests

- `python -m unittest test_media_analysis test_camera_motion`: 34 OK.
- Full non-live suite: **1547 OK (2 skipped)**, 275 s, exit 0 (2026-09-25, `runtime/dspy_opt/judge_eval/full_suite_20260925_cammotion.log`); +11 new tests over 25b.

## Housekeeping

- `TODO.md`: the 25b "camera-motion accuracy" item closed; one open item
  for feeding the measurement into the VLM's frame table.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- Give the VLM the measurement: a `(measured camera: push-in)` note per row
  of the instruction's frame table would let the model's `cam=` slot and
  its prose agree with the pixels. It changes the prompt, so it needs the
  25b A/B rerun before it ships.
- Subject-fills-frame vs camera move (M03 creek) is not separable from
  global motion alone; a foreground/background split (e.g. border blocks
  only) is the next refinement if it matters for prompts.
- Thresholds (2% per one-second window) were set from the synthetic tests
  and the 79-clip distribution, not from labeled camera moves; there is no
  labeled camera-motion set yet.
