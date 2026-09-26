# 2026-09-21r generate_until_accepted hybrid

- `HybridPhaseController`: Comfy generate, CPU CLIP/WD14/ImageReward, Caption V4 after `/free`. Tests: `python local_agent/test_gvd_qa_hybrid.py`.
- `assemble_mp4.py` stitched the receipt-gated Wan 5-frame take to `local_agent/runtime/gvd_qa/i2v_from_receipt.mp4` (480x256, 6 fps).
- Live SDXL 512x512 8-step (`RealVisXL_V5.0_fp16`, seed 17) then local QA: CLIP 33.49, ImageReward -0.71, Caption V4 admitted yellow carpet corridor, `accepted.json`. Peak 11014 MiB during VLM, 482 MiB after. Receipt unlocks I2V. Report: `local_agent/runtime/gvd_qa/smoke_generate_until_accepted.json`.
- `generate_until_accepted` now stores `qwen_checks` on the verdict (same as persisted stills).
