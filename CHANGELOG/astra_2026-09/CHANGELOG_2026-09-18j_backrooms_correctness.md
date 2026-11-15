# CHANGELOG 2026-09-18j — Backrooms correctness blockers (local fix copy)

Scope: `/workspace/backrooms_fix/` only. No Equal Shares changes. No GPU/Comfy launched.

## Added
- `backrooms_compile.py` — EDITOR OVERRIDES → typed `JobSettings` (Flux, 4:3, 10s, native voice, no music), dialogue extraction from `<d>[English]…</d>`, conflict ledger, compile artifacts under `outputs_compile/`.
- `backrooms_still_contract.py` — require `references.start/last` asset ids; `video_requires_still_review` blocks animation until `stills_approved`.
- `verify_backrooms_compile_offline.py`
- `verify_backrooms_entrypoint_offline.py`
- `verify_native_voice_qa_offline.py`
- `EVIDENCE_MATRIX_2026-09-18j_backrooms.md`

## Changed
- `local_agent/backrooms_prompt_adapter.py` — Flux override detection; `model_profile=flux`; no BacHal SDXL LoRA when Flux; natural-language prompts; preserves `source_*` + `override_resolution`.
- `local_agent/backrooms_fully_merged_adapter.py` — same Flux/LoRA guard when settings/source demand Flux.
- `local_agent/managed_prompt_pack.py` — compile JobSettings before adapt; enrich `dialogue_lines` / `required_audio` / `duration_seconds` / `aspect_ratio` after parse; `compile_pack()` helper.
- `master_batch_runner.py` — fix broken voice-gate `mark_clip` kwargs via `mark_clip_blocked`; `clip_requires_audio`; per-clip duration (10s Backrooms); pass `--native-minimax-voice` / dialogue-json; completed count = SELECTED/verified only; `--require-store` / `--backrooms-production`; `accept_clip_after_gates` fail-closed stub.
- `generate_video.py` — register `--native-minimax-voice`, `--voice-ref-json`, `--image-ref-json`; call `enforce_native_voice_cli` at main start; refuse fish/f5 when native required.
- `native_voice_qa.py` — `speaker_margin_min`, `authorize_speaker_identity`, optional `contrast_wav` / `wrong_speaker_control`; spectral remains diagnostic only.

## Explicit non-claims
- Does **not** claim full 102-shot film production readiness.
- Does **not** silently rewrite story conflicts (ledger only).
- Live voice bootstrap, combined boundary/audio GPU quals, all-stills approval, and full soak remain open.

## Follow-on same day � Qual 3 voice bootstrap
- Added `live_voice_bootstrap_test.py`; report under `live_jobs/voice_bootstrap_20260918/`.
- C001 boot + C002 dependent PASS with muxed audio and immutable canonical hash.
