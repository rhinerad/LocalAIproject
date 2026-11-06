# 2026-09-25d — action log: measured camera motion fed into the VLM's frame table

Follows 2026-09-25c (deterministic estimator reported beside the model's
`cam=` claim). Operator asked for the measurement to reach the model. It
now goes into the instruction as a per-frame list right after the frame
table, with a rule to write that exact word into the line's `cam=` slot and
to describe the subject from the frames as before. Because this changes the
prompt, the 25b A/B was rerun on the same clips, twice: the first wording
measured badly and was replaced before anything shipped (details below).

VLM only, one owned llama-server launch under `gvd_judge_eval.preflight`
(8188 closed, owners idle, GPU 28 °C at start, 82 °C check before every
call, release and cool-down after). Two launches (one per wording), 33 calls each, 0 errors, server alive throughout, GPU 36–68 °C during, idle afterwards. No ComfyUI, no renders.

Backups: `local_agent/{media_tools.py,test_media_analysis.py}.bak_camfeed_20260925T020000`.
Edits applied by `local_agent/runtime/dspy_opt/judge_eval_20260924/_edit_camfeed.py`
(v1 wording) then `_edit_camfeed_v2.py` (shipped wording); both kept as the
record, their asserts refuse a second run.

## Change (`local_agent/media_tools.py`, LF)

- `_action_frame_instruction(..., measured_camera=None)`: when given
  `{frame: label}`, a block follows the frame table: "Measured camera
  motion per frame (instrument reading of the global image motion, not a
  description of the subject): Frame 1: push-in, Frame 2: static, …", and
  one rule is added: fill each line's `cam=` slot with that exact word for
  that frame (push-in stays push-in, never translate or invert it); only
  where it reads `uncertain` judge the camera from the frames; the
  measurement says nothing about the subject, describe subject position,
  movement and changes from the frames exactly as without it. Without the
  argument the instruction is byte-identical to 25b.
- `extract_video_actions`: the estimator now runs **before** the VLM
  batches (it is CPU, about a second per clip) and its labels are passed
  into every batch's instruction. The post-hoc `camera_motion` /
  `camera_motion_vs_model` fields are unchanged in shape; an estimator
  failure means the VLM runs without measurements and
  `camera_motion_error` says so. The `note` now says that `cam=` agreeing
  with `camera_motion` is expected, not independent confirmation.
- Tests: the instruction test asserts the row text and the rule appear only
  when a measurement is given; the action-job test asserts the measured
  value reached the instruction the VLM was called with. 34 OK across
  `test_media_analysis` and `test_camera_motion`.

## Measured (`runtime/dspy_opt/judge_eval_20260924/actions_cam_fed_ab.py`)

Same 8 clips, ffmpeg recipe (`fps=2,scale=768:-1`, 16–20 frames) and
`repeat_penalty=1.0` as production and 25b. Per clip: current 25b
instruction once, fed instruction twice. Rows `actions_cam_fed_ab.jsonl`,
summary `…_summary.json`, log `actions_cam_fed_ab_run.log`.

Two wordings were measured. The first (v1) put the value inside each
frame-table row (`Frame N: t=… | measured camera: push-in`) with the rule
"copy it into the cam= slot unless the frames clearly contradict it". The
second (v2, shipped) lists the values after the table and says: write that
exact word, never translate or invert it, judge only `uncertain` yourself,
and the measurement says nothing about the subject.

| plain format, 8 clips, 140 lines | current (25b) | v1 fed | **v2 fed (shipped)** |
|---|---|---|---|
| `cam=` agrees with measurement | 49/127 | 107/127 | **127/127** |
| disagreements | 78 | 20 (all push-in → pull-back) | **0** |
| `cam=` values | static ×140 | mixed | mixed, as measured |
| "no visible change" lines | 86 | 108 | **86** |
| motion verbs in descriptions | 30 | 1 | 24 |
| mean description chars | 76.8 | 34.4 | 66.5 |
| well-formed / slot missing / truncated | 140 / 0 / 0 | 140 / 0 / 0 | 140 / 0 / 0 |
| mean tokens | 806 | 671 | 778 |

| H3 beats, 3 clips, 56 lines | current | v1 fed | **v2 fed** |
|---|---|---|---|
| `cam=` agrees with measurement | 10/56 | 56/56 | **56/56** |
| "no visible change" lines / mean chars | 56 / 17 | 56 / 17 | 56 / 17 |

(Agreement is counted over windows the estimator did not call `uncertain`:
127 of 140. Per-clip rows are in the run logs.) Determinism of the fed
instruction: v1 11/11 byte-identical repeats, v2 9/11 (the two differing
are the 16–20-frame batch nondeterminism from 25a; `cam=` values agreed on
all 11).

What the two rounds showed:
- v1 made the model **translate** the reading: every one of its 20
  disagreements wrote `pull-back` where the measurement said `push-in` (D03
  drone tracking ×16, M04 ×4), and the in-row value dragged descriptions
  toward "no visible change" (108 lines, motion verbs 30 → 1, even the S05
  duel lost every action verb). Not shipped; kept as
  `actions_cam_fed_ab_v1.jsonl` / `…_summary_v1.json` / `…_run_v1.log`.
- v2 copies exactly (0 inversions) and leaves the descriptions where the
  current instruction had them: same 86 "no visible change" lines, mean
  length 77 → 67 chars, motion verbs 30 → 24. The drop is mostly M01 (dew
  macro), where the current instruction's 15 "motion" hits were "sunlight
  continues to glint"; v2 writes the same still web without the verb. D03
  went the other way: the current instruction had collapsed it to "no
  visible change" on 15 of 16 lines, v2 with `push-in` in hand reports the
  motorcycle's progress on all 16 (22 motion verbs). S05 got terser (86 →
  46 chars) but still describes the fencers' stance changes.
- `uncertain` windows (D01 `6609`, 13 of 16) are left to the model, which
  answers `static`; that is the documented behaviour, not an error.
- The measurement is now the source of the `cam=` value, so
  `camera_motion_vs_model` agreeing is expected. Its remaining use is to
  catch a batch where the model ignored the list (none in 33 runs).

## Tests

- `python -m unittest test_media_analysis test_camera_motion`: 34 OK.
- Full non-live suite: **1547 OK (2 skipped)**, 304 s, exit 0 (2026-09-25, `runtime/dspy_opt/judge_eval/full_suite_20260925_camfeed.log`); same count as 25c, two tests extended.

## Housekeeping

- `TODO.md`: the 25c "feed the measurement into the frame table" item
  closed with these numbers.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- The estimator's own limits carry into the prompt now: M03-style subject
  motion filling the frame is fed to the model as a camera move. A
  border-blocks-only estimate is the next refinement (25c open item).
- No labeled camera-motion set exists, so "agrees with the measurement" is
  consistency, not accuracy. The 79-clip sanity table in 25c is the closest
  thing to ground truth so far.
- Another 66 rows of texts in `actions_cam_fed_ab*.jsonl`; nothing appended
  to `gvd_vlm_raw.jsonl`.
