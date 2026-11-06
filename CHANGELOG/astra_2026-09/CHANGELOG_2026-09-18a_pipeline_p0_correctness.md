# CHANGELOG 2026-09-18a — pipeline P0 correctness

Offline-only patches under `/workspace/pipeline_p0/` (copies). No ComfyUI/GPU touched.

## Summary

| ID | Status | What changed |
|----|--------|--------------|
| P0-1 | done | Real `--start-frame-path` / `--end-frame-path` → `LoadImage` → `MiniMaxH3ImageToVideo.first_frame` / `.last_frame` |
| P0-2 | done | Separate `editorial_frames` vs `generation_frames`; `h3_generation_frames` (congr. 5 mod 17, 124–362) |
| P0-3 | done | Typed dialogue array `{speaker,text}` through master/batch → generate_video → voice path |
| P0-4 | done | Explicit providers `local_f5` / `fish_audio` / `minimax_native` / `none`; refuse Fish-as-F5 |
| P0-5 | done | Required dialogue + voice/class_type failure → `VoiceAudioGateError` (no silent success) |
| P0-6 | done | `RENDERED` → `QA_PENDING` → `SELECTED`; resume rejects nonempty file / legacy `done` alone |

## Files touched

- `handoff/gvd_core.py` — pure `h3_generation_frames` / `editorial_vs_generation_frames` (offline-importable)
- `handoff/local_agent/dynamic_voice.py` — providers, typed dialogue, audio gate
- `handoff/local_agent/dspy_orchestrator.py` — frame resolve/bind, dialogue, fail-closed submit
- `handoff/generate_video.py` — CLI args + `submit_comfy` passthrough
- `handoff/master_batch_runner.py` — real frame/dialogue args; resume = SELECTED only
- `handoff/batch_run_backrooms_gvd.py` — lifecycle states; dialogue array; already_done gate
- `verify_p0_offline.py` — offline proof suite (all checks passed)
- `FILES_CHANGED.txt` — CopyFromBox relative list
- this changelog

## Verify

```bash
python3 /workspace/pipeline_p0/verify_p0_offline.py
# ALL P0 OFFLINE CHECKS PASSED
```

## Ops notes

- Default voice provider is `local_f5` (`F5TTSAudio`). Set `GVD_VOICE_PROVIDER=fish_audio` to use Fish explicitly.
- `GVD_F5_TTS_CLASS=FishAudio*` without explicit provider now fails closed.
- Master runner marks render success as `rendered` / `QA_PENDING` (not SELECTED). Operator/VLM must verify before resume-skip.
- Thermal/VRAM/telemetry guards in orchestrator submit path preserved.
