# Changelog 2026-09-18h — Caller wiring, unattended policy, live native voice smoke

## Added
- `unattended_policy.py` — job-scoped policy; separate `machine_accepted` vs `operator_accepted`
- `voice_extract.py` — clean speaker WAV extraction with rejection reasons (overlap/noise/music/transcript)
- `live_native_voice_bounded_test.py` — bounded Ref2VA dual-audio Autogrow live smoke
- `verify_unattended_voice_extract_offline.py`

## Patched
- `work/batch_render_folder.py` — `audio_filenames` / `character_ids_for_audio` → `ref_audios.ref_audio_N`
- `generate_video.py` — `--native-minimax-voice`, `--voice-ref-json`, `--image-ref-json`; forbids silent F5/Fish when native required

## Offline
- verify_unattended_voice_extract_offline PASS
- prior native voice + integration verifiers still PASS

## Live
- See `live_jobs/remaining_20260918_111727/live_native_voice_report.json` when complete

## Live result (2026-09-18)

- PASS dual-character Ref2VA with `ref_images.ref_image_0` + `ref_audios.ref_audio_0/1`
- Characters ALICE/BOB via `astra_voice_ALICE.wav` / `astra_voice_BOB.wav` (not shared C001 filename)
- ~225.8 s wall, peak ~15318 MiB, Comfy 0.36.0
- Output: `ComfyUI-Shared/output/astra_native_voice/dual_char_00001_.mp4`
- Report: `live_jobs/remaining_20260918_111727/live_native_voice_report.json`
