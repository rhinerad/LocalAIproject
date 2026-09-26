# 2026-09-11e — C002_start both bounded repairs failed; production stopped

## Stop condition
Per operator procedure: after two materially distinct arm-corridor repairs failed, **all production work is stopped**. Evidence preserved. No third method attempted. No video.

## Failure 1 — v1 `c002-localized-arm-down-ipadapter-v1`
- Attempt: `2c0ad89da8334a75b8e6285ec1a16904`
- SHA-256: `f11ab6ba99b6398f23c743a7a2436d562ddfcfcca90589295a1a880c04245f29`
- Mode: `inpaint_identity`, denoise 0.68, no OpenPose, grow_mask_by 8 (hard-coded default)
- Automated VLM: **pass** (overruled)
- Visual: raised-arm corridor filled with translucent **teal/blue glow**; no natural lowered olive-sleeve arm
- Outside corridor: ~98.9% exact-equal to accepted C001_last `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`
- Receipt: `operator_review.json` decision=reject

## Failure 2 — v2 `c002-localized-arm-down-openpose-v2` / `openpose-arm-down-grow2-v1`
- Attempt: `ce34caa723dc422e90ececc8818a51ee`
- SHA-256: `4f733d45183f4a664088592e736f55e46bb00d02366b2233010b708f4e896913`
- Mode: `inpaint_identity_pose`, OpenPose arm-down, denoise 0.55, grow_mask_by **2**
- Automated gate: semantic fail (`semantic review error: Expecting ',' delimiter...` JSON parse from VLM) — still counts as bounded rejection
- Visual: **same teal brush/glow** covering viewer-right arm corridor; room/identity outside mask remain locked (~99.8% exact-equal outside)
- Supervisor paused: `paused_for_identity_recovery` after max_attempts=1

## Anchor unchanged
Accepted C001_last attempt `6e12ff2ab0b84085b765b7dd07a6bd4c` / `1302d430...` still the immutable visual anchor.

## Next requires operator
New repair strategy must be specified by the operator. Do not auto-retry further C002 methods. Still-only; no video.
