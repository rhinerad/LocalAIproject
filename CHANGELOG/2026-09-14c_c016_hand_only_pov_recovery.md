# 2026-09-14c — C016 hand-only POV recovery

## Problem

The two ordinary C016 start-frame SDXL attempts were preserved and rejected.
The authored shot is a fallen-camcorder floor POV showing only carpet and one
hand at the lower edge, but the generic full-actor continuity rubric demanded
an actor, clothing, and face. That is a category mismatch, not evidence that a
full actor should be invented into the shot.

## Bounded repair

- Added one checksum-pinned C016 start candidate at
  `work/runtime/identity_donors/c016_start/c016_start_floor_hand_backrooms_imagegen_v1.png`.
- SHA-256: `fc7893767a312afb317d6176833899fb990390e3ebf3c08a1ad0772674da6e5d`.
- Added `c016-start-hash-pinned-floor-hand-pov-v1` to the still runner. It is
  eligible only after two completed base failures and has `max_attempts: 1`.
- Its exact-VLM rubric is specific and strict: Backrooms interior, carpet,
  exactly one hand plus olive cuff at the lower edge, no other body, camera,
  operator, equipment, apartment, text, blood, or gore. Cross-image identity
  comparison is intentionally skipped because this shot cannot show a face.
- The first review found two residual generic checks which incorrectly required
  face/torso prohibition text in the original source prompt and visible jeans
  in a hand-only frame. The candidate image itself passed literal VLM review.
  The v2 policy re-reviews the same immutable pixels with explicit face/torso
  prohibition in the delivery rubric and scopes semantic assertions to that
  truthful shot rubric; it does not weaken forbidden-equipment or setting
  checks and does not create another image.
- The v2 review identified one final generic wardrobe check that required
  hidden jeans merely because the visible sleeve is an overshirt. v3 fixes
  that only when the delivery rubric explicitly says exactly one hand is shown
  and the actor is otherwise outside frame. The same candidate is re-reviewed;
  full-body shots continue to require their visible clothing and footwear.

## Verification and limits

- `python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py local_agent/capabilities.py`
- `python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q`
- Result: 120 tests passed after the v3 hidden-wardrobe repair.
- No existing attempt or QA evidence was changed or deleted. No video was
  started. The candidate must pass the installed exact Qwen2.5-VL Caption V4
  gate before C016 can advance.
