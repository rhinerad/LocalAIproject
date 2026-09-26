# 2026-09-14ag - DSPy temporal-physics BootstrapFewShot compiler

Scope: cloud compile of few-shot demos into a local JSON artifact. No live
ComfyUI. No image_render changes.

## Added

- `evaluate_temporal_physics` compiler metric (physics + conflict rules;
  no judge `score` required). Extra gold rows: tripod, dolly.
- `optimize_dspy_pipeline.py`: `TemporalPhysicsInjector`,
  `compile_pipeline()` via `dspy.teleprompt.BootstrapFewShot`, save to
  `models/dspy_compiled/temporal_physics_v1.json`, verify
  "A static tripod shot of a yellow hallway".
- Judge LM remains SpaceXAI grok-4.6 (`XAI_API_KEY`, `https://api.x.ai/v1`).

## Validation

```
python -m py_compile evaluate_dspy_pipeline.py optimize_dspy_pipeline.py
python -m unittest tests.test_media_pipeline -q
```

28 passed. Cloud `compile_pipeline()` was not run (needs `dspy` + `XAI_API_KEY`).
