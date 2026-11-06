# 2026-09-06s — Owned-backend Flux/RealPro model visibility

Date: 2026-09-06 (evening ET). Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06s**.

## Operator goal

`render_story_image` / `render_story_image_batch` with `model_profile=realpro_flux`
must get past `model not visible to owned backend: realProV3_realProV3Unet.safetensors`
so Flux stills can land as PNGs. Do not invent a flux tool; do not start video.

## Root cause

1. Operator UNet lives at
   `A:\Users\rhine\Downloads\minimax and realprovisualXL\realProV3_realProV3Unet.safetensors`
   (not Downloads root).
2. `work/runtime/image_render_model_paths.yaml` pointed `realpro.download` at
   Downloads root with `diffusion_models: ''`.
3. ComfyUI `utils/extra_config.load_extra_path_config` **skips empty path
   segments**, so that entry registered **no** search dir at all. UNETLoader
   never saw RealPro. Same empty-string pitfall for AliceMix checkpoints.

## Changes

### A. Model paths YAML

- `realpro.download.base_path` -> operator folder `...\minimax and realprovisualXL`
- `diffusion_models: '.'` (register base_path itself; never `''`)
- Same fix for `alicemix.download` / `checkpoints: '.'`

### B. Fail-fast path resolver in `work/image_render.py`

- `iter_extra_model_folder_paths` / `model_file_on_configured_paths` /
  `assert_configured_model_visible` mirror Comfy's empty-segment skip + legacy
  `unet`/`clip` mapping.
- Execute path asserts the profile model is on configured dirs **before**
  booting owned Comfy, then still checks live `object_info` visibility.

### C. Revision

- `APP_REVISION=2026-09-06-flux-model-visible-r95` in `local_agent/server.py`
- `$ExpectedAgentRevision` synced in `local_agent/START_LOCAL_AGENT_GUI.ps1`

## Tests

- `test_extra_model_paths_empty_segment_is_a_noop`
- `test_extra_model_paths_dot_registers_base_path`
- `test_live_realpro_yaml_sees_operator_unet`
- `python -m unittest test_image_render -v` (11 OK)

## Live

Owned-backend visibility smoke after this entry. Agent restart only if needed
to pick up revision for `/api/status` (image_render paths are process-local to
the render child, not the agent import for YAML).
