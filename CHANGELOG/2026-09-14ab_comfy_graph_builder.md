# 2026-09-14ab - Dynamic Comfy graph injection and auto FaceDetailer

Scope: implement Media Generation Pipeline tasks 2 and 3. No Equal Shares
production, no live ComfyUI, no custom-node enable on the image renderer.

## Why

`work/image_render.py` builds graphs per explicit mode. It does not expose a
general injector that severs and rewires API links, and FaceDetailer is opt-in
because that renderer starts ComfyUI with custom nodes disabled.

## Added

- `local_agent/comfy_graph_builder.py`
  - `base_txt2img_workflow` with string node ids and `[id, slot]` links
  - `ComfyGraphBuilder.inject_conditioning_node` copies the live KSampler
    `positive`/`negative` links onto the new node, then points KSampler at
    the new outputs. Other KSampler keys are untouched.
  - `prompt_requests_human_subject` plus `inject_face_detailer`: VAEDecode
    IMAGE → FaceDetailer → SaveImageWebsocket; model/clip/vae from the same
    CheckpointLoaderSimple (and VAEDecode vae link) as the base graph.
- Tests in `tests/test_media_pipeline.py`.
- TODO.md tasks 2 and 3 marked complete.

Unchanged: `work/image_render.py` default t2i path (custom nodes remain off).

## Validation

```
python -m unittest tests.test_media_pipeline -q
```

13 passed (CPU-only; no ComfyUI).
