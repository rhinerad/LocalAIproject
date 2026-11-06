# 2026-09-14o — C021 start low narrow-corridor recovery

C020 last remains accepted on
`eac8d438863f92e884428def8ec8c78a445fdb5196c0dce7c3235a4922782ada`.
C021 start paused after two unconditioned SDXL failures. No video.

The authored start line is Mode B: low through a narrow yellow corridor,
floor and wallpaper filling the frame. Both SDXL candidates reused the
chest-height center-opening plate.

- Donor: `work/runtime/identity_donors/c021_start/c021_start_narrow_corridor_low_imagegen_v1.png`
- SHA-256: `3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`
- Policy `c021-start-hash-pinned-narrow-corridor-v1` /
  `low-narrow-yellow-corridor-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 154 tests passed.

## Controlled rerun

Attempt `f1598c867b2747699faa45158cb7a3c9` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C021 start SHA-256
`3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`.
Stills continued to C021 last. No video.
