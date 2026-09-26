# Evidence matrix â€” 2026-09-18j Backrooms correctness

| Qual / item | Status | Notes |
|---|---|---|
| 1. Exact-pack compile (102, 17:00, Flux, 4:3, dialogue, ledger) | **COMPILE_PASS** (offline) | `verify_backrooms_compile_offline.py`; artifacts in `outputs_compile/` |
| 2. Entrypoint integration (argv/AST, voice-gate kwargs, duration/dialogue-json) | **PARTIAL_PASS** (offline AST/dry argv) | `verify_backrooms_entrypoint_offline.py`; no live child render |
| 3. Voice bootstrap (first MiniMax take â†’ lock â†’ dependent shot) | **NOT_RUN** | Needs GPU/Comfy + real audio mux |
| 4. Combined boundary/audio production workflow | **NOT_RUN** | Needs GPU + installed Ref2VA/FL2VA graph quals |
| 5. Representative story beats (apartment, C014â€“C016, entity speech, C068â€“C072, ending) | **NOT_RUN** | Targeted GPU checks still required |
| 6. All stills approved barrier | **HELPER_ONLY** | `backrooms_still_contract.py` fail-closed helpers; no approved asset map yet |
| 7. Full 102 production + soak | **NOT_RUN** | Do not claim from short harness / this offline pass |
| 8. Final delivery gate (SELECTED assemble, 17:00, 4:3, speech) | **NOT_RUN** | Downstream of 3â€“7 |

## Voice QA
| Check | Status |
|---|---|
| Spectral cosine alone authorizes identity | **FIXED FAIL-CLOSED** â€” `authorize_speaker_identity=False` without contrast margin |
| Cross-speaker contrast control | **OFFLINE_PASS** expectation in `verify_native_voice_qa_offline.py` |
| Live Alice-vs-Bob 0.986 gate | Historical failure retained as motivation; not re-run live here |

## Honest summary
Offline compile + entrypoint wiring blockers from the audit are addressed in this local copy. Remaining GPU quals 3â€“8 (and live voice bootstrap) are still required before any full-film readiness claim.

## Live follow-on (same day)

| Claim | Status | Proof |
|-------|--------|-------|
| Native Ref2VA output muxes audio stream | PASS | `dual_char_00002_.mp4` has h264+aac; `live_native_voice_mux_report.json` |
| First-take voice bootstrap lock ? dependent shot | NOT_RUN | next |

## Qual 3 voice bootstrap (2026-09-18)

| Claim | Status | Proof |
|-------|--------|-------|
| Dependent blocked before canonical lock | PASS | `blocked_dependent_before_lock` |
| First take extracted + promoted canonical (hash ? disposable seed) | PASS | seed `705139…` vs lock `b6f781…` |
| Refuse later replace of canonical | PASS | `refuse_canonical_replace` |
| Restart preserves voice hash | PASS | sqlite reopen |
| Dependent binds exact locked LoadAudio path/hash + has AAC | PASS | `dep_c002_00001_.mp4`; report `live_jobs/voice_bootstrap_20260918/live_voice_bootstrap_report.json` |

Honest limits: disposable seed used only as Ref2VA conditioner for bootstrap; lock is extracted take. Not ENTITY bootstrap yet. Not calibrated ASR/timbre QA on takes. Not 102-shot.

## Qual 4 combined boundary + audio (2026-09-18)

| Claim | Status | Proof |
|-------|--------|-------|
| Distinct start/last stills in one graph | PASS | different SHA256 |
| ImageToVideo first_frame + last_frame wired | PASS | nodes 9000/9001 |
| Locked canonical voice via MiniMaxH3AddGuide | PASS | LoadAudio ACTOR_canonical_from_take |
| Exact dialogue in prompt | PASS | C002 line |
| Muxed AAC output | PASS | `astra_combined_boundary_audio/combined_00001_.mp4` |
| Pixel-perfect boundary match QA | NOT_RUN | follow-on |

Report: `live_jobs/combined_boundary_audio_20260918/live_combined_boundary_audio_report.json`

## Qual 5 representative beats (compile)

PASS compile-level for C001/C014-C016/C050/C068-C072/C102: Flux, no SDXL LoRA, C050 ENTITY dialogue present, 10s durations.
Report: `live_jobs/representative_beats_compile_20260918/report.json`
GPU story-beat renders: NOT_RUN (blocked on approved Flux stills).

## Qual 6 all stills approved

INVENTORY_ONLY: 204 still specs listed; approved_count=0; animation correctly not authorized.
`live_jobs/all_stills_inventory_20260918/`

## Quals 7–8

NOT_RUN (require approved stills + full coordinator soak).

## Flux canvas + stills (2026-09-18 continued)

| Claim | Status | Proof |
|-------|--------|-------|
| True 4:3 Flux canvas qualified | PASS | EmptyLatentImage **1152x864** (not Comfy preset 1152x896 which is 9:7) |
| C001 start+last Flux stills auto-approved | PASS | `input/astra_backrooms_stills/C001_*.png` |
| C002-C014 apartment stills + shared-boundary aliases | PASS | 15 approved registry ids; contract OK for C001-C014 |
| C015-C102 stills | NOT_RUN | next |
| Conflict ledger operator decisions | TEMPLATE | `CONFLICT_LEDGER_OPERATOR_DECISIONS.md` |

Reports: `live_jobs/flux_canvas_qualify_20260918/`, `live_jobs/flux_stills_batch_20260918/`

## ENTITY voice bootstrap (2026-09-18)

| Claim | Status | Proof |
|-------|--------|-------|
| ENTITY first take lock ? disposable seed | PASS | canonical `1c20f0…` vs seed `705139…` |
| Dependent C051 binds locked hash + AAC | PASS | `astra_entity_voice/dep_c051_00001_.mp4` |
| Report | PASS | `live_jobs/entity_voice_bootstrap_20260918/live_voice_bootstrap_report.json` |
