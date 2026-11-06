# 2026-09-14s — C023 start look-back gesturing-hand recovery

C022 last remains accepted. C023 start paused after two unconditioned SDXL
failures. The authored start line is Mode B: looking backward down the
corridor with a hand gesturing into frame. SDXL omitted the gesturing hand.

- Donor: `work/runtime/identity_donors/c023_start/c023_start_look_back_gesturing_hand_imagegen_v1.png`
- SHA-256: `a4f84b1d838847d11f3f061201a31ba80b11b5732e081e546505bf713c5a68d2`
- Policy `c023-start-hash-pinned-gesturing-hand-v1` /
  `look-back-hand-gesturing-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 166 tests passed.

## Controlled rerun

Attempt `8be0a3c926d6484493b09e9c8b31ab12` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C023 start SHA-256
`a4f84b1d838847d11f3f061201a31ba80b11b5732e081e546505bf713c5a68d2`.
Stills continued to C023 last. No video.
