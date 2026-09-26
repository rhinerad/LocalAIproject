# 2026-09-21u Provisional floors, held-out ablation, 17/33/81-frame I2V

- `provisional_loop_labels_v1.json`: CLIP min 28 from three loop-labeled stills (reject 26.16, accept 33.49 and 35.73). ImageReward stays unfloored (accepted still at -0.71). Not production calibration.
- Held-out generate omitting the CLIP-sensitive hallway phrase: CLIP 29.7 and 31.4 passed 28, Caption V4 `qwen:corridor` failed twice, `held_out_outcome=rejected`. Phrase not promoted.
- Receipt-gated Wan from generated SDXL still, peak ~1165x MiB across lengths: 17f `i2v_17frame.mp4` (~2s), 33f `i2v_33frame.mp4` (~4s), 81f `i2v_81frame.mp4` (~10s at 8fps).
