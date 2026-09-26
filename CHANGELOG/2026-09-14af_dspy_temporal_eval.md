# 2026-09-14af - DSPy temporal-physics evaluation suite

Scope: grade orchestrator video-prompt injections. No live ComfyUI, no
image_render changes.

## Added

- `evaluate_dspy_pipeline.py` with `ValidateTemporalPhysics` (base_prompt,
  injected_prompt → rationale, score). Judge LM is SpaceXAI `grok-4.6`
  (`XAI_API_KEY`, `https://api.x.ai/v1`), not GPT-4o/Claude.
- Loads `logs/run_traces/*.json` plus gold open-hallway / static-camera
  pairs. Metric fail-closes if handheld physics leaks onto a locked camera,
  or if an open Backrooms prompt is missing required aesthetics.
- Helper tests in `tests/test_media_pipeline.py` (no dspy install required).

## Validation

```
python -m py_compile evaluate_dspy_pipeline.py
python -m unittest tests.test_media_pipeline -q
```

26 passed. Live judge run needs `pip install dspy` and `XAI_API_KEY`.
