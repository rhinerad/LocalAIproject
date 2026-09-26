# 2026-09-22d — F5-TTS and MuseTalk blockers fixed and measured

Used the existing Rockernow Comfy on :8188. Did not start a second backend.

## F5-TTS (`synthesize_dialogue`)

- Cause: torchaudio 2.10 routes load/save through torchcodec;
  `libtorchcodec_image.dll` fails with WinError 127 in this venv.
- Fix in `ComfyUI-F5-TTS/F5TTS.py`: `torchaudio.load` via PyAV,
  `torchaudio.save` via soundfile; skip `AudioEncoder`.
- Extra **1344 MiB**. Prompt `2b435af8-7112-46cd-9f95-959342dbcf98`.
- Promoted `f5_tts_adapter_required` (now has a pinned API graph).

## MuseTalk (`apply_lipsync`)

- Added `vae-ft-mse-840000-ema-pruned.safetensors` (~335 MB) to shared vae.
- Wired LoadAudio → VHS_AudioToVHSAudio → vhs_audio_to_audio_tensor →
  whisper_to_features → UNETLoader_MuseTalk + SD15 VAE + 4-frame identity.
- `MuseModelConfig` now sets `custom_operations`, `optimizations`,
  `memory_usage_factor` (Comfy 0.36 BaseModel requires them).
- First UNETLoader downloaded TMElyralab/MuseTalk (~3.4 GB unet).
- Extra **4866 MiB**. Prompt `91f1a81e-03d6-456a-be40-d04e317a7794`.
- Promoted `musetalk_unvalidated`. Digest
  `614e795f31cf791fd19d4a9300abf35137299c2c85a7c252ae77bef014601cfe`.

## Registry load fix

`implementation_from_dict` now accepts a single output object as well as a
list (1-tuple `outputs=` had serialized as a dict and blocked later promotes).

## Still unmeasured (hardware)

FastH3 V2 8-step, StoryDiffusion (>20 GB), LongCat TI2V fp8, Wan dual MoE.
LTX / FastH3 V1 remain tight vs 2048 MiB headroom.
