# 2026-08-29 — Cross-checked the concurrent PowerInfer pipeline against the coordination prompt

## Context

Earlier this session, replied to Grok's PowerInfer control-plane plan with two
specific asks: (1) record hashes/versions/benchmarks as evidence, not just log
them; (2) make `--vram-budget` a required argument with no silent default, and
print a GPU-gateway/idle-status reminder before launching. Grok's
`tools/powerinfer/` landed while this session was doing the worker_farm work
(see `CHANGELOG/2026-08-29_powerinfer_native_pipeline.md`). Checked it against
those two asks rather than assuming they were honored, and independently
re-ran the claimed test evidence rather than trusting the changelog's "8/8" by
itself.

## What was verified as correct

- Native Windows build (VS 2022 x64, `-DLLAMA_CUBLAS=ON`,
  `CMAKE_CUDA_ARCHITECTURES=120`), not WSL2 — matches the reply prompt.
- `record_acceptance_gate.py` writes `acceptance_gate.json` with cold/warm
  20-turn latency, tokens/sec, host RAM, VRAM, and SHA-256 of the GGUF,
  predictor tree, and `activation/` files — matches the "record evidence, not
  just log it" ask.
- `check_gpu_preflight.py` is called from `Assert-Execute` before any GPU
  stage and refuses with the blocking owner list if ComfyUI/another render
  process holds the GPU — this is actually stronger than what was asked for
  (an automated refusal instead of just a printed reminder).
- Independently reran `python -m unittest test_powerinfer_pipeline -v` from
  an isolated copy (`pipeline_lib.py`, `models.json`, and the test file only,
  no GPU/network needed) in this session's sandbox: **8/8 passed**, matching
  the claimed evidence.

## What was not honored, and the fix

`run_pipeline.ps1` declared `[double]$VramBudget = 12` — a real default, not
`Mandatory`, and not what was asked. A silent 12 GiB would have reached
`main.exe`/`server.exe`/`record_acceptance_gate.py` on any `validate`/`bench`
run where the operator forgot to pass `-VramBudget` explicitly.

Fixed directly rather than only flagging it, since it's small and matches the
original request precisely:

- Changed the parameter to `[Nullable[double]]$VramBudget = $null`.
- `Invoke-ValidateAndBench` — the only function that actually forwards
  `$VramBudget` to a GPU binary — now throws before doing anything if it's
  still `$null`, with a message naming the GPU gateway/idle check explicitly.
  `-Stage show` and every non-GPU stage remain usable with zero required
  flags beyond `-ModelId`, since the plan-preview mode was never the problem.
- `Show-Plan`'s output now prints `(not set -- required before validate/
  bench)` instead of a numeric default, so a dry-run preview doesn't imply a
  budget is already chosen.

## Verification

- Reran the 8-test offline suite after the edit (unaffected — it doesn't
  touch `run_pipeline.ps1`, which needs `pwsh` and isn't runnable in this
  sandbox).
- `run_pipeline.ps1` itself could not be executed or syntax-checked here (no
  `pwsh`, no GPU, no PowerInfer checkout). Read through twice for correctness:
  confirmed `Invoke-Dump`/`Invoke-Train`/`Invoke-Convert`/`Invoke-Quantize`
  never reference `$VramBudget` (so they're correctly unaffected by the
  stricter check), and only the two `Invoke-ValidateAndBench` code paths
  (plain validate's `Start-Process -ArgumentList` and bench's
  `record_acceptance_gate.py --vram-budget`) consume it.

## What is unverified

The actual PowerShell parsing of `[Nullable[double]]` as a param type and the
`$null -eq $VramBudget` check have not been run through a real PowerShell
interpreter — this sandbox has none. This is standard, well-established
PowerShell syntax, but per this project's own verification standard, "should
work" is not the same as "ran it." Flagging for the next session with `pwsh`
or a live Windows terminal to confirm `-Stage show` still runs with just
`-ModelId`, and that `-Stage bench` without `-VramBudget` throws the new
message instead of silently defaulting.
