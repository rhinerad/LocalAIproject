# Implementation status — Astra pipeline audit

Last updated: 2026-09-18 (America/New_York)

## Offline scaffolding — DONE

P0 correctness, P1 store/profiles/VRAM lease/dataset/VHS, canonical assets + audio timeline, continuity fail/resume offline, RTX 5080 benchmark profile JSONs, final_master_audit planner — all green via verify_*_offline.py scripts.

## Live GPU / ComfyUI — DONE (2026-09-18)

| Item | Status | Evidence |
|------|--------|----------|
| Bounded base-H3 continuity (first_frame, fail/resume, SELECTED) | PASS | ~64.2 s/accepted-sec; `astra_live_continuity/continuity_*_00001_.mp4` |
| ffmpeg boundary extract + normalize/concat + ~10:04 master | PASS | `live_jobs/remaining_20260918_111727/` |
| Live reconcile + fault injection | PASS | `remaining_suite_report.json` |
| VRAM envelopes 1152x640 / 1344x768 | PASS | ~15.3 / ~15.1 GiB peaks |
| Attention Sage vs SDPA | PASS | Sage faster on 864x480/124 |
| ComfyUI upgrade to **0.36.0** | DONE | checkout `ee71d5c4`; prior in `ASTRA_PRE_UPGRADE_COMMIT.txt` |
| FastH3 Dense LoRA (6-step) | PASS | ~271 s, ~15462 MiB; `astra_post36/fasth3_00001_.mp4` |
| Ref2VA single + dual Autogrow identity lock | PASS | single ~301 s / 15258 MiB; dual ~290 s / 15418 MiB; `ref_single_*`, `ref_dual_*` |

## Ref2VA API note (critical)

Use dotted Autogrow keys on `MiniMaxH3ReferenceToVideo`:

- `ref_images.ref_image_0`, `ref_images.ref_image_1`, ...
- Prompt tags: `<Picture 1>`, `<Picture 2>`, ...
- Do **not** wire IMAGE/ImageBatch into `ref_images` (Tensor boolean ambiguity).
- Do **not** use bare `ref_image_0` without the `ref_images.` prefix (unexpected kwarg).

Script: `post36_ref2va_autogrow_test.py`  
Reports: `live_jobs/remaining_20260918_111727/post36_ref2va_autogrow_report.json`, `post36_fasth3_ref2va_summary.json`, earlier `post36_ref_fasth3_report.json`

## Optional follow-ups (not blocking this audit)

- Official FastVideo / separate FastH3 T2V checkpoint if released for Comfy
- Ref image_size=`max` fidelity vs speed trade study
- Pipeline production code path to emit dotted Autogrow keys automatically

## Production readiness (2026-09-18g)

Bounded experimental checklist remains closed (see 2026-09-18f).

**New foundations (OFFLINE_TESTED):** `gvd_graph_builder.py`, `native_voice_continuity.py`, final-master execute helpers.

**Not closed:** native per-character MiniMax voice live proof, full production caller wiring, unattended endurance, narrative (non-padded) long master.

See `EVIDENCE_MATRIX_2026-09-18g.md`.

## 2026-09-18h — caller wiring + live native voice smoke

- `batch_render_folder` emits `ref_audios.ref_audio_N`; `generate_video` has `--native-minimax-voice` fail-closed against Fish/F5.
- `unattended_policy.py` + `voice_extract.py` offline PASS.
- Live dual-audio Autogrow PASS (~226 s) → `astra_native_voice/dual_char_00001_.mp4`.
- Still open: calibrated voice-similarity QA, endurance, narrative (non-padded) long master, operator acceptance workflows.

## 2026-09-18i closeout (voice QA / endurance / distinct master)

- Offline voice QA: PASS
- Live calibrate on ALICE/BOB WAVs: PASS (transcript fail-closed strong; spectral speaker margin weak)
- dual_char take extract: deferred (no audio stream)
- Endurance: PASS as BOUNDED_ENDURANCE_CONTROL_PLANE
- Distinct masters: short ~22.3 s and long ~601.9 s from 5 unique SELECTED clips
- See CHANGELOG_2026-09-18i_voice_qa_endurance_distinct_master.md and EVIDENCE_MATRIX_2026-09-18i.md


## 2026-09-18j — Backrooms correctness (audit priority)

Exact-pack compile on audit attachment (`pasted-text.txt` / Codex cf01dcbc…):
- 102 clips, Flux still backend (Rule 0), zero SDXL LoRA bindings
- dialogue_fields_count=59 / 63 lines; duration_total_s=1020 (17:00); aspect 4:3
- conflict ledger 6 entries (ending/static/improv/camera/C102/bible) — unresolved, not rewritten
- Offline verifies PASS: compile, entrypoint (native flags + mark_clip_blocked + dry argv), voice QA contrast fail-closed
- Runner: per-clip 10s, required_audio from compiled dialogue, SELECTED-only completion counting, `--backrooms-production` / `--require-store`
- generate_video: `--native-minimax-voice` / voice-ref / image-ref registered + enforce at main
- Still open (GPU quals 3–8): voice bootstrap lock, combined boundary+audio, representative beats, all-stills approval, 102 soak, final 17:00 delivery gate
- See CHANGELOG_2026-09-18j_backrooms_correctness.md and EVIDENCE_MATRIX_2026-09-18j_backrooms.md


## 2026-09-18j+ Qual 3 voice bootstrap PASS
- Extracted ACTOR voice from first MiniMax take; dependent C002 bound same hash; AAC present on both mp4s.
- See live_jobs/voice_bootstrap_20260918/live_voice_bootstrap_report.json

## Qual 4 combined boundary+audio PASS
- I2V first/last + AddGuide(locked voice) + mux; see live_jobs/combined_boundary_audio_20260918/

## Flux stills progress
- Canvas: 1152x864 true 4:3 flux1-dev-fp8 QUALIFIED
- Approved stills: C001-C014 apartment opening (15 registry entries)
- Remaining: C015-C102 (+ ENTITY voice bootstrap in flight)
