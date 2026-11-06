# 2026-09-10h - C001_last larger-mouth inpaint identity trial (v8)

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10g` (FaceDetailer smile-push-v7: identity OK, smile miss).
No alternate photoreal SDXL checkpoint was wired in `MODEL_PROFILES` besides RealVisXL,
so this trial used a non-FaceDetailer mouth path instead of a checkpoint swap.

## Change

Added `c001-smile-lowerface-inpaint-v8` / `larger-mouth-inpaint-identity-v1`:
- Activates after smile-push-v7 fails once
- Mode: `inpaint_identity` (no FaceDetailer `render_mode`)
- Larger lower-face smile mask `[0.48, 0.198, 0.59, 0.31]`, clamp `0.196`, feather `5`
- IP-Adapter weight `0.80`, denoise `0.40`, `use_openpose: false`
- Tooth-bearing smile prompt; `max_attempts: 1`; immutable wave only
- Also added a C001 smile success pause so a pass cannot continue into the rest of the pack

## Single live attempt

Attempt `27d66f0fa739466bad4643c87bf14033`

- Wave SHA matched `9374d6e2...`; identity anchor SHA matched `0b944e9a...`
- Output still SHA-256: `c052bd182bda64ae650d0391f9d95a711990c3bf876a3c972d05f8c860b32261`
- Peak GPU during load ~32 C / ~9.5 GB; released after render
- Blind continuity: FAIL (`same_person/hair/facial_hair` false)
- Blind observation: face obscured by a solid grey/white rectangle; expression serious; no smile
- Semantic reasons include identity_continuity + missing smile + missing wave evidence
- Ledger: `paused_for_identity_recovery`

## Conclusion

Larger-mouth inpaint at IP 0.80 / denoise 0.40 destroyed the face (opaque grey plate)
and did not produce a smile. Do not accept. Do not promote as reference. No video.
FaceDetailer path saturated without smiling; this inpaint path is unsafe at these
settings. Next reassessment needs a different mouth tool (tighter/safer mask + lower
denoise, or a true alternate checkpoint once one is installed/wired), not another
unbounded FaceDetailer bump.
