# 2026-09-10k - C001_last mid-IP FaceDetailer smile trial (v11)

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on after inpaint mouth trials v8–v10 failed.

## Change

Added `c001-smile-facedetailer-midip-v11` / `face-crop-tooth-bearing-mid-ip-v1`:
- Activates after medium-mouth inpaint-v10 fails once
- FaceDetailer `face_refine_identity`
- IP-Adapter weight `0.70` (between v5 smile@0.58 and v6 lock@0.80)
- FaceDetailer denoise `0.46`
- Tooth-bearing sitcom smile prompt; `max_attempts: 1`; immutable wave only

## Single live attempt

Attempt `93d570a84f034e6cabb95152e2b115a8`

- Wave SHA matched; output SHA-256: `2197901f96b76ce9262a840cfb869db4b22fbb61e665298c7a2e4cb84ce5a1b5`
- Peak GPU ~34 C / ~10.7 GB during load; released after render
- Blind continuity: all **true** (person/hair/beard/clothes/room)
- Blind expression: **serious**; only semantic fail: no smile/grin
- Ledger: `paused_for_identity_recovery`

## Conclusion

Mid-IP FaceDetailer preserved identity like v6/v7 and still produced no
blind-visible smile. Do not accept. Do not promote. No video.
At IP ≥ ~0.70 FaceDetailer locks identity and saturates expression; only the
lower-IP v5 pass ever showed a smile, and that broke continuity.
