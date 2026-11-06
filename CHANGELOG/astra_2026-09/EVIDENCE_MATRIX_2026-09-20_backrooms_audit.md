# Evidence matrix — 2026-09-20 Backrooms audit closeout

| Qual / item | Status | Proof |
|---|---|---|
| 1 Exact-pack compile | PASS | outputs_compile/ |
| 2 Entrypoint integration (offline) | PASS | verify_backrooms_entrypoint_offline.py; verify_production_integration_offline.py |
| 3 Voice bootstrap ACTOR+ENTITY | PASS | live_jobs/voice_bootstrap_20260918/; entity_voice_bootstrap_20260918/ |
| 4 Combined boundary+audio | PASS | live_jobs/combined_boundary_audio_20260918/ |
| 4b Pixel-perfect boundary | FAIL_STRICT / chain PASS | live_jobs/pixel_boundary_qa_20260920/ |
| 5 Representative GPU beats | PASS 11/11 | live_jobs/representative_beats_gpu_20260920/live_representative_beats_gpu_report.json |
| 6 Stills technical + contract | PASS (rebuilt registry) | flux_stills_batch_20260918/stills_approved.json |
| 6b Creative stills sign-off | REJECTED_MANY | creative_stills_review_20260920/ |
| Conflict ledger | LOCKED defaults | conflict_ledger_decisions.json |
| 7 Full 102 soak | IN_PROGRESS | qual7_soak_20260920/ |
| 8 Final 17:00 delivery | NOT_PASS (interim only) | qual8_delivery_20260920/master_qual5_representative_selected.mp4 ~17.9s |

## Final readiness
**Not ready** for autonomous 17:00 creative delivery. Engineering gates largely closed except soak completion; creative stills block final claim.
