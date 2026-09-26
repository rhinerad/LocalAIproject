# 2026-09-11f — C002 teal-glow root cause and strategies

## Root cause (measured)
On v2 attempt `ce34caa7…`:
- Teal pixels: **55.5% inside mask, 0% outside** → pure inpaint fill failure.
- OpenPose `left_shoulder` (0.575, 0.300) was **OUTSIDE** the editable arm polygon.
- Elbow/wrist were inside → floating raised-hand hole without shoulder attachment.
- Outside mask stayed ~99.8% exact-equal to accepted C001_last.

## Ranked strategies
1. **v3 Shoulder-inclusive union mask (implementing now)** — union raised-hand erasure + hanging-arm corridor including left_shoulder; grow_mask_by=0; feather 2; denoise 0.58; OpenPose arm-down.
2. **Two-pass erase→arm** — Pass A background-fill raised hand only; Pass B hanging-arm from shoulder.
3. **Non-SD erase + SD arm** — deterministic fill of raised-hand hole, SD only for hanging arm.
4. **Contralateral donor composite** — warp the already-down right arm (cv2 not installed).
5. **Operator donor still** — hash-pinned paste into arm corridor only.

## Constraint
Still-only. Preserve evidence. GPU ≤82°C. Direct script only.
