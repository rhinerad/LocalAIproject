# 2026-09-14i — C018 start hand-on-wallpaper recovery

C017 last remains accepted on
`7559d8f0ed3dd75f8899351f8cbcc9963078c36b90d7aefdaa6918661df14400`.
C018 start paused after two unconditioned SDXL failures. No video.

The authored start line is a close Mode B view of a hand pressing into yellow
patterned wallpaper. Both SDXL candidates reused the empty wallpaper wall and
omitted the hand. Mechanical QA also failed on missing Mode B face/torso
language. Generic full-person continuity is inapplicable.

- Donor: `work/runtime/identity_donors/c018_start/c018_start_hand_press_wallpaper_imagegen_v1.png`
- SHA-256: `761b050c5cdee41cd4911e8c33a798876cb653a1ce55245b566fda90050c8e38`
- Policy `c018-start-hash-pinned-hand-wallpaper-v1` /
  `hand-press-yellow-wallpaper-pov-v1`, `max_attempts: 1`

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 136 tests passed.

## Controlled rerun

Attempt `ab4d651616f94c3eb7de01c15fa2af1e` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C018 start SHA-256
`761b050c5cdee41cd4911e8c33a798876cb653a1ce55245b566fda90050c8e38`.
Stills continued to C018 last. No video.
