# 2026-09-25b — action log: mandatory cam= slot; camera field now on every line (but always "static")

Follows 2026-09-25a, which found the `extract_video_actions` camera-motion
field present on only about half of all lines even with the repeat penalty
off, and flipping per clip between identical runs. Operator asked for the
compliance fix. Done and measured; one honest limit found on the way.

VLM only, one owned llama-server launch under `gvd_judge_eval.preflight`
(8188 closed, owners idle, GPU ≤ 70 °C at start, 82 °C check before every
call, release and cool-down after). 33 calls, 0 errors, server alive
throughout, GPU 37 °C afterwards. No ComfyUI, no renders.

Backups: `local_agent/{media_tools.py,test_media_analysis.py}.bak_camslot_20260925T004500`.
The edit itself was applied by
`local_agent/runtime/dspy_opt/judge_eval_20260924/_edit_camslot.py` (kept as
the record of the exact replacement; its asserts refuse a second run).

## Change (`local_agent/media_tools.py`, LF)

- `_action_frame_instruction`: the line template gains a mandatory third
  slot, `Frame N | t=… | cam=<camera motion> | <visible state …>`, in both
  the plain and the H3-beats format. New rule text: the slot takes exactly
  one of `static | push-in | pull-back | pan-left | pan-right | tilt-up |
  tilt-down | uncertain`, is mandatory even when the camera is still and
  even when the rest of the line is "no visible change", and is never left
  blank. The camera list moved out of the free-text state list.
- `_action_coverage`: parses `cam=` per line (`_CAMERA_SLOT_RE`, position
  in the line does not matter) against `_CAMERA_MOTION_VALUES`. New fields:
  `camera_labels` (frame → value), `invalid_camera_labels` (a `cam=` value
  outside the vocabulary), `missing_camera_labels`, `camera_complete`. A
  missing or invalid slot is reported, never inferred. `complete` keeps its
  old meaning (frame labels); `warning` now concatenates both problems.
- `extract_video_actions` result `note`: says what `camera_labels` are and
  what `static` does and does not mean (below).
- Tests: `test_action_instruction_…` asserts the slot in both formats;
  new `test_action_coverage_reports_camera_slot_without_inferring_one`
  (valid, case-insensitive, invalid vocabulary, missing slot, all-present).
  Downstream: nothing parses the line format (`lxmf_agent` passes the text
  through), so the template change breaks no consumer.

## Measured (`runtime/dspy_opt/judge_eval_20260924/actions_cam_compliance_ab.py`)

Same 8 clips, ffmpeg recipe (`fps=2,scale=768:-1`, 16–20 frames) and
`repeat_penalty=1.0` as production; old builder (verbatim copy of the
pre-25b function) once, new builder twice. Rows
`actions_cam_compliance_ab.jsonl`, summary `…_summary.json`, log
`actions_cam_compliance_ab_run.log`.

| | lines | well-formed | valid `cam=` slot | camera-word anywhere | clips camera-complete | truncated | mean tokens |
|---|---|---|---|---|---|---|---|
| plain, old | 140 | 140 | **0** | 72 (51%) | 0/8 | 0 | 818 |
| plain, new | 140 | 140 | **140** | 140 | **8/8** | 0 | 806 |
| H3 beats, old | 56 | 56 | 0 | 16 | 0/3 | 0 | 716 |
| H3 beats, new | 56 | 56 | **56** | 56 | **3/3** | 0 | 644 |

Determinism (new builder, run twice): `cam=` values agreed on 11/11 pairs
and no slot went missing in any run; the text was byte-identical on 8/11,
the other 3 being the 16–20-frame batch nondeterminism noted in 25a.
Compliance is fixed and stable; frame-label coverage stayed 100% both ways.

## What the fix does not do

- **Every one of the 196 values is `static`.** That includes D03 (aerial
  follow of a motorcycle) and c036 (handheld camcorder walk). The old free
  text called D03 "Camera is static" on all 16 lines too, so the model's
  judgement did not get worse; it was never there. From a 2 fps batch of
  768 px frames this VLM does not report camera motion. The slot makes the
  field present and deterministic; it does not make it true. Hence the
  `note` caveat: `cam=static` means no camera move was claimed.
- Description content: on the still-hallway clips (c005, c017, D01) the new
  format collapses each line to `no visible change` (17 chars) where the
  old one repeated a 100-char description of the same unchanged frame; the
  instruction asks for exactly that. On the moving-subject clip D03 the two
  new runs disagree: one keeps the motorcycle's progress (8 motion verbs,
  like the old run's 11), the other writes "Same aerial view … no visible
  change" on 15 of 16 lines (0 motion verbs). That is the batch
  nondeterminism, but the new template's leading slot may make the
  no-change attractor easier to fall into; not resolved on n = 1 clip.

## Tests

- `python -m unittest test_media_analysis`: 23 OK.
- Full non-live suite: **1536 OK (2 skipped)**, 310 s, exit 0 (2026-09-25, `runtime/dspy_opt/judge_eval/full_suite_20260925_camslot.log`); +1 test over 25a.

## Housekeeping

- `TODO.md`: the 25a "camera-motion field compliance" item closed with
  these numbers; new open item for camera-motion *accuracy*.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- Camera-motion accuracy. The VLM answers `static` for everything, so the
  field carries no information. A deterministic estimator from consecutive
  frames (global translation via phase correlation for pan/tilt, scale
  change for push/pull, on the same 64×36 decode `video_judge` already
  uses) would give a real value per window that `_action_coverage` could
  report beside the model's claim. Not started.
- The leading `cam=` slot vs a trailing one (description first, camera
  last) was not A/B'd; worth one run if the D03-style collapse shows up in
  production logs.
- Another 33 rows of texts in `actions_cam_compliance_ab.jsonl`; nothing
  appended to `gvd_vlm_raw.jsonl`.
