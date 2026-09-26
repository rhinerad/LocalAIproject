# GVD Watcher Pipeline (2026-09-18)

## Phase 1 — Rules lock
- Module: `local_agent/gvd_pipeline_rules.py`
- Lock JSON: `local_agent/runtime/gvd_backrooms_batch/PIPELINE_RULES_LOCK.json`
- Wired into `batch_run_backrooms_gvd.py` (scrub SDXL/weights, expand universal negative, env cues for non-literal clips).
- MiniMax length remains forced to 192 in `dspy_orchestrator._force_frame_length`.
- `--silent-fallback` sets `GVD_F5_TTS=0` (skip Fish/F5).

## Phase 2 — Watcher
- `gvd_watcher.py` at project root
- Audit: `local_agent/runtime/logs/watcher_audit.log`
- PID: `local_agent/runtime/logs/gvd_watcher.pid`
- Skips progress `done` clips; heals OOM via `/free` retry; audio/auth via `--silent-fallback`; flushes VRAM after every clip.

## Launch
```bash
python -u gvd_watcher.py
python -u gvd_watcher.py --dry-run --limit 5
python -u gvd_watcher.py --start-from C008
```