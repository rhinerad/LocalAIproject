# 2026-09-10f — C001_last tooth-bearing identity-lock FaceDetailer trial

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10e` (tooth-bearing-smile-v5 identity break).

## Change

Added `face-crop-tooth-bearing-identity-lock-v6` under `c001-smile-facedetailer-ipadapter-v5`:
- Activates after `face-crop-tooth-bearing-smile-v5` fails once
- Keeps tooth-bearing sitcom smile prompt
- IP-Adapter weight `0.80`, FaceDetailer denoise `0.42`, `max_attempts: 1`
- Immutable wave intermediate only

## Single live attempt

Attempt `9657de0a39e340088c3a1916322c5fe0`

- Policy/weights as above; wave SHA matched
- Output still SHA-256: `5de658a36448929938ac6faa19a9431c055809d0827a695259a05338721b5cb0`
- Peak GPU ~39 C; `:8188` released
- Blind continuity: **PASS** (same_person/hair/facial_hair/clothing/room all true)
- Semantic fail reason: `blind evidence does not show the required smile or grin`
- Ledger: `paused_for_identity_recovery`

## Conclusion

Identity lock worked; smile is still missing under blind evidence. Do not accept.
Do not promote as reference. No video. Next trial should keep IP lock high and
push smile geometry without lowering identity weight back to the 0.58 failure zone.

