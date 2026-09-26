# 2026-09-10i - C001_last tiny-lip inpaint trial (v9)

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10h` (larger-mouth inpaint-v8: grey face plate).

## Change

Added `c001-smile-tiny-lip-inpaint-v9` / `tiny-lip-inpaint-low-denoise-v1`:
- Activates after larger-mouth inpaint-v8 fails once
- Lip-only mask `[0.505, 0.238, 0.560, 0.278]`, clamp `0.236`, feather `3`
- IP-Adapter `0.88`, denoise `0.30`, `use_openpose: false`
- Soft tooth-hint smile prompt; negatives reject grey/white plates
- `max_attempts: 1`; immutable wave only

## Single live attempt

Attempt `58350556dbe64dc987b6243e0939948d`

- Wave SHA matched; output SHA-256: `c4a782a9d276d7f944436b6850bdfdf7ceee04d4caf349680bdf669bf059c9e3`
- Peak GPU ~37 C / ~9.3 GB during load; released after render
- Blind continuity flags: same_person/hair/facial_hair/clothing/room **true**
- Continuity differences note: white rectangular object covering mouth/nose
- Blind expression: **serious**; fail reason: no smile/grin
- Ledger: `paused_for_identity_recovery`

## Conclusion

Tiny lip mask avoided the full-face grey plate but reintroduced the classic
tiny-mask mouth artifact (white patch) and still no smile. Do not accept.
Do not promote. No video.
