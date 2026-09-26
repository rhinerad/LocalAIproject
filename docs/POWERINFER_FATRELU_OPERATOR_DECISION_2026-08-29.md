# PowerInfer FATReLU operator decision — 2026-08-29

**Status:** waiting on an operator choice. The relu-gate stays closed.
**This note does not authorize a download, a GPU stage, a gate bypass, or a ReluLLaMA intake.**

Written 2026-08-29 at 5:28 PM ET. The existing ProSparse intake is already on disk; this session only read it and ran the gate.

## Finding

`SparseLLM/prosparse-llama-2-7b` is a **FATReLU / `SparseLlamaForCausalLM`** checkpoint. PowerInfer's conversion pipeline **rejects** it. The weights are already ingested and must be treated as parked evidence, not as a conversion source.

On-disk `config.json` at
`C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf\config.json`:

| field | value |
|---|---|
| `_name_or_path` | `SparseLLM/prosparse-llama-2-7b` |
| `hidden_act` | `fatrelu` |
| `hidden_act_param` | `0.01` |
| `model_type` | `sparsellama` |
| `architectures` | `["SparseLlamaForCausalLM"]` |
| `hidden_size` / `intermediate_size` / `num_hidden_layers` | `4096` / `11008` / `32` |

FATReLU is not plain ReLU. With `hidden_act_param: 0.01` the activation is a floored ReLU (`max(x, 0.01)`), so neurons that would be exactly zero under ReLU stay at the floor. PowerInfer's CUDA solver builds GPU index tensors from a ReLU sparsity map (a neuron is either zero or positive). Feeding it FATReLU activations would produce an incorrect sparsity map. The failure mode is not a reliable crash; it is plausible-looking wrong output.

## Intake already on disk

Do not re-download. Do not delete.

| item | path |
|---|---|
| vault / bundle | `C:\PowerInferVault\prosparse-7b\20260829-prosparse` |
| HuggingFace snapshot | `C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf` |
| source manifest | `C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\source_manifest.json` |

`source_manifest.json` records:

- `created_at`: `2026-08-29T21:11:52Z` (5:11 PM ET)
- `repo`: `SparseLLM/prosparse-llama-2-7b`
- `count`: 35 files
- `combined_sha256`: `6654eb0ea085082895792cb8ef635c60f0ae205edfd89008c758dd3746b446ab`
- six weight shards totaling ~26.9 GB (`model-00001-of-00006.safetensors` is 4,840,396,416 bytes)

This is the correct HuggingFace ProSparse-LLaMA-2-7B snapshot. The gate is rejecting a real property of that model, not a corrupt download.

## Gate that refused it

The pipeline fails closed unless `hidden_act` is exactly the expected ReLU-family string **and** the activation is not FATReLU **and** the recorded shapes / `model_type` match the target.

### `tools/powerinfer/pipeline_lib.py` — `relu_gate()` (lines 226–252)

```python
def relu_gate(source_dir: Path, expected_act: str = "relu") -> dict[str, Any]:
    config_path = source_dir / "config.json"
    ...
    act = str(config.get("hidden_act") or "").lower()
    ...
    fatrelu = act.startswith("fatrelu")
    ok = act == expected_act.lower() and not fatrelu
    return {
        "ok": ok,
        ...
        "reason": None
        if ok
        else (
            "FATReLU is not supported by PowerInfer"
            if fatrelu
            else f"hidden_act={act!r} is not {expected_act!r}; ReLUfy before dump/train/convert"
        ),
    }
```

The `startswith("fatrelu")` check is deliberate: a value such as `fatrelu` or `fatrelu_0.01` is refused even if someone later aliases it toward `"relu"`.

### `tools/powerinfer/check_relu_gate.py` (lines 17–31)

Wraps `relu_gate()`, then also fails on shape / `model_type` mismatches against `models.json`:

- expected `hidden_act`: `"relu"`
- expected `model_type`: `"llama"`
- expected shapes: `4096 / 11008 / 32`

`model_type='sparsellama'` is therefore a second, independent refusal. Exit code `2` means closed.

### `tools/powerinfer/run_pipeline.ps1` — `Invoke-ReluGate` (lines 202–206)

```powershell
function Invoke-ReluGate {
    $src = Get-Source $Target $Bundle
    if (-not $src) { throw 'no source checkpoint. Pass -SourceDir or run intake.' }
    Invoke-Py (Join-Path $Tools 'check_relu_gate.py') --model-id $ModelId --source $src
}
```

`-Stage relu-gate` is read-only. It does not take `-Execute`. Later GPU stages (`dump`, `train`, `validate`, `bench`) must not run until this gate returns `ok: true`.

### Offline unit coverage

