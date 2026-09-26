# 2026-09-14f — C016 last empty-plate subject/pose scope fix

## Why v1 was not a content fail

Attempt `8f6065756a1b47298301a024685f1b64` copied the checksum-pinned empty
floor-POV donor
`088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75`.
Mechanical QA passed. Exact Qwen2.5-VL Caption V4 / llama.cpp returned
`pass: true` with matching floor-level Backrooms setting and composition and
no camera. The gate then failed closed because
`requested_subjects_present` and `requested_pose_or_action_visible` were
false on an authored empty plate. That is the same class of check-scope
mismatch C016 start already recovered with v2/v3: the pixels were not
wrong.

## Bounded v2

- Re-review the same immutable donor. No new image. No seed-spin.
- Policy `c016-last-hash-pinned-floor-pov-v2` /
  `empty-plate-subject-pose-scope-fix-v1`, `max_attempts: 1`.
- Delivery rubric now states that the requested subject is the empty
  floor-level environment and that absence of a person or pose is correct.
- `empty_plate_subject_pose_false_positive()` repairs only those two person
  checks when the delivery rubric forbids a person, blind subjects are empty,
  the camera is absent, and setting/composition/equipment checks already
  passed. It does not skip equipment, setting, or composition.
- `qa_passed()` now also accepts a delivery-rubric recovery whose
  generation prompt hash still matches the authored still, so C016 start
  is not re-copied on every restart. Ordinary authored stills may keep a
  distinct generation-prompt hash; that existing C001-start binding must
  still skip.

## Verification

```
python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py local_agent/media_accuracy_gate.py local_agent/production_integrity.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 127 tests passed after the C001-start skip regression was narrowed.

## Controlled v2 rerun

Attempt `9dd2d9a33a4647b6becae97ef0979486` copied the same donor
`088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75`.
Exact Qwen2.5-VL Caption V4 / llama.cpp plus
`empty_floor_pov_subject_pose_scope_repair` passed. C016 last is
`semantic_check=pass`. No video was started. The stills runner continued
to C017 start.
