# 2026-09-14ae - Live media-pipeline runner

Scope: first live ComfyUI generation script for DSPy baseline traces.
Does not start or kill ComfyUI. `work/image_render.py` unchanged.

## Added

- `run_live_test.py`: two jobs (SDXL woman+FaceDetailer, video Backrooms
  temporal physics). Writes graphs under `logs/run_traces/`, POSTs `/prompt`,
  blocks on WebSocket `execution_success` (600s budget per job). Exits 2 if
  :8188 is down.
- `PipelineOrchestrator.track_prompt_id` now waits for `execution_success`
  (or `executing` with `node=null`), not the first per-node `executed`.

## Validation

```
python -m unittest tests.test_media_pipeline -q
```

23 passed (CPU). Live submit is operator-run after ComfyUI is up.
