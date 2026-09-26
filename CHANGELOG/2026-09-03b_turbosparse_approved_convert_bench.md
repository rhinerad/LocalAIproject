# 2026-09-03b — TurboSparse approved-20260902 convert/quantize/package/bench

GPU go-ahead. Did not dump. Did not train predictors. Did not edit the immutable
o_proj tree. Dump profile remains 25000 samples (profile_meta n_written=25000
on all 32 layers). Did not retry 400k.

## A convert / quantize / package — PASS

SourceDir was the edited checkpoint
`A:\PowerInferModels\turbosparse-mistral-instruct\turbosparse-approved-20260902-182522\source\edited`
(not source\hf, not the parked 20260830b tree).

`convert.py` needed two local tooling patches (weights untouched):

- skip HF-baked `model.layers.{L}.mlp.predictor.fc1/fc2` tensors; GGUF predictors
  come from the retrained `predictor/model_{L}.pt` files as `blk.{L}.fc1/fc2`
- pad SentencePiece+added_tokens vocab 32002 → model `n_vocab` 32064 with dummy
  `[PAD{i}]` tokens (ChatML `<|im_start|>` / `<|im_end|>` kept)

F16 GGUF: `output\turbosparse-mistral-instruct.powerinfer.gguf`
14,787,775,552 bytes, sha256 `14474bd8f1d76fa7246bca5b9b63312fd661807dbe56eda38223015f493678d2`.
PWRI magic, 355 tensors, `blk.0.fc1/fc2` … `blk.31.fc1/fc2` all present.

Q4 GGUF: `output\turbosparse-mistral-instruct.q4.powerinfer.gguf`
4,194,219,136 bytes, sha256 `59318ed894f16d791ee418cb1536ba9bab62a85986a6a7b112ce59b17436c98b`.
quantize.exe Q4_0, 695.8 s, all 32 predictor tensors quantized.

Package: activation copy succeeded; `run_pipeline.ps1` `Invoke-Py @(...)` collapsed
argv so `write_manifest.py` was invoked directly. `manifest.json` status
`candidate`. Prompt contract hash
`151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`
status `verified_local_contract`.

## B bench — mechanical PASS, agentic quality FAIL

Idle nvidia-smi before bench: 28 C, 56 MiB, util 0%. `-SkipGpuPreflight` after
that snapshot (do not run `check_gpu_preflight.py` as a script). Loaded the NEW
q4 GGUF only. VramBudget 12.

`record_acceptance_gate.py` main.exe smoke succeeded (CUDA, FFN split, ~34.6 tok/s
eval, ~5928 MB reported VRAM) but `server.exe` started via pipeline `Popen(text=True)`
exited before listen. Relaunch with cwd=`output` and `PYTHONPATH`=PowerInfer tree
stayed up on 127.0.0.1:8080.

20-turn cold+warm via `record_acceptance_gate._run_session` (checkpoint_chatml):
- cold: 20/20, 0 failures, mean latency 0.58 s, decode tok/s p50 ~52 (mean polluted by tiny predicted_ms outliers)
- warm: 20/20, 0 failures, mean 36.17 tok/s, p50 36.09, p95 38.86
- GPU during bench max observed: 40 C, 5183 MiB, util 55% (thermal cap 82 C never hit)
- post: 30 C, 55 MiB, util 0% after server stop

Wrote `validation\acceptance_gate.json`. Checklist all true.

Agentic quality gate (2 JSON tool-call turns) against the same server and verified
prompt_contract.json: **failed_turn_1** (`invalid_json`). Response was garbled
prose, not a JSON tool call. Wrote `validation\agentic_quality_gate.json`. Did
not fake a pass. Server then stopped.

## C registry — FAIL

`production_registry.py register` REFUSED: `manifest status must be accepted`.
Did **not** flip status to `accepted` because the agentic gate failed. Did not
write `A:\PowerInferModels\registry\production_models.json`. Provenance:
`validation\registry_attempt.2026-09-03.json`.

20260830b parked: untouched. Spot-check `config.json` / `model.safetensors.index.json`
mtimes remain 2026-08-30 18:35 ET; hashes unchanged. No writes into that tree.
