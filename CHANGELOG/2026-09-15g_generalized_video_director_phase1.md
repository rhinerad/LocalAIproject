# 2026-09-15g - Generalized Video Director Phase 1 scaffold

Phase 1 only: signature, 15-row Beta Set, Qwen2.5-VL float-score contract.
No compile loop, no Comfy submit, no VRAM flip-flop.

- `local_agent/generalized_video_director.py`
  - `GeneralizedVideoDirectorSignature` outputs `positive_prompt`,
    `negative_prompt`, `cfg_scale`, `denoise`, `step_count` (floats).
  - `BETA_SET`: 15 VidProM/VBench-style intents, 5 each of
    `drone_high_kinematics`, `macro_nature`, `stylized_2d`.
  - `clamp_director_hparams` coerces GEPA strings into Wan-legal ranges.
  - Does not replace `TemporalPhysicsSignature` (Backrooms specialist).
- `local_agent/media_accuracy_gate.py`
  - `VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT` forces three unit-interval floats:
    text-video alignment, temporal consistency, aesthetic quality.
  - `parse_video_director_scores` fail-closed on exact Caption V4 llama.cpp.
  - Progressive curriculum: 0.60 (iter 0-2) → 0.70 → 0.80 → 0.85 (iter 9+).
  - Pass uses the *minimum* axis so one weak score cannot hide behind the mean.
- Tests: `test_generalized_video_director.py` plus gate parser/curriculum
  cases in `test_media_accuracy_gate.py`. CPU only; no GPU.

Await architect approval before Phase 2 (metric loop / memory flip-flop).
