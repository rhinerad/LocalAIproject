# 2026-09-21f — live FastH3 T2VA profile and FastH3 V2 download

Used the existing Rockernow Comfy on :8188. Did not start a second backend.
Qwen :11436 stayed down.

## FastH3 Preview V1 (`execute_fast_action`)

- Graph: pruned FL2VA int8 + CPU Qwen3-VL nvfp4 CLIP + int8 video VAE +
  `FastH3-Dense-4-step-v1-LoRA-ComfyUI-pruned.safetensors` (`low_vram` merge),
  `MiniMaxH3TurboSampler`, 608×352, 5 frames, 4 steps, `simple` scheduler.
- CLIP encode paged hard on the 32 GB host (~4 GB free during encode).
- Baseline 1288 MiB; peak used 15160 MiB; extra **13872 MiB**.
- Prompt `628f4963-1b78-4c66-b884-eb05aa93113b`
- Outputs: `gvd_tool_router/h3_fasth3_smoke_00001_.png` … `_00005_.png`
- Promoted `fasth3_v1_t2va_unvalidated`. Registry digest
  `e03b317375023834dab88f164d19e6574437fc0de41ac5fb25af78a637197ed0`.
- 13872 + 2048 headroom is tight on this 16 GB card after `/free` (~14690 MiB
  free at the same idle). Production admission may still `RESOURCE_BLOCK`.

## Downloads (no Comfy restart)

- Official FastH3 8-step V2:
  `ComfyUI-Shared/models/diffusion_models/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors`
  (22.128 GB). **Unmeasured.** `fasth3_v2_unvalidated` stays disabled.
- Cloned `ComfyUI-AnimateDiff-Evolved` and `ComfyUI_FizzNodes` into Rockernow
  `custom_nodes`.
- Motion modules: HotshotXL `hsxl_temporal_layers.safetensors`, AnimateDiff-SDXL
  `mm_sdxl_v10_beta.ckpt`. Hardlinked into shared `animatediff_models`.
- Those node packs are not in this Comfy process's `/object_info` until restart.
  Montage/morph remains unmeasured.

## Active registry now

| Tool | Implementation | peak extra MiB | 2048 headroom |
| --- | --- | ---: | --- |
| generate_still | known_good_sdxl_txt2img_v1 | 6978 | fits |
| execute_narrative_scene | ipadapter_sdxl_plus_face_unvalidated | 8640 | fits |
| execute_continuous_take | wan22_i2v_q4_high_unvalidated | 11198 | fits |
| execute_fast_action | fasth3_v1_t2va_unvalidated | 13872 | tight / may RESOURCE_BLOCK |
| execute_fast_action | ltx23_unvalidated | 14580 | tight / may RESOURCE_BLOCK |
