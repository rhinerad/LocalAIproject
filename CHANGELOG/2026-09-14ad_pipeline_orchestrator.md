# 2026-09-14ad - Media pipeline orchestrator

Scope: unify Media Generation Pipeline modules into one dispatch path.
No Equal Shares production. `work/image_render.py` startup is unchanged.

## Added

- `local_agent/dispatcher.py` `PipelineOrchestrator`:
  1. `resolve_latent_bucket`
  2. `inject_temporal_physics` when style is backrooms
  3. `format_prompt_for_target`
  4. base txt2img API JSON + `ComfyGraphBuilder.apply_size_and_prompts`
  5. FaceDetailer when `prompt_requests_human_subject`
- `submit_prompt` POSTs to ComfyUI `/prompt` with a dedicated `client_id`.
- `track_prompt_id` follows that id on `/ws?clientId=...` (executed /
  execution_success / execution_error), falling back to HTTP `/history`.
- `ComfyGraphBuilder.apply_size_and_prompts` writes snapped width/height
  and dialect prompts onto the base nodes before FaceDetailer.
- Integration tests in `tests/test_media_pipeline.py`.
- TODO.md Media Generation Pipeline marked complete.

## Validation

```
python -m py_compile local_agent/dispatcher.py local_agent/comfy_graph_builder.py
  tests/test_media_pipeline.py
python -m unittest tests.test_media_pipeline -q
```

22 passed. `work/image_render.py` not modified.
