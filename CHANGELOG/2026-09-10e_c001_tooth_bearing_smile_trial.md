# 2026-09-10e — C001_last tooth-bearing FaceDetailer smile trial

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10d` / `work/C001_SMILE_REFINEMENT_CLAUDE_HANDOFF_2026-09-10.md`.

## Change

Added bounded policy revision `face-crop-tooth-bearing-smile-v5` under
`c001-smile-facedetailer-ipadapter-v5` in `work/run_prompt_pack_production.py`
`apply_smile_refinement()`:

- Activates only after `face-crop-strong-smile-guidance-v4` has one preserved failure
- Face-only positive prompt demands a clearly visible natural **tooth-bearing**
  friendly sitcom smile
- Negative no longer bans open mouth; still rejects oversized/deformed teeth and
  closed/sealed lips
- FaceDetailer denoise `0.50`, IP-Adapter weight `0.58`, `max_attempts: 1`
- Working reference remains the immutable wave intermediate; failed refinements
  cannot become anchors

Regression: `work/test_still_retry_not_stop.py::test_failed_strong_smile_promotes_tooth_bearing_face_crop` (OK).

## Single live attempt

Attempt `b4d497043d1349a88ef046516cc8d648`

- Policy: `c001-smile-facedetailer-ipadapter-v5` / `face-crop-tooth-bearing-smile-v5`
- Intermediate wave SHA-256: `9374d6e23a5d81e42dbea377c5b8a4203ea521f731ee6364bc2675853b13b014` (match)
- Output still SHA-256: `aa6d2ec8679fbd6493e4042f11680ac0ca70726807a330444dd8650fbbcce7b7`
- Peak GPU during run ~53 C (under 82 C ceiling); `:8188` released after
- Prompted main verdict claimed smile + identity OK
- Blind continuity **failed**: `same_person=false`, `same_hair=false`,
  `same_facial_hair=false` (clothing/room true)
- Semantic status: fail; evidence preserved (`still.png`, `qa.json`, `failure.json`,
  `identity_control.json`, `render.log`)
- Ledger returned to `paused_for_identity_recovery` after the one bounded attempt

## Conclusion

Do **not** accept this still. The tooth-bearing guidance path broke identity under
blind continuity even though the prompted verdict hallucinated a pass. Preserve
and reassess the FaceDetailer/IP-Adapter settings or crop path before another
trial. Do not start video. Do not promote this PNG as a reference.

