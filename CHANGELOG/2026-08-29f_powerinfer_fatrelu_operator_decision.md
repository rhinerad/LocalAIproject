# 2026-08-29 — PowerInfer FATReLU operator decision note (prosparse-7b parked)

## What changed

- Added `docs/POWERINFER_FATRELU_OPERATOR_DECISION_2026-08-29.md`. It records that the already-ingested `SparseLLM/prosparse-llama-2-7b` checkpoint is FATReLU / `SparseLlamaForCausalLM`, that PowerInfer's relu-gate rejects it, and that the operator must choose (a) a supported ReLU/ReLU² sparse model, (b) wait for upstream FATReLU support, or (c) park PowerInfer.
- Did **not** edit `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md`.
- Did **not** change `tools/powerinfer/pipeline_lib.py` `relu_gate()`, `check_relu_gate.py`, or `run_pipeline.ps1`.
- Did **not** download, run `-Execute`, touch the GPU, or continue ReluLLaMA intake.

## Why

The 5:13 PM ET setup-attempt changelog already showed intake complete and `relu-gate` exit 2 (`hidden_act=fatrelu`, `model_type=sparsellama`). That file asked for an operator decision and must not be rewritten. Previous attempts to write the decision note failed on machine registration / resume, so the note did not exist under `docs/` yet. Without it, a later session could treat the parked ProSparse vault as a conversion source or flip the gate.

## The evidence

On-disk `C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf\config.json` (972 bytes):

```json
"architectures": ["SparseLlamaForCausalLM"],
"hidden_act": "fatrelu",
"hidden_act_param": 0.01,
"model_type": "sparsellama"
```

`source_manifest.json`: `created_at` `2026-08-29T21:11:52Z` (5:11 PM ET), repo `SparseLLM/prosparse-llama-2-7b`, 35 files, `combined_sha256` `6654eb0ea085082895792cb8ef635c60f0ae205edfd89008c758dd3746b446ab`. Shard 1 is 4,840,396,416 bytes.

Gate code that closed:

- `tools/powerinfer/pipeline_lib.py` `relu_gate()` lines 226–252: `fatrelu = act.startswith("fatrelu"); ok = act == expected_act.lower() and not fatrelu`; reason `"FATReLU is not supported by PowerInfer"`.
- `tools/powerinfer/check_relu_gate.py` lines 17–31: also fails when `model_type` is not the target's `expected_model_type` (`"llama"`).
- `tools/powerinfer/run_pipeline.ps1` `Invoke-ReluGate` lines 202–206: calls that checker; no `-Execute`.
- `local_agent/test_powerinfer_pipeline.py` `test_fatrelu_is_rejected`.

## What was verified after

Ran, from the canonical tree, with no `-Execute`:

```powershell
python .\tools\powerinfer\check_relu_gate.py --model-id prosparse-7b --source "C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf"
```

Exit code **2**. JSON: `ok: false`, `hidden_act: "fatrelu"`, `model_type: "sparsellama"`, `architectures: ["SparseLlamaForCausalLM"]`, `reason: "FATReLU is not supported by PowerInfer"`, `shape_mismatches: ["model_type='sparsellama'"]`.

Confirmed `docs/` had no prior FATReLU operator decision file before this write. Confirmed `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md` was left untouched.

## What is still unverified

- Whether a later operator-chosen ReLU/ReLU² checkpoint will pass this same gate on its real `config.json`.
- Whether upstream PowerInfer will ever document FATReLU / `SparseLlamaForCausalLM` support. Until it does, choice (b) means wait, not bypass.
- Native RTX 5080 (`sm_120`) compile: CUDA Toolkit 12.8+ and VS 2022 C++ are still absent, independent of the activation mismatch.
- Any live PowerInfer sparse latency/VRAM number. None was collected; the GPU was not used.
- A concurrent session (not this one) wrote further into `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md` at 5:28 PM ET and completed ReluLLaMA-7B intake under `C:\PowerInferVault\relu-llama-7b\20260829-relullama`. This session observed that vault read-only afterward (`hidden_act=relu`, `LlamaForCausalLM`) and did not rewrite the 5:13 PM setup-attempt file.