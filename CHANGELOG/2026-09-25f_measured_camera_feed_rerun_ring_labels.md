# 2026-09-25f — 25d feed A/B rerun with the 25e ring labels: same result

Closes the caveat left in 2026-09-25e: the measured-camera feed to the VLM
(25d) had been A/B'd with the 3×3 full-frame labels, and 25e switched the
estimator to the 4×4 border-ring fit. Operator asked for the rerun. No code
change in this entry; evidence only.

VLM only, one owned llama-server launch under `gvd_judge_eval.preflight`
(8188 closed, owners idle, GPU 28 °C at start, 82 °C check before every
call, release and cool-down after). 33 calls, 0 errors, server alive
throughout, GPU peak 69 °C, idle afterwards. No ComfyUI, no renders.

Harness unchanged: `runtime/dspy_opt/judge_eval_20260924/actions_cam_fed_ab.py`
(it calls `camera_motion.estimate_camera_motion`, so it picked up the ring
fit, and `media_tools._action_frame_instruction`, so it used the shipped v2
wording). Previous run preserved as `actions_cam_fed_ab_v2.jsonl` /
`…_summary_v2.json` / `…_run_v2.log`; this run is the unsuffixed set.

## What the ring changed in the inputs

Same 8 clips, 0.5 s windows (fps 2). The ring labels differ from the 3×3
full-frame labels on 11 of 140 windows, on 3 clips:

- M04 `15e7` (butterfly, locked macro): windows 3–6 **push-in → static**.
  At this window size the ring no longer reads the wings' expansion as a
  camera move; the 1 s table in 25e still shows 3 push-in windows for this
  clip, so this is window-size dependent, not a general fix.
- c005 (hallway walk): windows 6 and 17 swap static/push-in.
- c036 (handheld, operator in frame): 5 windows relabelled among
  push-in / pan / tilt / static.

The other 5 clips' labels are identical. All `cur` rows (instruction
without measurement) are byte-identical to v2, as they must be.

## Result

| plain format, 8 clips, 140 lines | current (25b) | fed, v2 (3×3 labels) | **fed, ring labels** |
|---|---|---|---|
| `cam=` agrees with measurement | 49/127 | 127/127 | **127/127** |
| disagreements / inversions | 78 / – | 0 / 0 | **0 / 0** |
| "no visible change" lines | 86 | 86 | 71 |
| motion verbs in descriptions | 30 | 24 | 24 |
| mean description chars | 76.8 | 66.5 | 65.0 |
| well-formed / slot missing / truncated | 140 / 0 / 0 | 140 / 0 / 0 | 140 / 0 / 0 |
| mean tokens | 806 | 778 | 775 |
| fed repeat byte-identical | – | 9/11 | **11/11** |

H3 beats (3 clips, 56 lines): 56/56 agreement, 0 disagreements, 56 "no
visible change" lines, 17 chars mean, unchanged from v2.

The only texts that differ from v2 are the 8 fed rows of the 3 clips whose
measured labels changed (c005 plain+H3, M04 plain, c036 plain, each with
its repeat); the model copied the new labels exactly. The 15 fewer "no
visible change" lines are M04: with `static` instead of `push-in` in hand
the model describes the wings' state per frame instead of writing "no
visible change" under a camera move it could not see.

## Bottom line

The 25d feed behaves the same with the ring labels: exact copy, no
inversions, descriptions intact, and this time fully deterministic across
the 11 repeats. The 25e caveat is closed.

## Housekeeping

- `CHANGELOG/2026-09-25e_…md`: the "not re-measured" open item now points
  here.
- `TODO.md`: the closed 25d item notes the rerun.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
- No code changed; the last full non-live suite (25e) stands: 1550 OK (2 skipped).
- Another 33 rows of texts in `actions_cam_fed_ab.jsonl`; nothing appended
  to `gvd_vlm_raw.jsonl`.
