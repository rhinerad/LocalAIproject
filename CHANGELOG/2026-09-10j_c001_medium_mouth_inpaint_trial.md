# 2026-09-10j - C001_last medium-mouth ultra-low-denoise inpaint trial (v10)

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10i` (tiny-lip inpaint-v9: white mouth patch, no smile).

## Change

Added `c001-smile-medium-mouth-inpaint-v10` / `medium-mouth-ultra-low-denoise-v1`:
- Activates after tiny-lip inpaint-v9 fails once
- Medium-small mouth mask near original v4 size `[0.490, 0.220, 0.575, 0.292]`
- IP-Adapter `0.90`, denoise `0.24`, feather `4`, `use_openpose: false`
- Soft closed-to-slight smile prompt; plate/patch negatives
- `max_attempts: 1`; immutable wave only

## Single live attempt

Attempt `325d4cf5b8724d73b3a47425c01cca59`

- Wave SHA matched; output SHA-256: `009561d0b3de78555b06a639a664485c4d3701c2127360c5006559fe1768de59`
- Peak GPU ~48 C / ~9.6 GB during sample; released after render
- Blind continuity: `same_person`/`same_facial_hair` **false** (beard/face shape drift noted)
- Blind expression still serious; no smile/grin
- Ledger: `paused_for_identity_recovery`

## Conclusion

Medium mouth + ultra-low denoise still failed: no smile, identity drift vs wave.
Do not accept. Do not promote. No video.
Inpaint mouth masks on RealVisXL (tiny→medium→large) have not produced a clean
blind-visible smile without artifacts or identity loss. FaceDetailer remains the
only path that ever showed a smile (v5), and that broke identity.
