# 2026-09-14h — C017 last wallpaper-wall POV recovery

## After C017 start passed

C017 start remains accepted on
`a1a707d0cde7168c4e9927bcc48760080502f0748a0927e01467020b3b32507d`.
C017 last paused after two unconditioned SDXL failures. No video.

## Diagnosis

The authored last-frame line is Mode B: the view turns toward a wall of
repetitive yellow wallpaper. Both SDXL candidates showed a visible camcorder
body (and readable branding on the second). Mechanical QA also failed because
the generic prompt lacks Mode B face/torso language. A hand is not requested.

## Bounded repair

- Donor: `work/runtime/identity_donors/c017_last/c017_last_wallpaper_wall_imagegen_v1.png`
- SHA-256: `7559d8f0ed3dd75f8899351f8cbcc9963078c36b90d7aefdaa6918661df14400`
- Policy `c017-last-hash-pinned-wallpaper-wall-v1` /
  `turn-to-yellow-wallpaper-pov-v1`, `max_attempts: 1`
- Exact-VLM rubric: yellow wallpaper dominates, carpet strip at the bottom,
  no person/hand/camera. Skip identity comparison. Empty-plate subject/pose
  repair remains available.

Preserve the two rejected stills. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 133 tests passed.

## Controlled rerun

Attempt `33580996a6d74e2d818f3e75da224524` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C017 last SHA-256
`7559d8f0ed3dd75f8899351f8cbcc9963078c36b90d7aefdaa6918661df14400`.
Stills continued to C018 start. No video.
