# 2026-09-15c - Phase 4 Wan Tile photoreal upscale

Scope: after Wan FLF, a 720p low-denoise ControlNet pass. Phase 4
failures preserve the Phase 3 mp4. `wan2.1_tile_control.safetensors` is
the expected ControlNet filename (not present in Shared yet).

## Added

- `live_vram_test.build_tile_upscale_graph`: VHS_LoadVideoPath → ImageScale
  1280x720 → ControlNetLoader `wan2.1_tile_control.safetensors` →
  ControlNetApplyAdvanced → KSampler denoise 0.35 → VHS_VideoCombine
  `photoreal_video_<id>`.
- `batch_generate_backrooms.py` Phase 4 after FLF `/free`, then `/free`
  again. Dry plan prints the full sequence.
