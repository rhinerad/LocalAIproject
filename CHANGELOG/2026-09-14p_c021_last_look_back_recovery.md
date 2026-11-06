# 2026-09-14p — C021 last look-back corridor recovery

C021 start remains accepted on
`3c90e7ba037b5063f226acfc2244a3d1a0d90c185c355e7bce7b85a2ed4cfd88`.
C021 last paused after two unconditioned SDXL failures. No video.

The authored last-frame line is Mode B: the view swings back over the
shoulder toward the corridor behind. Both SDXL candidates showed generic
office hallways with doors, knobs, and an exit sign.

- Donor: `work/runtime/identity_donors/c021_last/c021_last_look_back_corridor_imagegen_v1.png`
- SHA-256: `50127899525009d2786b68b9b7a93273595e2c31541ac4706af9829ae6b956f7`
- Policy `c021-last-hash-pinned-look-back-v1` /
  `over-shoulder-corridor-behind-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 157 tests passed.

## Controlled rerun

Attempt `78d518fbeda345d9a9af97f551add488` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C021 last SHA-256
`50127899525009d2786b68b9b7a93273595e2c31541ac4706af9829ae6b956f7`.
Stills continued to C022 start. No video.
