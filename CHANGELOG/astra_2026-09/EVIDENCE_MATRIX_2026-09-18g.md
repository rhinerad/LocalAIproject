# Evidence matrix — GVD production readiness (2026-09-18g)

Statuses: IMPLEMENTED | OFFLINE_TESTED | LIVE_SMOKE_TESTED | PRODUCTION_INTEGRATED | ENDURANCE_QUALIFIED | BLOCKED

Authoritative checkout: `COMFYUI_STORY_HANDOFF_2026-08-09` on DuranGamingPC.  
Box `/workspace/pipeline_p0/` is a mirror/scratch only.

## Matrix

| Requirement | Implementation location | Production caller | Offline test | Live artifact/report | Verification scope | Remaining limitation | Status |
|---|---|---|---|---|---|---|---|
| P0 audio gate / SELECTED-only / resume reject | `production_store.py`, `master_batch_runner.py`, verifiers | `master_batch_runner.py` (partial) | `verify_p0_offline.py` (path drift: expects `handoff/gvd_core.py`) | continuity live + suite | scaffolding + bounded live | generate_video still has alternate paths | OFFLINE_TESTED / LIVE_SMOKE_TESTED |
| SQLite store + GPU lease helpers | `production_store.py` | `master_batch_runner.py`, `generate_video.py` (lease refs) | `verify_p1_offline.py` | — | helpers exist | not every agent tool path proven on store | IMPLEMENTED / OFFLINE_TESTED |
| Canonical assets / continuity bind | `canonical_assets.py` | continuity tests / dry-run | `verify_p1_assets_audio_offline.py` | live continuity mp4 | bind plan + invalidate | Story Bible rewrite governance not fully proven in prod runner | OFFLINE_TESTED / LIVE_SMOKE_TESTED |
| Audio timeline modes + dialogue lines | `audio_timeline.py` | store dialogue helpers | `verify_p1_assets_audio_offline.py` | — | mode gates | VoiceAssetRecord still TTS-shaped | OFFLINE_TESTED |
| Bounded H3 continuity fail/resume | `live_continuity_bounded_test.py` | test harness | continuity offline | `astra_live_continuity/continuity_*_00001_.mp4`; ~64.2 s/accepted-sec | bounded live | not full story job | LIVE_SMOKE_TESTED |
| ffmpeg boundary + normalize/concat | live job scripts / suite | remaining suite | final_master plan | `live_jobs/remaining_20260918_111727/final/*` | assembly mechanics | **10:04 master is repeated/padded identical clip** (clip_a sha == clip_b sha); not long-form narrative | LIVE_SMOKE_TESTED |
| Queue/history reconcile + fault inject | `remaining_audit_suite.py`, store reconcile | suite | suite self | `remaining_suite_report.json` | smoke | not full unattended crash matrix on prod CLI | LIVE_SMOKE_TESTED |
| VRAM envelopes / attention | `vram_ref_attn_bench.py` | bench only | — | `vram_ref_attn_report.json` | isolated benches | peaks ~15–15.5 GiB → thin 16 GiB margin; not endurance | LIVE_SMOKE_TESTED |
| ComfyUI 0.36.0 | Rockernow install | server | — | `/system_stats` = 0.36.0 | version | `ASTRA_PRE_UPGRADE_COMMIT.txt` missing at handoff root | LIVE_SMOKE_TESTED |
| FastH3 Dense LoRA 6-step | post36 test | test only | — | `astra_post36/fasth3_00001_.mp4` | smoke | ≠ official FastVideo checkpoint | LIVE_SMOKE_TESTED |
| Ref2VA dotted Autogrow image keys | `post36_ref2va_autogrow_test.py`, **`gvd_graph_builder.py`**, `local_agent/minimax_ref2vid.py` | **new shared builder**; work scripts already had keys; `generate_video.py` does **not** emit | `verify_native_voice_offline.py` | ref_single/dual mp4 + reports | API smoke + unit | dual-image ≠ temporal continuity proof; identity QA not calibrated | LIVE_SMOKE_TESTED / IMPLEMENTED |
| Ref2VA audio Autogrow keys | `gvd_graph_builder.py` (`ref_audios.ref_audio_N`), minimax_ref2vid | shared builder + work audio pass | offline unit | schema via object_info | unit + schema | **no live multi-character native voice GPU proof yet** | IMPLEMENTED / OFFLINE_TESTED |
| Native per-character voice bootstrap + canonical records | **`native_voice_continuity.py`** | not yet wired through `master_batch_runner` / agent tool end-to-end | `verify_native_voice_offline.py` | — | offline | extraction/ffmpeg speaker isolation + live MiniMax conditioning still needed | IMPLEMENTED / OFFLINE_TESTED |
| Forbid silent F5/Fish replacement when native required | `native_voice_continuity.forbid_tts_fallback`; dynamic_voice still contains Fish/F5 | partial | offline | — | unit | generate_video/dynamic_voice still contain TTS paths for explicit alternate backend | OFFLINE_TESTED |
| Final master executable gate | `final_master_audit.execute_normalize_concat` + `--execute` | CLI | integration offline | — | code path | full A/V sync decode gate not endurance-qualified | IMPLEMENTED / OFFLINE_TESTED |
| Unattended job policy | — | — | — | — | — | machine_accepted vs operator_accepted policy module not shipped | BLOCKED |
| Endurance / multi-hour unattended | — | — | — | — | — | explicit plan only | BLOCKED |
| Full storytelling objective | — | — | — | — | — | requires PRODUCTION_INTEGRATED voice + SELECTED assembly of distinct shots | BLOCKED |

## 10:04 master scope (verified)

- Files: `final/master_approx_10min.mp4` (~604.5 s), `final/master_short.mp4` (~10.3 s)
- Inputs under `normalized/`: `clip_a.mp4` and `clip_b.mp4` share **identical SHA256**
- Classification: `assembly_smoke_repeated_or_padded` — proves concat/normalize mechanics, **not** distinct narrative generation or voice continuity

## Ref2VA live smoke vs continuity

- Single/dual image Autogrow execution succeeded post-0.36
- Does **not** by itself prove temporal first/last-frame continuity or identity lock QA thresholds

## Deployed vs Box mirror

- Edit/deploy on handoff root on DuranGamingPC
- Box `/workspace/pipeline_p0` may lag; do not treat as production

## New / changed files this pass

- `gvd_graph_builder.py`
- `native_voice_continuity.py`
- `verify_native_voice_offline.py`
- `verify_production_integration_offline.py`
- `local_agent/minimax_ref2vid.py` (adds `apply_minimax_ref2vid_from_plan`)
- `final_master_audit.py` (`execute_normalize_concat`, `classify_master_scope`, CLI execute flags)
- `CHANGELOG_2026-09-18g_production_voice_integration.md`
- this matrix

## Next qualification steps (ordered)

1. Wire `require_canonical_voices_for_shot` + `apply_minimax_ref2vid_from_plan` into `master_batch_runner` / agent `batch_render_folder` path.
2. Implement clean speaker-segment extraction with rejection reasons; promote canonical only after QA evidence.
3. Bounded live GPU: one bootstrap shot + one dependent shot using canonical `ref_audios.ref_audio_0` (no F5/Fish).
4. Replace 10:04 assembly smoke with SELECTED distinct shots before claiming long-form.
5. Unattended policy object + endurance plan; keep historical operator gates.
