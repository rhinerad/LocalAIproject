# 2026-09-21k — live AnimateDiff + Fizz montage profile

Used the existing Rockernow Comfy on :8188 after the node-pack restart.
Did not start a second backend. Qwen :11436 stayed down.

## Montage (`execute_montage_morph`)

- Graph: RealVisXL + HotshotXL `hsxl_temporal_layers.safetensors` via
  `ADE_AnimateDiffLoaderGen1`, Fizz `BatchPromptSchedule` (frames 0 and 7),
  512², 8 frames, 4-step euler.
- First POST failed: `BatchPromptSchedule.animate()` requires `start_frame`
  and `end_frame` even though `/object_info` marks them optional.
- Retry prompt `cfd827f6-b23f-4673-9730-4bbe94af8239`
- Baseline 419 MiB; peak used 8613 MiB; extra **8194 MiB**. Fits 2048 MiB headroom.
- Promoted `animatediff_fizz_unvalidated`. Registry digest
  `63f76e616d6241740744192f3d5dea4de1187b9cab35799664c447bc87ac3ace`.

## Active registry now

| Tool | Implementation | peak extra MiB | 2048 headroom |
| --- | --- | ---: | --- |
| generate_still | known_good_sdxl_txt2img_v1 | 6978 | fits |
| execute_narrative_scene | ipadapter_sdxl_plus_face_unvalidated | 8640 | fits |
| execute_continuous_take | wan22_i2v_q4_high_unvalidated | 11198 | fits |
| execute_montage_morph | animatediff_fizz_unvalidated | 8194 | fits |
| execute_fast_action | fasth3_v1_t2va_unvalidated | 13872 | tight |
| execute_fast_action | ltx23_unvalidated | 14580 | tight |
