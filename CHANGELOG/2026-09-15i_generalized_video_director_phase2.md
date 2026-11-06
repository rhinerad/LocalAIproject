# 2026-09-15i - Generalized Video Director Phase 2 mock MIPROv2

Phase 2: metric + orchestrator with mocked inference. No ComfyUI, no VLM
load, no VRAM flip-flop.

- `local_agent/generalized_video_director.py`
  - Beta Set is 16 rows: previous 15 generalized + `GVD-B01` Backrooms
    retention (handheld Level 0 walk). CFG bands remain soft instructions.
  - `clamp_director_hparams` still the only hard range.
  - `generalized_video_metric(example, pred) -> float` for MIPROv2.
    JSON feedback is `generalized_video_metric.last_feedback` / `LAST_METRIC_RESULT`.
  - Mock VLM JSON is parsed by the production
    `parse_video_director_scores` path (exact Caption V4 identity).
  - Curriculum bar is min(alignment, temporal, aesthetic) vs threshold.
  - `compile_director(mock=True)` runs `dspy.MIPROv2` on `MockDirectorLM`.
    Live compile (`mock=False`) is refused until Phase 3.
- Tests in `test_generalized_video_director.py`: dataset shape, metric
  clamp+JSON, Backrooms physics reward, and a 3-example MIPROv2 mock compile.

Run: `python local_agent/generalized_video_director.py --compile --mock`

Evidence (this session, CPU only):
- `unittest test_generalized_video_director` + `test_media_accuracy_gate` passed.
- Full 16-row mock MIPROv2: average min-axis 11.65/16 (72.8%), saved
  `models/dspy_compiled/generalized_video_director_mipro_mock.json`.
  Did not overwrite `temporal_physics_v1.json`.
- Last mock feedback for GVD-B01: hparams cfg=5.5 / denoise=0.85 /
  steps=28.0 (floats), scores 1.00 / 0.96 / 0.85, min=0.85 ≥ 0.60.
