# 2026-09-14g — C017 start hand-press floor-POV recovery

## After C016 last passed

C016 last v2 remains accepted on donor
`088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75`.
The stills runner then reached C017 start and paused after two unconditioned
SDXL failures. No video was started.

## Diagnosis

The authored C017 start line is a Mode B floor POV: a hand presses into
unfamiliar damp carpet at the bottom of frame. The production prompt instead
asked for a kneeling actor. Both renders were floor-level Backrooms plates;
the second invented a distant standing figure. Mechanical QA also failed
because the generic prompt lacks Mode B face/torso prohibition language.
Generic full-person continuity is inapplicable.

## Bounded repair

- One checksum-pinned donor:
  `work/runtime/identity_donors/c017_start/c017_start_hand_press_carpet_imagegen_v1.png`
- SHA-256: `a1a707d0cde7168c4e9927bcc48760080502f0748a0927e01467020b3b32507d`
- Policy `c017-start-hash-pinned-hand-press-pov-v1` /
  `hand-press-damp-carpet-pov-v1`, `max_attempts: 1`
- Exact-VLM rubric: one olive-cuffed hand pressing into damp carpet, no face
  or torso, no camera/operator, skip identity comparison.

Preserve the two rejected SDXL attempts. Do not seed-spin.

## Verification

```
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 130 tests passed.

## Controlled rerun

Attempt `9d77805f8c6f4e47a1e27aaf1ecfb3db` copied the donor and passed exact
Qwen2.5-VL Caption V4 / llama.cpp. C017 start SHA-256
`a1a707d0cde7168c4e9927bcc48760080502f0748a0927e01467020b3b32507d`.
Stills continued to C017 last. No video.
