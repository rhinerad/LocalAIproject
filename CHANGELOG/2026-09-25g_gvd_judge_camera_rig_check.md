# 2026-09-25g — GVD judge: eighth check, camera rig / drone / operator in the picture

Follows 2026-09-24q/r/ac/ad/ae. 24q's final measurement left one false-pass
family fully open: "wrong viewpoint 3/3 (drone visible in frame: D02 `614e`,
D01 `3032`; camera operator in shot: c036)". The prompt-side mitigation
(2026-09-08 camera-visibility invariant, 09-08r, 09-09u: negative prompts and
the "camcorder is the viewpoint, its body/lens/tripod/operator are outside the
frame" rule) evidently does not stop the renderer from producing these, so
this entry adds a detection-side backstop in the judge. This is a different
"camera" concern from 2026-09-25b–f (camera *motion* direction for the action
log); `camera_motion.py` and `media_tools.py` are untouched.

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
28–36 °C at start, 82 °C check before every clip, release and cool-down after
each run). Five llama-server launches (three 3-clip probes, the 50-clip set,
the 29-clip set), 0 crashes, 0 connection resets, ~8.7 s per clip, GPU 38 °C
after. No ComfyUI, no renders.

Backups: `local_agent/{video_judge.py,test_video_judge.py}.bak_camrig_20260925T023018`.
Edits applied by `local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_camrig.py`,
`_edit_camrig_v2.py`, `_edit_camrig_v3.py` (kept as the record; their asserts
refuse a second run). All files LF.

## Change (`local_agent/video_judge.py`)

- `CHECK_KEYS` gains `camera_or_operator_visible` (eighth, after
  `text_or_logo_visible`). `normalize_checks`, the "fault checks unanswered"
  reason and rule (a) from 24q (a `constraint_broken` that names a check key
  is a dump, not a quote) pick it up automatically.
