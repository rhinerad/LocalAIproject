# 2026-09-20c — GVD tool router M0–M2

Implemented `docs/gvd_tool_router_spec.md` milestones M0–M2 in
`local_agent/gvd_tool_router/`. M3–M6 (validated family profiles, live
discovery adapters, automatic promotion, dialogue/repair) are present only as
disabled catalog rows and injected-adapter orchestration. They are not complete.

## Delivered

- M0: `GVD_ROOT` layout, `config/runtime.json`, environment lock, node-schema
  snapshot. Inventory never starts ComfyUI or downloads models.
- M1: typed registry dataclasses, API binder (SHA-256 + `/object_info` bindings,
  UI graphs refused), SQLite attempts/prompt_ids, mocked known-good still
  execute/reconcile.
- M2: four public tools always registered; deterministic router; stage DAG;
  OS-held GPU lease via `production_integrity.process_lock`; bounded fallbacks.
- Agent whitelist: `gvd_inventory`, `gvd_route_shot`, `execute_narrative_scene`,
  `execute_continuous_take`, `execute_montage_morph`, `execute_fast_action`,
  `discover_workflows`. Execute tools plan by default (`live=false`).
- Tests: `python local_agent/test_gvd_tool_router.py` — 17 passed.

## Spec vs existing tree (mismatches kept)

- `local_agent/vram_controller.py` still uses informational JSON ownership;
  the new lease is a separate OS lock. Fail-open `wait_for_ollama_unload` was
  not rewritten in this change.
- `generalized_video_director.py` / DSPy MIPRO remains a prompt/hparam director.
  This control plane selects workflow *implementations*; it does not replace
  DSPy compilation.
- `tools.py` `start_batch_render` still launches `work/batch_render_folder.py`.
  GVD execute tools do not call that path.
- ComfyUI version remains user-reported in the spec. Inventory recorded backend
  commit `ee71d5c4993f29086b27fde1629a945ae48425bf` from the Rockernow tree
  when git was available.
- FastH3 V1/V2, StoryDiffusion, LongCat, LTX rows are catalogued **disabled**.
  No custom nodes or checkpoints were installed.

## Evidence

- Unit tests: 17/17 OK (no GPU submit).
- Seeded catalog: `local_agent/runtime/gvd_tool_router/registry/catalog.json`
- Inventory: `local_agent/runtime/gvd_tool_router/inventory/environment_lock.json`
- Spec copy: `docs/gvd_tool_router_spec.md`
