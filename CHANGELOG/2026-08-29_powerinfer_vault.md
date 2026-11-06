# 2026-08-29 — PowerInfer encrypted vault layout

## What changed

- Added `tools/powerinfer/vault.py` and `tools/powerinfer/init_vault.py`.
- Layout (preferred `D:\PowerInferModels`, outside the git tree): `production/`,
  `quarantine/`, `scratch/`, `private/`, `keys/`, plus per-build `source`,
  `calibration`, `activation`, `predictor`, `output`, `validation`, `runtime`.
- Free-space preflight refuses when free bytes are below need plus 20%.
- `protect_source` SHA-256s shards then sets them read-only.
- Private calibration/result files encrypt to AES-256-GCM envelopes; plaintext
  is not deleted. Access is append-logged without payload text.
- Vault init refuses a path inside this repository unless `--allow-in-repo`.
- There is no delete/rmtree helper for conversion evidence.

## Deliberate non-changes

- Did not edit `tools/powerinfer/run_pipeline.ps1` (including the required
  `-VramBudget` behavior).
- Did not run `-Execute` against a ReLU checkpoint or load the 5080 for
  conversion. A bench-without-budget check used `-Execute` only far enough to
  hit the VramBudget throw; `main.exe` / `server.exe` were not started.
- Did not create `D:\PowerInferModels` on disk in this session.

## Evidence

- `run_pipeline.ps1 -ModelId prosparse-7b` printed
  `vram-budget : (not set -- required before validate/bench)` and exited 0.
- `run_pipeline.ps1 -ModelId prosparse-7b -Stage bench -Execute` (no
  `-VramBudget`) threw `Pass -VramBudget <GiB> explicitly -- no silent default
  reaches the GPU binary` and named the GPU gateway/idle check. nvidia-smi was
  queried by preflight; no model was loaded.
- `python -m unittest test_powerinfer_pipeline -v` from `local_agent/`: 14/14
  passed (previous 8 plus 6 vault tests).
