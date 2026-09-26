# 2026-09-25e — camera-motion estimator: border-ring fit and subject-motion flag; coherence gate tried and rejected

Follows 2026-09-25c/d. Operator asked for the border-only-blocks refinement
that 25c listed as the next step for the creek-style confounder (subject
motion filling the frame read as a camera move). Built, unit-tested, and
measured on the same 79 labeled clips. Result, plainly: the refinement is a
sound estimator and adds a real subject-motion signal, but it does **not**
fix the creek or the butterfly, and the coherence gate I built alongside it
turned out to be wrong in both directions and was removed before shipping.
CPU only, no VLM, no ComfyUI, no renders.

Backups: `local_agent/{camera_motion.py,test_camera_motion.py}.bak_border_20260925T030000`.
Edits applied by `local_agent/runtime/dspy_opt/judge_eval_20260924/_edit_border.py`
then `_edit_border2.py` (kept as the record; asserts refuse a second run).

## Change (`local_agent/camera_motion.py`, LF)

- Grid 3×3 → 4×4 (64×36 px blocks, the judge's own frame size). The
  translation+scale fit now uses the **outer ring** (12 blocks) and gives
  `dx`, `dy`, `scale`, `response`; the four centre blocks are compared
  against that fit and their mean excess motion is `subject_excess_px`.
  The all-blocks fit is still computed as `full_dx/dy/scale` and, per
  window, `full_frame_camera`, so the two can be compared.
- `_fit_similarity` handles a non-centred block set (the ring's centroid is
  the frame centre, the inner set's is too, but the code no longer assumes
  it).
- Per window: `coherence` (weighted fraction of ring blocks within
  1.0 px + 25 % of the fitted shift), `subject_excess_px`, and
  `subject_motion` (excess ≥ 1.0 px per pair). `camera` is classified from
  the ring sums exactly as before; **coherence does not relabel anything**.
- Public API unchanged for callers: `estimate_camera_motion`,
  `compare_with_claims`, `classify`, `CAMERA_VALUES`. The 25d feed to the
  VLM therefore now carries ring-based labels.
- `test_camera_motion.py` +3 (14): a textured subject sliding across a
  still background is `static` with `subject_motion` true; a field where
  every block slides by its own amount has lower coherence than a clean pan
  but keeps its summed label; a clean pan agrees between ring and full
  frame with coherence ≥ 0.9. The earlier 11 pass unchanged (pan, tilt,
  zoom, cut, blank, thresholds, sign convention).

## What the coherence gate would have done, and why it is not in

The first build relabelled any above-threshold window with mean coherence
below 0.6 as `uncertain` ("incoherent"). Measured on 12 clips at three
tolerances (`camera_motion_border_vs_full.txt` companion run, and the
transcript of this session):

| clip | what the pixels are | coherence (1.0 px + 25 %) |
|---|---|---|
| M03 `1216` creek, good | water filling the frame | **1.00** |
| M03 `2b3d` creek | still water | 1.00 |
| c005 hallway walk | corridor push-in | 1.00 |
| M04 butterfly | wings spanning the frame | 0.99 |
| B01 handheld walk | corridor push-in | 0.92 |
| D01 `8358` drone | forward flight over cliffs | 0.87 |
| c036 handheld | operator in frame, lighting swings | 0.76 |
| D03 `1adb` drone | tracking beside a motorcycle | **0.68** |
| synthetic per-block random slide | not a camera | 0.79 |

Uniform flow is perfectly coherent; a real camera move over a 3D scene is
incoherent because near and far blocks shift by different amounts
(parallax). Tightening the tolerance to 0.75 px + 15 % made 7 of 8 D03
windows `uncertain` and left the creek at 1.00. So the gate would have
thrown away real drone moves and kept the confounder. Removed; `coherence`
stays in the output as a diagnostic with that caveat in the docstring.

## Ring vs full frame on the 79 clips (656 one-second windows)

`runtime/dspy_opt/judge_eval_20260924/camera_motion_border_vs_full.txt`,
refreshed `camera_motion_labeled_clips.{txt,json}`.

- Ring label == full-frame label on the same 4×4 grid: **636/656**.
- Ring label == 25c's 3×3 full-frame label: 608/656; the 48 differences are
  on the chaotic clips (D04 skateboard, c036, c030 drift, M02 bee, D04
  `2d86`), one window at a time, with no way to say which is right without
  labeled camera moves.
- Label distribution is unchanged in shape: push-in 300, static 169,
  pull-back 42, pan-left 35, pan-right 27, tilt-up 24, tilt-down 16,
  uncertain 43.
- `subject_motion` fired on 91 windows. Where it fires hardest it is right:
  D04 skateboard `3f0c` (excess 5.7 px on the flip), c009 (5.1), c030
  (4.3), c036 (3.0), D03 `5c73` (2.7 on the motorcycle). Where the operator
  cared it does not fire: M03 creek 0.1 px (the flow reaches the ring, so
  the ring moves with it), M04 butterfly 0.6 px (wings reach the ring).

## Bottom line

The ring fit is at parity with the full-frame fit on real footage and
strictly better on the synthetic case it was designed for (subject confined
to the centre). It adds a subject-motion flag that fires on genuine
subject action. It does not resolve a subject that spans the whole picture,
and no geometric split of one frame can; that needs either depth (parallax
between far-apart frames) or a labeled camera-motion set to learn against.
Both stay open.

## Tests

- `python -m unittest test_camera_motion test_media_analysis`: 37 OK.
- Full non-live suite: **1550 OK (2 skipped)**, 246 s, exit 0 (2026-09-25, `runtime/dspy_opt/judge_eval/full_suite_20260925_border.log`); +3 tests over 25d.

## Housekeeping

- `TODO.md`: the 25c/d "estimator refinements" item closed with this
  outcome; open item reworded to what is actually left.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- Subject spanning the whole frame (creek, wings) is not separable from a
  camera move by any single-frame-pair geometry; parallax across frames
  farther apart, or a labeled camera-motion set, is the next real step.
- No labeled camera-motion set exists; ring-vs-full disagreements on 48
  windows cannot be adjudicated until one does.
- The 25d feed now sends ring labels to the VLM; re-measured in
  2026-09-25f: same result (127/127 agreement, 0 inversions, 11/11
  deterministic).