- `VIDEO_JUDGE_SYSTEM_PROMPT`: the failure list names "showing the recording
  rig itself (a camera, a tripod, the drone that should be carrying the
  camera, or the operator) in the picture"; the per-frame line asks for "any
  camera, drone, tripod or person holding a camera that is itself an object
  in the picture"; and the question reads (final wording, v3):

  > answer from the pictures only, not from the BRIEF: is any recording
  > equipment or its operator IN the picture in any frame: a camera or
  > camcorder body, a lens, a tripod or light stand, a drone / quadcopter /
  > aircraft seen from outside (from behind, beside, above or below it, flying
  > ahead of the camera), a boom, a monitor, or a person holding, carrying or
  > looking through a camera or camcorder? If a drone is an object in the
  > picture, the camera is not on that drone, whatever the BRIEF calls the
  > shot: "yes". If a person is holding a camcorder in the picture, that
  > person is the operator: "yes". A view seen THROUGH a camera or drone with
  > none of this in the picture is "no", and a still, locked-off framing is
  > "no": the fault is the rig or operator appearing in the image, not the
  > shot being static

  Deliberately **not** in the question: the task's suggested "a viewpoint that
  looks unusually static or shake-less while the brief implies handheld
  footage also counts". From eight stills this VLM cannot judge shake, the
  measured camera-motion estimator (25c) is the instrument for that, and
  locked-off framings are legitimate in this pack (br_c003 "static reference
  framing", the Mode A audition briefs). Putting it in the same yes/no would
  create exactly the false-fail mode this entry has to avoid.
- `fault_caps`: `camera_or_operator_visible == "yes"` caps
  `text_video_alignment` at **0.25**, unless `_GEAR_REQUESTED` matches the
  brief. 0.25 sits between "subject absent" (0.20: nothing requested is
  there) and "wrong medium" (0.30: the scene is there in the wrong form): the
  scene is usually there, seen from the wrong side. Any cap ≤ 0.40 already
  fails both curriculum bars (0.60 / 0.80), so the value only orders rejects
  among themselves.
- `_GEAR_REQUESTED`: a brief that has the actor handle or inspect the gear
  asks for it to be in the picture (c013, good: "in front of the tripod …
  checks everything on the tripod (tripod legs, cable)"; the sitcom pack's
  "grips the camera body", "examining the tripod legs"). It matches an
  interaction verb followed within three words by tripod / camera body /
  camcorder body / light stand / boom / rig / lens. "camcorder on a locked
  tripod", "no visible camera body in frame", "no tripod lock" and "in front
  of the camera" (the viewpoint camera of every audition brief) do not match,
  so the check binds on those. Nine probe briefs in the edit record.

Everything else in the judge (seven older checks, caps table, CPU detector,
frame count, `repeat_penalty=1.0`) is unchanged in this entry.

## Wording was measured three times on the three named clips (`--only`)

| wording | D02 `614e` | D01 `3032` | c036 | results |
|---|---|---|---|---|
| v1: question ends "when the BRIEF does not ask to show it" | no (0.9) | **yes** (0.0, VLM also called the subject absent) | no (0.8) | `results_v3a_w1.jsonl` |
| v2: visual only, "if you can see a drone … yes" | no (0.9) | yes (0.25) | **yes** (0.25) | `results_v3a_w2.jsonl` |
| v3 (shipped): + drone "seen from outside … whatever the BRIEF calls the shot" | no (0.9) | yes (0.0) | yes (0.25) | `results_v3a.jsonl` |

- v1 failed on c036 because the VLM echoed the brief's own "no visible camera
  body" into its frame lines while also writing "actor holding camcorder to
  face"; the brief clause in the question invited that. v2/v3 answer from the
  picture: "A person holding a camcorder in a dimly lit hallway … looking
  through the camcorder lens".
- **D02 `614e` is not caught by any wording.** Its frame lines are
  byte-identical across v2 and v3 ("FPV drone view through dense pine canopy,
  weaving between trunks …" ×8) although the quadcopter fills the centre of
  all eight judge frames (`judge_eval_20260925/sheets/gvd_GVD-D02_614e3cb8a3_judge8.png`).
  The VLM reads the brief's "FPV drone" as the viewpoint and never lists the
  aircraft as an object; on D01 `3032` (drone small against water) it does.
  This is perception anchored on the brief's camera words, not a wording
  problem, so it was not forced. Left open below.

## Full sets, same code, against the shipped judge (`results_v2b` / `results_heldout_v2b`)

Reports: `runtime/dspy_opt/judge_eval/report_v3a.json`, `report_heldout_v3a.json`;
per-clip diff: `judge_eval_20260925/compare_results.py`. FP = reject clips that
pass, FF = good clips that fail, hc = high-confidence labels.

| set | bar | FP v2b → v3a | FF v2b → v3a | hc FP | hc FF | partial pass | AUC |
|---|---|---|---|---|---|---|---|
| tuning (50) | 0.60 | 10/35 → **8/35** | 0/8 → 0/8 | 4/27 → 4/27 | 0/4 → 0/4 | 6/7 → 6/7 | 0.821 → **0.836** |
| tuning | 0.80 | 10/35 → 8/35 | 0/8 → 0/8 | 4/27 → 4/27 | 0/4 → 0/4 | 6/7 → 6/7 | |
| held-out (29) | 0.60 | 2/12 → **1/12** | 3/12 → **4/12** | 1/7 → **0/7** | 2/5 → 2/5 | 2/5 → 3/5 | 0.809 → 0.806 |
| held-out | 0.80 | 2/12 → 1/12 | 3/12 → 4/12 | 1/7 → 0/7 | 2/5 → 2/5 | 2/5 → 2/5 | |

Reject faults still passing at 0.60, tuning: wrong_viewpoint **3/3 → 1/3**
(`614e`), requested_subject_absent 2/13 → 1/13, location_drift 3/4 → 2/4,
constraint_violation 2/5 → 1/5; requested_action_absent 1/3 → 2/3 and
scene_change 0/4 → 1/4 (M05, below). Distinct triples 17 → 23 (top share 0.18).

Where the new check fired (all seven are labeled reject, none good or partial):
tuning D01 `3032`, c036, D03 `ffd4` (constraint "no camera body in frame"),
M02 `9405`, c009 (camcorder reflection); held-out br_c001 `32ce` and
br_c001 `855b` (label: "a tripod camcorder stands in the shot", the held-out
wrong_viewpoint clip, now 0.25 with the rig cap). It did **not** fire on c013
(tripod inspected on purpose; the VLM answered "no" and `_GEAR_REQUESTED`
would have exempted it anyway) nor on br_c003 (static reference framing,
still 0.80). So the false-fail mode the task warned about, a legitimately
static or gear-showing brief being capped, did not occur on either set.

Verdict flips at 0.60 (the VLM is prompt-sensitive; 24q saw the same both
ways):
- tuning, caught: D01 `3032`, c036 (this check), M04 `15e7` (subject count,
  a 24q/v2b false pass regained). Lost: M05 `c6a5` (raindrop; subject now
  called visible). Partial D05 → fail (text/logo "yes"), partial M02 `b5ed`
  → pass (time-of-day "yes").
- held-out, caught: M04 `4c83` (subject absent). **New false fail: c038**
  (good, medium): the VLM now describes F4–F8 as "close-up of yellow
  wallpaper, no hallway" and answers abrupt cut / different place / subject
  absent; the clip turns to face the wall as its brief asks ("turns to
  confirm … walks towards the wall"). The rig check answered "no"; this is a
  requested camera move read as a cut, the same family as 24r's requested
  flicker read as a cut, and 2026-09-25h addresses both. Partial br_c005 →
  pass.
- **1 parse failure** (0 in v2b): held-out br_c001 `32ce` (reject) wrote
  `constraint_broken` outside the checks object and closed the JSON before
  the three scores (`missing or invalid float score`). Same shape as the
  24ae failure mode, now once in 79 at `repeat_penalty=1.0` with the longer
  checklist. In production that is a `_fail_result` (0.01), not a judged
  clip. Noted as open.

## Tests

- `test_video_judge.py` +6 (`CameraRigCheckTests`): key asked and parsed;
  cap 0.25 with min/mean recomputed and `scores_vlm` kept; "no" leaves
  scores alone; the brief exemption (c013 wording, "grips the camera body")
  and four viewpoint/negative mentions that must still bind; lowest cap
  wins against subject-absent; unanswered check reported, not failed. The
  `_checks()` fixture carries the new key as "no", so every older cap test
  runs against the eight-key list.
- `python -m unittest test_video_judge test_dspy_orchestrator test_media_accuracy_gate test_generalized_video_director test_llama_cpp_client`: 129 OK.
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
  baseline before any edit this session **1550 OK (2 skipped)**, 301 s
  (`runtime/dspy_opt/judge_eval/full_suite_20260925_baseline_preA.log`; same
  count as 25e/25f). On the Phase A files (`full_suite_20260925_camrig.log`,
  333 s): 1560 run, 1555 OK, 2 skipped, **5 not OK**, stated plainly: four
  are `LightingDipTests` written ahead of their code for 2026-09-25h (they
  need `_dip_returns_same_picture` and the flicker prompt rule, which were
  not yet applied), and one was this entry's own
  `test_check_key_is_asked_and_parsed` asserting the v2 phrase "THROUGH the
  camera" after v3 had reworded it to "THROUGH a camera or drone". The module
  run after the v3 edit was misread as passing (a `tail -1` showed a buffered
  test print, not the unittest summary). Assertion fixed to the shipped
  wording; the clean full-suite run on the final files is in 2026-09-25h
  (Phase A and B land in the same `video_judge.py`).

## Open

- D02 `614e`: the VLM does not list the quadcopter as an object when the
  brief says "FPV drone". A brief-free first pass ("list every object") or a
  per-frame object question would be the next thing to try; not a threshold.
- c038 false fail (requested turn to a wall read as a cut) → 2026-09-25h.
- One JSON closed before the scores (br_c001 `32ce`). A retry on
  `missing or invalid float score` in `run_qwen_director_scores` would turn
  it into a judged clip; not done here.
- `gvd_vlm_raw.jsonl` gained 88 debug rows (9 + 50 + 29);
  `gvd_live_metric_history.jsonl` untouched (261 rows).
