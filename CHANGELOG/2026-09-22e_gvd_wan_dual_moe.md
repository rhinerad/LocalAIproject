# 2026-09-22e — Wan 2.2 dual MoE I2V live profile

Used the existing Rockernow Comfy on :8188. Did not start a second backend.

## Dual MoE (`execute_continuous_take`)

- Graph: high-noise Q4 then low-noise Q4, 480×256, 5 frames, 4 steps split
  `end_step=2` / `start_step=2`, `force_offload` on both samplers.
- Extra **11158 MiB** (peak used 11610, baseline 452). Fits 2048 MiB headroom.
  Sequential offload kept peak in the same band as high-noise-only (11198).
- Prompt `1247566e-283f-4218-b29f-02f2df922b97`
- Promoted `wan22_i2v_q4_dual_unvalidated`. Digest
  `a1a22cad0790bcb17425534212f4e9abf51740885480358b2015965ef3b71e4b`.

## LongCat TI2V

- Smoke started after `/free`. Comfy :8188 dropped before `report.json`.
  `longcat_video_unvalidated` stays disabled. GPU now idle (~61 MiB).
