# Changelog 2026-09-18g — Production integration + native voice foundations

## Verified prior evidence (not re-run)

- Continuity live mp4, post36 FastH3/Ref2VA outputs, remaining_suite_report, VRAM/attention reports, Comfy 0.36.0 present.
- 10:04 master reclassified: repeated identical normalized clips (same SHA256), assembly smoke only.

## Added

- `gvd_graph_builder.py` — production Autogrow emission for `ref_images.ref_image_N` / `ref_audios.ref_audio_N`, character↔tag mapping, over-limit fail-closed.
- `native_voice_continuity.py` — per-character bootstrap ordering, candidate vs canonical records, immutable promote, job isolation, block dependent shots, forbid C001_master_voice reuse and silent F5/Fish when native required.
- Offline: `verify_native_voice_offline.py` (PASS), `verify_production_integration_offline.py` (PASS).

## Patched

- `local_agent/minimax_ref2vid.py` — `apply_minimax_ref2vid_from_plan` via shared builder (legacy C001 defaults retained but marked).
- `final_master_audit.py` — `execute_normalize_concat`, duration probe, master scope classifier, `--execute` / `--dry-run-execute`.

## Still not PRODUCTION_INTEGRATED / ENDURANCE_QUALIFIED

- End-to-end agent→runner always using store + native voice gate.
- Live GPU proof of multi-character MiniMax audio conditioning.
- Unattended policy + endurance batch.
