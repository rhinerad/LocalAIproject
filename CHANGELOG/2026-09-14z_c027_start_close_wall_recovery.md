# 2026-09-14z — C027 start Mode B close-wall recovery

## Receipts, not another IPAdapter retry

The repaired runner reached C027 and paused. GPU was idle (~30 C). No live
supervisor. The two newest attempts
`cd0ce5098823454d9db2bef7888a489c` and `9c1ab4337edf48f5a3a43bd0e69c6a87`
failed before producing an image:

- v2 diagnostic: IPAdapterModelLoader output 0 is MODEL, not IPADAPTER.
- v3 "output 1" fix: output 1 is CLIP, not IPADAPTER.

Those receipts are preserved. Do not restart v3.

The authored C027-start line is Mode B: close handheld view of a yellow-lit
wall, light flickering. The production job had been rewritten as a close
portrait. A selfie/portrait is forbidden. Same class as C026: keep the
physically possible camcorder POV.

## Bounded v4

- Donor: `work/runtime/identity_donors/c027_start/c027_start_close_yellow_wall_imagegen_v1.png`
- SHA-256: `2f4d36f86ad04b2d35b3ceca3223e72e5864b11c968334c408aa22151922b25a`
- Policy `c027-start-hash-pinned-close-wall-v4` /
  `mode-b-close-yellow-wall-flicker-v1`, `max_attempts: 1`
- No ComfyUI / IPAdapter for this copy. Face/body identity comparison skipped.

Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 185 tests passed.

## Controlled rerun

Attempt `85bc7de1e1154bf9a8b6c286672ac9c8` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C027 start SHA-256
`2f4d36f86ad04b2d35b3ceca3223e72e5864b11c968334c408aa22151922b25a`.
Stills continued to C027 last. No video. No IPAdapter retry.
