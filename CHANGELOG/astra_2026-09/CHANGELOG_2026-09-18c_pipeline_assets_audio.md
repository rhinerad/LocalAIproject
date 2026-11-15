# CHANGELOG 2026-09-18c — pipeline assets + audio timeline (audit §5 + §10)

Offline-only patches under `/workspace/pipeline_p0/` (copies). No ComfyUI/GPU touched.

## Summary

| ID | Status | What changed |
|----|--------|--------------|
| §5-A | done | `handoff/canonical_assets.py`: versioned AssetRegistry (identity/wardrobe/location/reference/boundary_frame/voice) with content hashes. |
| §5-B | done | Continuity path helper: SELECTED parent → frame index → lossless PNG → Comfy upload name → LoadImage → `MiniMaxH3ImageToVideo.first_frame` (same bind contract as orchestrator / pipeline_reference). |
| §5-C | done | Continuity rules as APIs: extract boundary from clean render before VHS/subtitles; record frame index+hash; reject broken/non-SELECTED parents; re-anchor from canonical assets at planned cuts. |
| §5-D | done | Edit-relationship strategy table: continuous / new_angle / new_scene / character_return / bridge. |
| §10-A | done | Versioned `VoiceAsset` / `VoiceAssetRecord` (job_id, speaker_id, voice_version, ref hashes, tts_backend, checkpoint_hash, language, delivery_params) — replaces shared C001-style voice assumption. |
| §10-B | done | Dialogue lines stored separately with speaker_id + exact text (`dynamic_voice.DialogueLine.to_dict`, `production_store.store_shot_dialogue`). |
| §10-C | done | Per-shot audio modes: narration_over_picture \| visible_dialogue \| native_h3_audio \| silent_abstract; silence only when intentional; dialogue+silent fails closed. |
| §10-D | done | `handoff/audio_timeline.py`: stems (narration/dialogue/ambience/music/fx); integer frame/sample fields; 24fps ↔ 48kHz = 2000 samples/frame. |
| §10-E | done | `build_local_f5_infer_args` CLI-shaped helper (`--ref_audio/--ref_text/--gen_text`); no network; fail closed on provider mismatch. |
| Harness | done | `verify_p1_assets_audio_offline.py` + `handoff/continuity_dry_run.py` (§13 fake job layout, no Comfy). |
| Wire | done | Minimal hooks in `production_store` (boundary/dialogue meta) and `master_batch_runner` (imports + `resolve_clip_audio_mode` / `continuity_parent_still_valid`). |

## Files touched

- `handoff/canonical_assets.py` — **new**
- `handoff/audio_timeline.py` — **new**
- `handoff/continuity_dry_run.py` — **new**
- `handoff/local_agent/dynamic_voice.py` — VoiceAsset, ShotAudioMode, local_f5 CLI helper; DialogueLine.speaker_id; Linux stub input dir (no Windows path)
- `handoff/production_store.py` — boundary + dialogue meta helpers
- `handoff/master_batch_runner.py` — import + thin continuity/audio helpers
- `verify_p1_assets_audio_offline.py` — **new** offline proof suite
- `FILES_CHANGED_ASSETS_AUDIO.txt` — CopyFromBox relative list
- this changelog

## Verify

```bash
python3 /workspace/pipeline_p0/verify_p1_assets_audio_offline.py
# ALL ASSETS/AUDIO OFFLINE CHECKS PASSED

python3 /workspace/pipeline_p0/verify_p0_offline.py
# ALL P0 OFFLINE CHECKS PASSED

python3 /workspace/pipeline_p0/verify_p1_offline.py
# ALL P1 OFFLINE CHECKS PASSED

python3 /workspace/pipeline_p0/handoff/continuity_dry_run.py --job-root /tmp/fake_job_s13
```

## Intentional stubs / non-goals

- No live Comfy upload, ffmpeg boundary extract, or TTS process spawn.
- `continuity_dry_run` uses a 1×1 PNG + stub wav/mp4 under a fake job tree.
- `local_f5` helper only builds argv; operators run `f5-tts_infer-cli` separately.
- Master runner wiring is import/API surface only — does not change live submit path behavior beyond helpers being available.

## Ops notes

- Boundary PNGs must be taken from **clean** renders (before VHS / subtitles).
- Child continuous binds invalidate when the parent's SELECTED attempt changes.
- Prefer versioned voice assets per job/speaker; do not assume a shared C001 master wav for every clip.
- Default editorial timing: 24 fps, 48 kHz, 2000 samples/frame.
