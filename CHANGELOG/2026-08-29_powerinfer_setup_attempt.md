# 2026-08-29 — PowerInfer pipeline: prosparse-7b retired, ReluLLaMA-7B adopted, intake running

## Summary of changes in this session

`tools/powerinfer/models.json` — new target `relu-llama-7b` added with
`hf_id: SparseLLM/ReluLLaMA-7B`; `prosparse-7b` retained but marked
`retired: true` with reason. Note recorded that `PowerInfer/ReluLLaMA-7B`
returns 404 on HuggingFace; `SparseLLM/ReluLLaMA-7B` is the correct public repo.
`tools/powerinfer/run_pipeline.ps1` — `relu-llama-7b` added to `ValidateSet`.
`C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf` — ProSparse weights
kept as evidence, not deleted.
`C:\PowerInferVault\relu-llama-7b\20260829-relullama\source\hf` — ReluLLaMA-7B
weights downloaded (14 files, exit 0). relu-gate passed (`ok: true`).

---

## What changed

- Ran GPU preflight before touching anything: RTX 5080, 29 °C, 0 % utilization,
  1392 MiB / 16303 MiB used (14.9 GB free). Only `C+G` display-GPU users (browser,
  ChatGPT desktop, Steam). Thermal guard: clear to proceed.
- Ran `run_pipeline.ps1 -ModelId prosparse-7b -Stage show` with
  `$env:POWERINFER_VAULT = 'C:\PowerInferVault'` to confirm the plan resolves:
  vault `C:\PowerInferVault\prosparse-7b\20260829-prosparse`, source from
  `SparseLLM/prosparse-llama-2-7b` on HuggingFace, CUDA combo `VS 17 2022 x64 /
  -DLLAMA_CUBLAS=ON / CMAKE_CUDA_ARCHITECTURES=120 (sm_120 = RTX 5080 Blackwell)`.
- Started `intake` stage (`-Execute -Vault C:\PowerInferVault -BuildId 20260829-prosparse`)
  to pre-download model weights while diagnosing the build prerequisites. The download
  began successfully: vault init at `C:\PowerInferVault` passed (outside repo),
  `snapshot_download` from HuggingFace started, 16 files fetching.
- Confirmed that no D: drive exists; vault fallback correctly redirected to
  `C:\PowerInferVault` via `-Vault` parameter (runbook step 1.6 procedure applied).

## Why (blocked here)

The `setup` stage compiles PowerInfer from C++/CUDA source and requires all three of:

| Tool | Status |
|---|---|
| CUDA Toolkit 12.8+ (`nvcc`, `sm_120`) | **not installed** — not found on C: or A: |
| Visual Studio 2022 with C++ workload | **not installed** — only VS 14.0 (2015) in registry; no VS Installer |
| cmake (bundled with VS or standalone) | **not installed** — not on PATH |

Evidence:
- `nvcc --version` in PowerShell: `CommandNotFoundException`
- `where.exe cmake`: `Could not find files`
- `where.exe cl.exe msbuild`: both not found
- `HKLM:\SOFTWARE\Microsoft\VisualStudio` — only `14.0` key exists; no `SxS\VS7` path
- `C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe` — does not exist
- `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` — does not exist

Stages that can still run without the build:
- `intake` (HuggingFace download): running — only needs `huggingface_hub` (v1.27.0 ✓)
- `calib` (C4 calibration): blocked — needs `datasets` package, which is installed
  by `setup`'s pip step

All subsequent stages (`dump`, `train`, `convert`, `quantize`, `validate`, `bench`,
and the server launch) require compiled binaries from `setup`.

## Evidence

```
nvidia-smi output (2026-08-29 17:04):
  NVIDIA GeForce RTX 5080  WDDM  29 C  P8  0%  1392 MiB / 16303 MiB
  No compute-only processes.

Drive enumeration:
  A:  (project drive)
  C:  (system drive)
  -- D: does not exist --

show-stage output:
  vault/bundle       : C:\PowerInferVault\prosparse-7b\20260829-prosparse
  CUDA combo         : VS 17 2022 x64, -DLLAMA_CUBLAS=ON, CMAKE_CUDA_ARCHITECTURES=120
  execute            : True (intake run)

intake job (in progress at time of this entry):
  Fetching 16 files: 56%+ of SparseLLM/prosparse-llama-2-7b
  Destination: C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf
```

## prosparse-7b retirement rationale

`SparseLLM/prosparse-llama-2-7b` was the original `hf_id`. The downloaded
`config.json` shows `hidden_act: "fatrelu"` with `hidden_act_param: 0.01` and
`model_type: "sparsellama"` / `architectures: ["SparseLlamaForCausalLM"]`.

