# 2026-09-11d — C002_start v1 teal-glow reject + OpenPose v2 armed

## Summary
C002_start localized arm-down inpaint v1 (2c0ad89da8334a75b8e6285ec1a16904, SHA-256 `f11ab6ba99b6398f23c743a7a2436d562ddfcfcca90589295a1a880c04245f29`) received an automated VLM pass but failed visual inspection: the raised-arm corridor was filled with a translucent teal/blue glow instead of a natural lowered olive-sleeve arm. Outside the edit corridor the frame stayed ~98.9% exact-equal to accepted C001_last `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`.

Supervisor PID 39872 (plus watchdog child) was stopped so later stills would not build on the rejected plate. Append-only `operator_review.json` decision=reject was written beside the attempt evidence (qa.json untouched).

## Second repair (exactly one distinct method)
Armed `c002-localized-arm-down-openpose-v2` / `openpose-arm-down-grow2-v1`:
- same arm-only mask + protected-face hard clear
- `inpaint_identity_pose` with OpenPose arm-down joints
- denoise `0.55` (was 0.68)
- `grow_mask_by` override `2` (default was hard-coded 8)
- `max_attempts: 1` — if this fails, stop all production and report both failures

## Code
- `work/run_prompt_pack_production.py`: `apply_c002_identity_recovery(..., attempt_root)` switches v1→v2 after operator reject; passes `--grow-mask-by`
- `work/image_render.py`: `grow_mask_by` parameter/CLI (default 8)
- tests: `test_c002_v1_reject_switches_to_openpose_v2`, `test_inpaint_graph_honors_grow_mask_by_override`
- unittest: 79 OK

## Constraints
Still images only. No video. GPU ceiling 82°C. Evidence trees preserved.
