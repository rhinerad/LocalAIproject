# 2026-09-22c — ProPainter live profile; remaining GVD families

Used the existing Rockernow Comfy on :8188 after a restart (previous grok-owned
process had hit the 10h cap). Did not start a second backend. Qwen :11436 down.

## Repair (`repair_video`)

- Graph: `gvd_identity_ref.png` repeated to 2 frames, solid 512 mask,
  `ProPainterInpaint` fp16, raft_iter 5, neighbor_length 2.
- First POST failed: mask 256 vs image 512.
- Retry prompt `684d0c45-ee7b-449d-8475-02df245d8c37`
- Extra **290 MiB** (tiny 2-frame smoke). Fits 2048 MiB headroom.
- Promoted `propainter_unvalidated`. Digest after this promote:
  `cdc220bb1deaf057bd4f70dba1733c8b263af00ab4cc5c2f89b74de094bc492c`.

## F5-TTS (`synthesize_dialogue`)

- Nodes load. `F5TTSAudio` / `F5TTSAudioInputs` both fail with
  `Could not load ... torchcodec\libtorchcodec_image.dll` even though the DLL
  is on disk. Stays unpromoted. Needs a working torchaudio backend in the
  Rockernow venv.

## Not smoked on this pass

- MuseTalk: live, but whisper path needs `VHS_AUDIO` and SD 1.5
  `sd-vae-ft-mse` is not in VAELoader.
- FastH3 V2 8-step checkpoint is on disk; 32B CPU CLIP + 22 GB transformer
  was not re-run.
- StoryDiffusion nodes load; spec already flags >20 GB. IPAdapter remains
  the measured narrative path.
- LongCat TI2V fp8 on disk, unmeasured.
- Wan dual MoE unmeasured.

## Active measured tools

| Tool | Implementation | extra MiB |
| --- | --- | ---: |
| generate_still | known_good_sdxl_txt2img_v1 | 6978 |
| upscale_still | tiled_diffusion_unvalidated | 7136 |
| execute_montage_morph | animatediff_fizz_unvalidated | 8194 |
| execute_narrative_scene | ipadapter_sdxl_plus_face_unvalidated | 8640 |
| execute_continuous_take | wan22_i2v_q4_high_unvalidated | 11198 |
| execute_fast_action | fasth3_v1_t2va_unvalidated | 13872 |
| execute_fast_action | ltx23_unvalidated | 14580 |
| repair_video | propainter_unvalidated | 290 |