`local_agent/test_powerinfer_pipeline.py` → `ReluGateTests.test_fatrelu_is_rejected` already asserts that `hidden_act: "fatrelu_0.01"` yields `ok: false` and a reason containing `"FATReLU"`.

## Live gate result from this session

Command (no `-Execute`, no download, no GPU):

```powershell
python .\tools\powerinfer\check_relu_gate.py --model-id prosparse-7b --source "C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf"
```

Exit code **2**. Printed JSON:

```json
{
  "ok": false,
  "config_path": "C:\\PowerInferVault\\prosparse-7b\\20260829-prosparse\\source\\hf\\config.json",
  "hidden_act": "fatrelu",
  "model_type": "sparsellama",
  "architectures": [
    "SparseLlamaForCausalLM"
  ],
  "hidden_size": 4096,
  "intermediate_size": 11008,
  "num_hidden_layers": 32,
  "reason": "FATReLU is not supported by PowerInfer",
  "shape_ok": false,
  "shape_mismatches": [
    "model_type='sparsellama'"
  ]
}
```

Two independent closures: FATReLU activation, and `sparsellama` vs expected `llama`.

## Operator choices

Pick **one**. Do not combine them by flipping the gate.

### (a) Pick a supported ReLU / ReLU² sparse model

Choose a checkpoint whose `config.json` reports a PowerInfer-supported activation (`relu` or ReLU² / ReGLU as the pipeline actually accepts) and `model_type` / architecture the gate and converter know. Then, and only then, run a **new** intake into a new vault bundle. Do not reuse the ProSparse FATReLU snapshot as if it were that model.

A prior session already registered `relu-llama-7b` in `tools/powerinfer/models.json` (`hf_id`: `SparseLLM/ReluLLaMA-7B`, `expected_hidden_act`: `"relu"`, `expected_model_type`: `"llama"`) and marked `prosparse-7b` `retired: true`. That is a **candidate registration**, not completion of this choice. This note does **not** authorize downloading ReluLLaMA, continuing `C:\PowerInferVault\relu-llama-7b\20260829-relullama`, or treating that registry edit as operator sign-off.

Whatever model is chosen still has to pass `relu-gate` on the actual downloaded `config.json`. Registry comments are not a substitute for the gate.

### (b) Wait for upstream FATReLU support

Leave the ProSparse vault parked. Do not convert, dump, train, or serve it. Revisit only if upstream PowerInfer documents FATReLU / `SparseLlamaForCausalLM` as a first-class sparse path **and** this tree's `relu_gate` is updated to match that documented contract. Until then the gate stays closed.

### (c) Park PowerInfer

Stop the conversion track. Keep the existing adapter (`local_agent/powerinfer_openai_proxy.py`) unlaunched and unwired. Keep the ProSparse vault as evidence. Existing Ollama routes remain the interactive fallback. CUDA Toolkit / VS 2022 C++ install for `setup` can wait.

## What this note does not authorize

- Flipping, commenting out, or bypassing `relu_gate` / `check_relu_gate.py` / `Invoke-ReluGate`.
- Passing `-Force` to pretend FATReLU is ReLU.
- Any `-Execute` stage (`setup`, `intake`, `calib`, `dump`, `train`, `convert`, `quantize`, `package`, `validate`, `bench`).
- A new HuggingFace download.
- GPU use, ComfyUI, Redis/Celery real export, WSL Sideband/APK work, `.env` reads, or `git push`.
- Deleting `C:\PowerInferVault\prosparse-7b\20260829-prosparse`.

## Related record (do not rewrite)

`CHANGELOG/2026-08-29_powerinfer_setup_attempt.md` already recorded the 5:13 PM ET intake and the same gate refusal. This note is the operator decision surface that file asked for; it does not replace that evidence log.

Independent of (a)/(b)/(c), compiling PowerInfer on this workstation still needs CUDA Toolkit 12.8+ (`nvcc`, `sm_120`) and Visual Studio 2022 with the C++ workload. That toolchain gap is separate from the FATReLU incompatibility.

## Default until the operator answers

Treat PowerInfer conversion as **parked on the existing FATReLU intake**. Continue only after an explicit (a), (b), or (c).

## Concurrent vault fact (not produced by this note)

While this file was being written, another session filled `C:\PowerInferVault\relu-llama-7b\20260829-relullama\source\hf`. This session did not start that download. Read-only listing afterward showed 14 files including three `.safetensors` shards and three `.bin` shards. `config.json` reports `hidden_act: "relu"`, `model_type: "llama"`, `architectures: ["LlamaForCausalLM"]`. That is a ReLU candidate already on disk for choice (a). It is **not** operator sign-off of (a) versus (b) versus (c), and it does not authorize `setup`/`dump`/`train`/`convert` or a gate change. The ProSparse FATReLU bundle remains parked evidence.