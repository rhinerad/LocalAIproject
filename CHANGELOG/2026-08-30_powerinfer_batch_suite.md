# 2026-08-30 — PowerInfer batch suite orchestrator

## What changed

- Added `tools/powerinfer/batch_suite.ps1`: loops `models.json` ids / HF repos and calls existing `run_pipeline.ps1` stages (`show`, `intake`, `relu-gate`, `calib`, `dump`, `train`, `convert`, `quantize`, `package`). Default is plan-only; GPU/download/delete requires `-Execute`.
- Default vault is `A:\PowerInferModels` (live vault as of 2026-08-30). Optional `-PredictorWorkspace` is passed through so ReluLLaMA can keep using `A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829`.
- After a verified Q4_0 GGUF **and** `activation_*.pt`, `-DeleteIntermediates` removes only `bundle\source\hf` and optional `bundle\source\ablit-fp16`. Never deletes activation/, predictor/, predictor_raw/, GGUF, manifests, or logs.
- ReluLLaMA-7B skips Orion-zhen (already `hidden_act=relu`). `-RunAbliteration` is research-only and still fail-closed at relu-gate (abliterated SiLU is not ReLUfication). Retired `prosparse-7b` is refused. `PowerInfer/ReluLLaMA-7B` is not used (404).
- Saved prior-session `generate_predictor.py` under `tools/powerinfer/` with a header that it is **not** the production dump/train path. Production remains `dump_activations.py` + `train_predictor_layer.py`. `-UseSketchPredictor` is the explicit opt-in. Known sketch bug: ReluMLP already applies ReLU then trains with `binary_cross_entropy_with_logits`.
- Dump/train skip if `activation_0.pt` already exists (`-SkipDumpTrainIfPresent` defaults on). That protects the in-progress ReluLLaMA layers 0–14 from a second dump.
- Did **not** run `-Execute`. Did not start GPU, dump, train, convert, or delete any vault files. Layers 15–31 still need operator go.

## Why

Rhine asked for a suite automation script (HF download → abliterate → predictors → convert.py → quantize Q4_0 → delete intermediates). The live tree already has that pipeline except abliteration, which must not be applied to ReluLLaMA-7B. Wrapping `run_pipeline.ps1` avoids a second convert path that would fight overnight layer training.

## The evidence

Files on disk:

- `tools/powerinfer/batch_suite.ps1`
- `tools/powerinfer/generate_predictor.py` (sketch; first lines state it is not production)

Plan only (no GPU):

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
.\tools\powerinfer\batch_suite.ps1 -Models relu-llama-7b
```

Execute after operator go (ReluLLaMA, reuse existing dump/train workspace, then convert/quantize; does not delete intermediates unless asked):

```powershell
.\tools\powerinfer\batch_suite.ps1 `
  -Models relu-llama-7b `
  -Vault A:\PowerInferModels `
  -PredictorWorkspace "A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829" `
  -Execute
```

Add `-DeleteIntermediates` only when a verified Q4_0 + activations exist and the raw HF tree can go.

## What was verified after

- Files copied onto the canonical local-agent tree.
- No `-Execute`. No huggingface download. No deletion.
- Catalog still has `relu-llama-7b.hf_id = SparseLLM/ReluLLaMA-7B`, `prosparse-7b.retired = true`.

## What is still unverified

- End-to-end suite `-Execute` on ReluLLaMA-7B (dump/train already in progress: layers 0–14 on disk; 15–31 need go).
- `.venv-ablit` / Orion-zhen CLI presence.
- Whether `quantize.exe` convert of a **complete** 32-layer predictor would succeed (assembly is deferred until 0–31 exist).

## Parse check (same session)

Windows PowerShell 5.1 `Parser.ParseFile` on `tools/powerinfer/batch_suite.ps1`: PARSE_OK (1501 tokens). This machine does not have `pwsh`; the suite calls `run_pipeline.ps1` in-process. No `-Execute`.
