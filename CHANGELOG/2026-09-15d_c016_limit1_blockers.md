# 2026-09-15d - C016 limit-1: tile LoRA, CLIP crash fix, DSPy momentum

- Downloaded `wan2.1_tile_control.safetensors` (378400000 bytes) into
  Shared controlnet + loras. HF file is a 1.3B tile *control LoRA*;
  Phase 4 uses `LoraLoaderModelOnly` at denoise 0.35 / 720p.
- DSPy: `enforce_physics_terms` appends missing `handheld walking momentum`
  on unlocked cameras. Confirmed on C016 inject.
- Phase 3 CLIP: switched off `umt5-xxl-encoder-Q6_K.gguf` dequant to
  `CLIPLoader` `umt5_xxl_fp8_e4m3fn_scaled.safetensors` on CPU, plus
  Rockernow restart after SDXL. Wan FLF completed (VRAM peak 11098 MiB).
- Phase 4: VHS_LoadVideoPath required a silent audio mux on the FLF mp4;
  720p + fp8 CLIP then killed Comfy again. No photoreal mp4. Keep `--limit 1`.
