# 2026-09-22a Provisional CLIP live split; 8-step I2V unstable

- Live CLIP on the three loop-labeled stills vs floor 28: C017 start 26.16 reject; C017 end 35.73 admit; generated hallway 33.49 admit. Report: `smoke_provisional_clip_floor.json`.
- `gvd_qa/defaults.py` points `--qa-policy-json` at `provisional_loop_labels_v1.json`.
- Fault tests: 12 OK including missing checkpoint name vs missing class.
- Cold 8-step Wan I2V crashed Comfy during `umt5_xxl_fp16` convert (twice). GPU returned to ~98 MiB. Stable path remains 4-step 5/9/17/33/81-frame takes (~1165x MiB).
