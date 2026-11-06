# 2026-09-14j — C018 last moist-hand pullback recovery

C018 start remains accepted on
`761b050c5cdee41cd4911e8c33a798876cb653a1ce55245b566fda90050c8e38`.
The authored last-frame line is Mode B: a hand pulls back into frame with
moisture visible on the fingers. Generic full-person continuity is
inapplicable. Camera body stays forbidden.

- Donor: `work/runtime/identity_donors/c018_last/c018_last_hand_pullback_moist_imagegen_v1.png`
- SHA-256: `3edae2d0266d33f6a31a5d745571a2e501d32284df144859469fbece905786a7`
- Policy `c018-last-hash-pinned-hand-pullback-v1` /
  `moist-fingers-pullback-pov-v1`, `max_attempts: 1`

Eligible only after two completed base failures. Preserve those attempts.
Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 139 tests passed.

## Controlled rerun

Attempt `73e44e2822174f6195420772b7f53b5b` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C018 last SHA-256
`3edae2d0266d33f6a31a5d745571a2e501d32284df144859469fbece905786a7`.
Stills continued to C019 start. No video.
