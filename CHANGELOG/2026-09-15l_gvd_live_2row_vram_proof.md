# 2026-09-15l - GVD live 2-row VRAM proof (GVD-B01 + GVD-D01)

Authorized live MIPROv2 against a temporary 2-row slice, 1 candidate / 1 trial.
Does not overwrite `temporal_physics_v1.json`. Full 16-row Beta Set untouched.

- Slice: `GVD-B01` (Backrooms retention) + `GVD-D01` (drone / high-kinematics).
- CLI: `--ids` on `dspy_orchestrator.py`; runner `local_agent/run_gvd_live_2row.py`.
- Preflight this session: :8188 down, :11436 clear, Ollama :11434 up,
  GPU 304 MiB used / 15674 free. Booted owned Rockernow via `BackroomsWatch`.
- Metric now records a `vram_trace` (prepare Comfy / after Wan / release Comfy /
  prepare VLM / after VLM / release VLM) plus `gvd_live_metric_history.jsonl`.
- Save target: `models/dspy_compiled/generalized_video_director_mipro_2row.json`.

Live compile finished 2026-09-15 14:59 Eastern. Elapsed 1780.5s, MIPRO best 0.0.
Saved `models/dspy_compiled/generalized_video_director_mipro_2row.json`.
Did not overwrite `temporal_physics_v1.json`.

Results:
- GVD-D01: Wan mp4 written; mechanical gate rejected (Backrooms physics tokens
  required on a drone clip). Qwen never loaded.
- GVD-B01 trial 1: student LM truncated, missing cfg/denoise/steps. No GPU.
- GVD-B01 trial 2: Wan mp4 written (cfg 5.0 / denoise 0.85 / steps 30). Gate
  rejected missing exact phrase `handheld walking momentum`. Qwen never loaded.
- VRAM: stills peaked ~7.6 GiB, Wan load peaked ~10.1 GiB, after `/free` ~739
  MiB idle. Final after owned Comfy stop: 324 MiB used. `:11436` stayed down.
