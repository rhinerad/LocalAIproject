# 2026-09-21t Reference metrics, live PromptTester, 9-frame I2V

- CPU DINO 0.62 and CLIP-image 0.85 between generated SDXL hallway and `br24_C017_end`. CLIP text on PromptTester variants: baseline 33.53; omitting the yellow-carpet hallway phrase drops to 28.20. Observations only.
- Live Comfy `PromptTester` + `GVDPromptPlan` prompt `bafb227a-8715-4485-95cd-a828dfc409b4` returned 7 variants.
- Receipt-gated Wan 9-frame 480x256 4-step: peak 11673 MiB (same neighborhood as 5-frame). Mux `local_agent/runtime/gvd_qa/i2v_9frame.mp4`. Client hit 1200s; Comfy finished and history was reaped.
