# 2026-08-29 — Single vault path resolver

## What changed

- Deleted the broken `pipeline_lib.default_vault()` loop, which always returned
  `D:\PowerInferModels` because `path == DEFAULT_VAULT_CANDIDATES[0]` was true
  on the first iteration even when that path did not exist.
- `vault.default_vault_path()` is the only Python resolver:
  `POWERINFER_VAULT` → `D:\PowerInferModels` if that path or its parent exists
  → else `artifacts/powerinfer_vault`.
- `init_vault.py status` now prints that resolver as `default` instead of a
  second, disagreeing `pipeline_default`.
- `run_pipeline.ps1` `Get-Vault` calls `vault.default_vault_path()` instead of
  a third PowerShell copy. `-VramBudget` remains required (`$null` default).

## Evidence

- `python -m unittest test_powerinfer_pipeline -v`: 18/18. New cases cover env
  override, missing preferred drive → fallback, preferred parent present →
  `D:\PowerInferModels`, and that `pipeline_lib` no longer exports
  `default_vault`.
- No `-Execute` against a ReLU checkpoint.
