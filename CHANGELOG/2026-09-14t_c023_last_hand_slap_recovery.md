# 2026-09-14t — C023 last hand-slap-wall recovery

C023 start remains accepted on
`a4f84b1d838847d11f3f061201a31ba80b11b5732e081e546505bf713c5a68d2`.
C023 last paused after two unconditioned SDXL failures. The authored last
line is Mode B: the frame lurches down as a hand slaps the wall for balance.
SDXL kept the gesturing-hand plate.

- Donor: `work/runtime/identity_donors/c023_last/c023_last_hand_slap_wall_imagegen_v1.png`
- SHA-256: `8c3248baeb9432e7ba356fcc33a1f093d964568ed934093ee18db02bf1b08921`
- Policy `c023-last-hash-pinned-hand-slap-v1` /
  `lurch-hand-slap-wallpaper-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin. Do not start videos.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 169 tests passed.

## Controlled rerun

Attempt `66439c03a80c4885af499b9433e07f19` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C023 last SHA-256
`8c3248baeb9432e7ba356fcc33a1f093d964568ed934093ee18db02bf1b08921`.
Stills continued to C024 start. No video.
