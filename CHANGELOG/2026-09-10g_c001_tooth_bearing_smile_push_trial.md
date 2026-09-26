# 2026-09-10g — C001_last tooth-bearing smile-push FaceDetailer trial

## Scope

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`. Still-only. C001 locked. No video.
Follow-on to `2026-09-10f` (identity-lock-v6: continuity pass, smile miss).

## Change

Added `face-crop-tooth-bearing-smile-push-v7`:
- Activates after identity-lock-v6 fails once
- Keeps IP-Adapter weight `0.80`
- Raises FaceDetailer denoise to `0.48`
- Stronger weighted smile prompt `(tooth-bearing smile:1.6)` etc.
- Negatives add `neutral expression`, `no smile`, `unsmiling`
- `max_attempts: 1`; immutable wave only

## Single live attempt

Attempt `e2f704eebf8247888b3c4fba6a0e0d2e`

- Policy/weights as above; wave SHA matched
- Output still SHA-256: `a0eac495dedeafd26262f39204d499cd9a71fbfb358453d1b6a3408cb823b4d9`
- Peak GPU ~42 C; `:8188` released
- Blind continuity: PASS (all true)
- Semantic fail: `blind evidence does not show the required smile or grin`
- Ledger: `paused_for_identity_recovery`

## Conclusion

Identity remains locked at IP 0.80; stronger smile weights + denoise 0.48 still
did not produce a blind-visible smile. Do not accept. Do not promote as reference.
No video. FaceDetailer+high IP may be saturating expression; next reassessment
should consider a different mouth-edit path or a documented checkpoint trial on C001 only.