FATReLU(x) = max(x, threshold) is **not plain ReLU**. PowerInfer's CUDA solver
builds GPU index tensors from activation sparsity — it pre-computes which
neurons fire and routes computation accordingly. That analysis assumes exactly
relu(x) = max(x, 0): a neuron is either zero or positive with no floor.
FATReLU keeps neurons at ≥ 0.01 even when they would otherwise be zero, so
the sparsity pattern is materially different; the solver's offload decisions
would be made against an incorrect sparsity map. The risk is not a hard crash
— it is subtly wrong outputs that look plausible and are difficult to detect.

The gate (`pipeline_lib.relu_gate`) was correct to reject this. It is left
unchanged.

`PowerInfer/ReluLLaMA-7B` is the model the PowerInfer team actually built the
pipeline and paper results around: LLaMA-2-7B retrained to use plain ReLU in
place of SiLU, so every neuron is truly zero or positive with no floor.
Its config.json is expected to show `hidden_act: "relu"` and `model_type:
"llama"`, which the gate will accept without modification.

## What is needed from the operator

Two free installs, in this order:

1. **CUDA Toolkit 12.8** (or newer, must include `nvcc` and match sm_120 / Blackwell):
   Download from developer.nvidia.com/cuda-downloads. The RTX 5080 (Blackwell, sm_120)
   requires CUDA 12.8+. The driver already supports CUDA 13.2; the toolkit is a separate
   install and is currently absent.

2. **Visual Studio 2022 Community** (free) with the **"Desktop development with C++"**
   workload selected during install. This provides MSVC, cmake, and the MSBuild generator
   that the pipeline's cmake call (`-G "Visual Studio 17 2022"`) requires. cmake can
   alternatively be installed standalone via `winget install Kitware.CMake` but VS 2022
   is still needed for the C++ compiler.

After both are installed, open **"Developer PowerShell for VS 2022"** (Start → search
for it by name) so `nvcc` and `cmake` land on PATH, then re-run:

```powershell
cd "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
.\tools\powerinfer\run_pipeline.ps1 -ModelId prosparse-7b -Stage setup -Execute -Vault C:\PowerInferVault -BuildId 20260829-prosparse
```

The `intake` download will be complete by then; subsequent stages
(`relu-gate`, `calib`, `dump`, `train`, `convert`, `quantize`, `package`, `validate`,
`bench`) can proceed in order from there without re-downloading the model.

## relu-gate result for ReluLLaMA-7B: PASSED

```json
{"ok": true, "hidden_act": "relu", "model_type": "llama",
 "architectures": ["LlamaForCausalLM"],
 "hidden_size": 4096, "intermediate_size": 11008, "num_hidden_layers": 32,
 "shape_ok": true, "shape_mismatches": []}
```

Build ID `20260829-relullama` is cleared through relu-gate. All stages from
`setup` onward are unblocked once VS 2022 + CUDA Toolkit 12.8 are installed.

---

## relu-gate failure on prosparse-7b (context for the retirement decision)

After intake completed (all 16 files, exit 0), `relu-gate` was run immediately:

```json
{
  "ok": false,
  "hidden_act": "fatrelu",
  "model_type": "sparsellama",
  "architectures": ["SparseLlamaForCausalLM"],
  "reason": "FATReLU is not supported by PowerInfer",
  "shape_mismatches": ["model_type='sparsellama'"]
}
```

`SparseLLM/prosparse-llama-2-7b` (the `hf_id` in `models.json`) ships with
`hidden_act: "fatrelu"` and a custom `SparseLlamaForCausalLM` architecture.
The gate in `pipeline_lib.relu_gate()` has `fatrelu = act.startswith("fatrelu");
ok = act == expected_act.lower() and not fatrelu` — FATReLU is explicitly
excluded regardless of the threshold value (here `hidden_act_param: 0.01`).
`models.json` records `expected_hidden_act: "relu"` and `expected_model_type:
"llama"` for this target; neither matches.

The downloaded model IS the correct HuggingFace checkpoint (6 shards,
~26.9 GB total, matching ProSparse-LLaMA-2-7B); the gate is catching a real
property of the model, not a download error. FATReLU(x) = max(x, 0.01) is
not the same activation function as ReLU, and whether PowerInfer's CUDA
solver handles it correctly is an open question that the gate is designed to
force explicit human sign-off on.

**This gate should not be crossed without operator instruction.** See the
main report below for what the operator needs to decide.

## Verification

- GPU preflight: `nvidia-smi` output captured above, 29 °C / 0 % / 14.9 GB free.
- Vault safety: `C:\PowerInferVault` is outside `REPO_ROOT`; `assert_outside_repo` passes.
- Intake: completed, exit 0 — 16/16 files, `downloaded SparseLLM/prosparse-llama-2-7b -> C:\PowerInferVault\prosparse-7b\20260829-prosparse\source\hf`
- relu-gate: ran, exit 2, full JSON recorded above.
- No render or ComfyUI process touched; GPU remains idle.
