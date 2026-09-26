# CHANGELOG 2026-09-18d — continuity failure/resume + benchmark profiles + master audit

Offline-only scaffolding under `/workspace/pipeline_p0/` (copies). No ComfyUI/GPU renders.

## Summary

| ID | Status | What changed |
|----|--------|--------------|
| § continuity harness | done | `handoff/continuity_failure_resume_offline.py`: RENDERED→QA_PENDING crash resume (no skip); tech QA fail→RETRY_PENDING; parent re-select invalidates child first_frame bind; SUBMITTING without prompt_id reconcile does not duplicate-enqueue. |
| § verify | done | `verify_continuity_offline.py` proves the harness + profiles + master audit offline. |
| §12 profiles | done | `handoff/benchmark_profiles/*.json` RTX 5080 starting points (not measured guarantees): base_continuity_validation, base_production_trial, high_resolution_trial, multi_reference, fast_draft (FastH3 placeholder + ComfyUI≥0.36 warning). |
| §12 metric | done | `handoff/benchmark_profiles/wall_clock_metric.md` + `backend_profiles.wall_clock_per_accepted_second`. |
| §12 wire | done | `backend_profiles.list_benchmark_profiles` / `get_benchmark_profile` / `benchmark_to_backend_hparams`. |
| §13 audit | done | `handoff/final_master_audit.py`: job-dir checklist (SELECTED, deps, QA pending, frame counts, dialogue, provenance) + ffmpeg normalize/concat **argv plan only** (never executes on missing media). |
| store helpers | done | `production_store`: `RETRY_PENDING`, `resume_should_skip_attempt`, `mark_technical_qa`, `reconcile_submitting_without_prompt_id`. |

## Verify (all green)

```bash
python3 /workspace/pipeline_p0/verify_p0_offline.py
python3 /workspace/pipeline_p0/verify_p1_offline.py
python3 /workspace/pipeline_p0/verify_p1_assets_audio_offline.py
python3 /workspace/pipeline_p0/verify_continuity_offline.py
# ALL CONTINUITY/BENCHMARK/AUDIT OFFLINE CHECKS PASSED
```

## Intentional stubs / non-goals

- No live Comfy submit, cancel, history poll, or GPU benchmark timing.
- FastH3 profile is a placeholder until ComfyUI ≥ 0.36 is confirmed on the render host.
- `final_master_audit.build_normalize_concat_plan` returns argv only — operators run ffmpeg when media exists.
- Benchmark JSON values are **starting points**, not wall-clock guarantees on RTX 5080.

## Ops notes

- Resume skip remains SELECTED-only (P0-6); QA_PENDING / RENDERED / RETRY_PENDING must continue.
- Parent SELECTED switch invalidates continuous children (boundary first_frame bind).
- Uncertain SUBMITTING (no prompt_id) → reconcile queue/history only; never second enqueue.
