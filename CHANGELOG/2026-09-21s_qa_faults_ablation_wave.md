# 2026-09-21s Faults, ablation, wave, generated-still I2V

- Resume scores orphan `candidate.png` after a crash (no regenerate). `generate_wave_then_score` generates a wave under one diffusion residency then scores.
- LocalQaClient logs DINO when a reference is supplied; overlong CLIP captions raise QAError.
- PromptTester-compatible ablation (`prompt_ablation.py`) pins `max_attempts: 1` and writes `qa_experiments` without promoting edits. Smoke: 7 variants from the C017-end prompt.
- Fault tests: headroom RESOURCE_BLOCKED, CUDA ORT forbidden, unknown class, overlong caption, queued journal, orphan resume, best-of-K, wave, DINO field. `python local_agent/test_gvd_qa_faults.py`.
- Live Wan I2V from the **generated** SDXL receipt: peak 11616 MiB, 5 frames `i2v_gen_accepted_00001–00005_.png`, mux `local_agent/runtime/gvd_qa/i2v_gen_accepted.mp4`. Report: `smoke_i2v_from_generated_receipt.json`.
