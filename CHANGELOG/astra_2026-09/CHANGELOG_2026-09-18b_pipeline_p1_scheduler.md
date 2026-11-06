# CHANGELOG 2026-09-18b — pipeline P1 scheduler / store / profiles

Offline-only patches under `/workspace/pipeline_p0/` (copies). No ComfyUI/GPU touched.

## Summary

| ID | Status | What changed |
|----|--------|--------------|
| P1-A | done | SQLite `production_store.py`: attempt rows + `input_hash` before submit; states PLANNED/READY/SUBMITTING/RUNNING/RENDERED/TECHNICAL_QA/CONTENT_QA/SELECTED + failure branches; transactional `select_attempt` with revision fencing; `invalidate_descendants` API; `export_progress_view` (progress.json export, SQLite authoritative). Wired from `master_batch_runner`. |
| P1-B | done | Backrooms/camcorder/VHS/fluorescent/yellow-wallpaper constraints moved into `style_profiles/backrooms_sitcom.json`. Generic path + `style_profiles/generic.json` have no genre hardcoding. CLI `--style-profile` / env `GVD_STYLE_PROFILE`. |
| P1-C | done | `backend_profiles.py` owns steps/scheduler/sampler/denoise/canvas. Planner (`gvd_core`) requests `quality_tier` / `motion_complexity` only — does not invent Wan/FLUX CFG + 16–40 steps for distilled H3. Batch runner resolves hparams via backend profile. |
| P1-D | done | VRAM admission failure is blocking in `generate_video` (`prepare_vram_or_raise`). `free_vram_safe` kwargs contract; `release_gpu_lease` cancels/reconciles prompt before lease release (stub-safe). Orchestrator helpers added. |
| P1-E | done | `dataset_synthesizer` validates bounds (cfg/denoise/steps when present), `quality_tier`/`motion_complexity` enums, multi-scene `scene_ids`, dialogue coverage, continuity aligned with shot schema. |
| P1-F | done | `vhs_postprocess`: REC overlay / effects optional finishing; **off by default**; gated by `--enable` / `GVD_VHS_FINISHING`. |
| P1-G | done | `get_completed_media` resolves only via SELECTED attempt IDs / SELECTED state (JSON or SQLite); no recently-modified MP4 acceptance without acceptance. |

## Files touched

- `handoff/production_store.py` — **new** transactional attempt store + GPU lease helpers
- `handoff/backend_profiles.py` — **new** deterministic sampling profiles
- `handoff/style_profiles/generic.json` — **new**
- `handoff/style_profiles/backrooms_sitcom.json` — **new**
- `handoff/master_batch_runner.py` — style profile + store + SELECTED-only media
- `handoff/generate_video.py` — blocking VRAM admission; free/lease contract; planner tier CLI
- `handoff/gvd_core.py` — planner tiers instead of CFG/steps for H3
- `handoff/dataset_synthesizer.py` — strengthened validation / coverage
- `handoff/local_agent/vhs_postprocess.py` — optional finishing (off by default)
- `handoff/batch_run_backrooms_gvd.py` — backend-profile hparams for H3
- `handoff/local_agent/dspy_orchestrator.py` — admission / cancel-reconcile helpers
- `verify_p1_offline.py` — **new** offline proof suite
- `FILES_CHANGED_P1.txt` — CopyFromBox relative list
- this changelog

## Verify

```bash
python3 /workspace/pipeline_p0/verify_p0_offline.py
# ALL P0 OFFLINE CHECKS PASSED

python3 /workspace/pipeline_p0/verify_p1_offline.py
# ALL P1 OFFLINE CHECKS PASSED
```

## Intentional stubs

- Live Comfy cancel/reconcile/lease methods: stubbed with clear no-op recording when client lacks methods (`production_store.release_gpu_lease` / orchestrator helpers).
- Descendant invalidation works when `parent_shot_id` / `parent_attempt_id` are set; sparse graphs still expose the API.
- `progress.json` remains an export/view; SQLite is authoritative on the new path.
- VHS finishing is not wired into the live orchestrator submit path (still staged); defaults off.

## Ops notes

- Default style is `generic` (no Backrooms bleed). For the sitcom pack: `--style-profile backrooms_sitcom` or `GVD_STYLE_PROFILE=backrooms_sitcom`.
- Default backend profile is `h3_distilled` (20 steps, `simple` / `res_multistep`, no CFG).
- Set `GVD_VHS_FINISHING=1` or pass `--enable` to vhs_postprocess only when finishing is desired; REC overlay needs `--rec-overlay` separately.
