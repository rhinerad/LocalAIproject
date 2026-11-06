# Local Agent Current Handoff — 2026-09-15

Repository:
`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

Read first:

1. `CLAUDE.md`
2. `AGENTS.md`
3. `HANDOFF_STATUS.md` — generated live snapshot from `scripts/write_handoff_status.py`
4. `TODO.md`
5. Recent `CHANGELOG/2026-09-14aa...` through `CHANGELOG/2026-09-15d...`

This handoff records the local-agent/media-pipeline work performed after the
2026-09-08 handoff. It is a status handoff, not approval to start renders.

## Current live product boundary

- `local_agent/server.py` still reports
  `APP_REVISION = "2026-09-07-prompt-pack-full-production-r98"`.
- The local agent is a general-purpose desktop assistant. Do not let old Equal
  Shares/H3 context leak into unrelated tasks.
- `HANDOFF_STATUS.md` is the generated current snapshot. Dated handoff docs are
  supporting context.
- One ComfyUI backend only. Do not start a backend or render unless the current
  operator request explicitly calls for it and all normal guards pass.

## Overnight media-pipeline state

The Media Generation Pipeline TODO section is now marked complete through the
offline and guarded-live orchestration layers:

- `local_agent/media_buckets.py`
  - reusable SDXL/FLUX bucket resolver
  - standard aspects and custom numeric ratios
  - default 1024x1024 pixel budget, snapped to multiples of 64
- `local_agent/prompt_router.py`
  - SDXL comma/tag dialect plus default negative failures
  - FLUX natural-language cleanup and tag-soup removal
  - video dialect routed through temporal-physics expansion
- `local_agent/comfy_graph_builder.py`
  - reusable ComfyUI graph builder
  - dynamic conditioning-node injection
  - automatic FaceDetailer path for human-subject prompts
- `local_agent/temporal_physics.py`
  - deterministic Backrooms/video temporal cues
  - compiled DSPy artifact loading with silent fallback
  - local Ollama configuration and unload helpers
- `local_agent/dispatcher.py`
  - `PipelineOrchestrator` combines bucket math, prompt routing, temporal
    physics, graph mutation, FaceDetailer injection, submit, and prompt tracking
- `models/dspy_compiled/temporal_physics_v1.json`
  - synthesized DSPy few-shot artifact; no cloud key required at runtime
- `run_live_test.py`
  - guarded live SDXL + Wan first-last-frame hardware QA script
- `batch_generate_backrooms.py`
  - 24-clip opt-in batch runner
  - default dry-plan; `--execute` submits
  - intended phase sequence: DSPy -> stills -> `/free` -> Wan FLF -> `/free`
    -> Wan tile upscale -> `/free`

## Most recent live blocker

See `CHANGELOG/2026-09-15d_c016_limit1_blockers.md`.

For C016 with `--limit 1`:

- `wan2.1_tile_control.safetensors` was downloaded into shared ControlNet/LoRA
  model locations.
- The HF file is a tile control LoRA; Phase 4 uses `LoraLoaderModelOnly`.
- DSPy `enforce_physics_terms` now appends missing `handheld walking momentum`
  for unlocked cameras.
- Wan FLF Phase 3 completed after switching away from the Q6 GGUF CLIP dequant
  path to CPU `CLIPLoader` with `umt5_xxl_fp8_e4m3fn_scaled.safetensors`.
- Reported live VRAM peak for Wan FLF: 11098 MiB.
- Phase 4 needed silent-audio muxing because `VHS_LoadVideoPath` requires audio.
- Phase 4 then killed Comfy again at 720p + fp8 CLIP. No photoreal Phase 4 mp4
  was produced.
- Keep future live work at `--limit 1` until Phase 4 is stabilized.

Do not claim Phase 4 is proven live. It is implemented and planned, but the
latest live attempt failed closed and preserved the Phase 3 mp4.

## Current tests and evidence

Recent validation recorded in changelogs:

- `tests/test_media_pipeline.py`
  - grew from 7 to 33 CPU tests across media buckets, prompt routing, dynamic
    graph injection, FaceDetailer, temporal physics, DSPy artifact loading,
    orchestrator payloads, and Ollama dispatch helpers.
- `test_dynamic_dspy_dispatch.py`
  - live Ollama run succeeded via fallback installed model:
    `source=compiled model=ollama_chat/llama3.1:8b seconds=45.19`.
- `HANDOFF_STATUS.md`
  - regenerated 2026-09-15 01:52 Eastern with the 2026-09-15 changelogs at top.

## Next safest work

1. Do not start broad batch generation. Work C016 only with `--limit 1`.
2. Stabilize Phase 4 Wan tile upscale:
   - preserve the Phase 3 mp4
   - keep silent-audio muxing
   - reduce Phase 4 load or split it into smaller/tiled chunks
   - confirm Comfy process survival and output file existence before continuing
3. If Phase 4 remains unstable, mark Phase 4 optional/fallback and let Phase 3
   remain the deliverable for that clip.
4. Keep `HANDOFF_STATUS.md` regenerated after material changes.
5. Add a same-session `CHANGELOG/` entry for every code or documentation change.

## Do not do

- Do not start videos for the older prompt-pack stills pipeline without the
  explicit still approval gates.
- Do not touch `outputs/equal_shares/**`.
- Do not touch PowerInfer weights, predictors, registries, or router settings
  as part of this media-pipeline handoff.
- Do not kill unknown ComfyUI or Python processes; identify ownership first.
- Do not treat a dry plan, unit test, or generated graph as a successful render.
