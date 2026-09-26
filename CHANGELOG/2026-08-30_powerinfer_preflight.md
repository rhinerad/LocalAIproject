# 2026-08-30 — PowerInfer predictor preflight

- Ran `run_pipeline.ps1 -ModelId relu-llama-7b -Stage show` in plan-only mode.
- Confirmed the native Windows target, VS 2022 + Ninja + CUDA 12.8+ (`sm_120`),
  `base` model route, ReLU gate, and staged dump/train/convert/package/validate/
  bench phases.
- Confirmed the TurboSparse projected checkpoint remains parked and is not part
  of the executable pipeline until operator-approved harmful/harmless pairs are
  available and predictors are regenerated from that exact tree.
- No model was loaded, no GPU process was started, no download occurred, and no
  protected artifact was changed.
- Ran local PowerInfer unit-test discovery; it exited successfully without
  reporting failures.

Status: preflight complete; execution remains intentionally gated.
