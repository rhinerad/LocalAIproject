# 2026-09-14ai - Runtime compiled temporal-physics injection

Scope: load `models/dspy_compiled/temporal_physics_v1.json` at dispatch time
with silent fallback. No live ComfyUI. No image_render changes.

## Changed

- `local_agent/temporal_physics.py`: `load_compiled_temporal_physics` and
  `runtime_inject_temporal_physics`. Compiled DSPy inference only if the
  artifact parses and a local `dspy.settings.lm` is set; otherwise
  `inject_temporal_physics`. Exceptions never escape into dispatch.
- `PipelineOrchestrator` and video `prompt_router` call the runtime injector.
- Tests: deserialize artifact, missing-path fallback, CLIPTextEncode cues
  on video payloads (open hallway and tripod).
- TODO.md: DSPy compile + runtime integration marked complete.

## Validation

```
python -m unittest tests.test_media_pipeline -q
```

32 passed.
