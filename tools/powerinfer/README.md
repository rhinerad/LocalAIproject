# PowerInfer native Windows conversion pipeline

Opt-in runner for the preparation track in
`docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md`. It does **not** start
the local-agent GUI, bind anything except the optional native `127.0.0.1:8080`
server during `bench`, or add a model to the picker.

## Native Windows vs WSL2

This tree’s OpenAI proxy (`local_agent/powerinfer_openai_proxy.py`) talks to
`http://127.0.0.1:8080` from **native** Python. The control-plane plan launches
`A:\PowerInferBuild\bin\server.exe`. The pipeline therefore **targets a native
Windows build**, not WSL2. The runner uses VS 2022's developer environment and
Ninja, with `A:\PowerInferNative` as a short junction to the canonical source,
because the Windows compiler can fail on the repository's deep path.

## Production registry gate

The proxy does not start until a human has explicitly registered an **accepted**
bundle. Registration rechecks the manifest status, hashed GGUF, all recorded
acceptance checks, and the model's supported-sparse route. It is a local
filesystem action only; it does not launch the backend or use the GPU.

```powershell
# After the controlled benchmark and human coherence review are complete:
py -3 tools\powerinfer\production_registry.py `
  --registry D:\PowerInferModels\registry\production_models.json `
  register --manifest D:\PowerInferModels\relu-llama-7b\<build-id>\manifest.json `
  --evidence-id "operator-review-<id>"

# A future manual proxy start must identify that exact accepted entry.
$env:POWERINFER_REGISTRY_PATH = 'D:\PowerInferModels\registry\production_models.json'
$env:POWERINFER_REGISTRY_MODEL_ID = 'relu-llama-7b'
$env:POWERINFER_MODEL_ALIAS = 'powerinfer-relu-llama-7b'
```

Candidate, quarantined, retired, tampered, incomplete, or subsequently changed
bundles are refused. The ordinary local-agent launcher never reads this registry
and cannot automatically switch to PowerInfer.

WSL2 localhost forwarding *can* make a Linux `./server` reachable from Windows,
but then you have two CUDA stacks and a Linux binary the proxy was not written
against. Use WSL2 only if the native `sm_120` build cannot compile.

**CMake/CUDA combo (RTX 5080 / Blackwell):**

```text
Visual Studio 2022 developer environment (the CUDA-supported host compiler) + Ninja
CUDA Toolkit 12.8 or newer (nvcc on PATH in a VS x64 developer PowerShell)
-DLLAMA_CUBLAS=ON
-DCMAKE_CUDA_ARCHITECTURES=120
```

`120` is documented for CUDA 12.8+ (`sm_120`). CUDA 12.8 does **not** support
Visual Studio 2026 as its host compiler; install Visual Studio 2022's C++
workload side-by-side. If configure fails, you are on
an older toolkit; do not silently drop the arch flag and ship an empty GPU
index.

## Parameterized targets

| `-ModelId` | Route | `intermediate_size` | tokenizer |
|---|---|---|---|
| `relu-llama-7b` | supported sparse PoC | 11008 | `--vocabtype` default SPM |
| `llama31-8b-abliterated-relu` | research | **14336** | **`--vocabtype bpe`** |
| `turbosparse-mistral-instruct` | gated Bamboo/ReLU candidate | **14336** | checkpoint ChatML |

Same dump/train/convert/quantize/package/bench scripts. Llama-3.1 must already
be ReLU/ReGLU (`hidden_act: relu`). Abliterated SiLU weights fail `relu-gate`.
ReLUfication is continued training (ProSparse), not a Safetensors convert.

TurboSparse is deliberately stricter: it accepts a local immutable source only,
requires reviewed local Bamboo code, and refuses dump/train work unless both the
supplied pair JSONL and the source's `abliteration_manifest.json` prove that the
edit was rebuilt from at least 32 approved contrastive pairs. The current
`...turbosparse-mistral-abliterated-projected-20260830b` directory has only
eight synthetic pairs, so it is evidence of loader/math behavior—not an input
to predictor generation.

## Commands

The runner enters the **VS 2022 x64 developer environment** itself; use ordinary
PowerShell:

```powershell
cd A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09

# Print the plan only (no clone, download, or GPU)
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage show

# Proof of concept — GPU stages need an idle 5080 (ComfyUI stopped)
.\tools\powerinfer\run_pipeline.ps1 -ModelId relu-llama-7b -Stage all -Execute -VramBudget 12

# Llama-3.1-8B after you have a ReLU checkpoint
.\tools\powerinfer\run_pipeline.ps1 -ModelId llama31-8b-abliterated-relu `
  -SourceDir D:\PowerInferModels\llama31-8b-relu `
  -Stage all -Execute -VramBudget 12
```

`-Stage` may be `setup`, `intake`, `relu-gate`, `calib`, `dump`, `train`,
`convert`, `quantize`, `package`, `validate`, or `bench`. `validate` runs
`main.exe` and records solver/split flags. `bench` is the acceptance gate:
cold and warm 20-turn latency, tokens/sec, host RAM, VRAM, and SHA-256 of the
GGUF, predictor tree, and `activation/` files →
`<bundle>/validation/acceptance_gate_<timestamp>.json`.

Default vault: `D:\PowerInferModels\<model-id>\<build-id>\` (falls back to
`artifacts/powerinfer_vault`). Existing bundles are not overwritten unless
`-Force`.

## Encrypted vault (outside the repo)

```powershell
py -3 tools\powerinfer\init_vault.py --vault D:\PowerInferModels init
py -3 tools\powerinfer\init_vault.py --vault D:\PowerInferModels preflight --model-id relu-llama-7b
py -3 tools\powerinfer\init_vault.py --vault D:\PowerInferModels create-bundle --model-id relu-llama-7b --build-id 20260829-poc
py -3 tools\powerinfer\init_vault.py --vault D:\PowerInferModels protect-source --source D:\PowerInferModels\relu-llama-7b\20260829-poc\source
```

Private calibration/result files go through `encrypt` / `decrypt` as AES-256-GCM
envelopes under `private/`. The 32-byte key is DPAPI-wrapped at `keys/vault_key.dpapi`
or supplied as `POWERINFER_VAULT_KEY`. Evidence is never auto-deleted; quarantine
is a manifest status, not `rmtree`. Init refuses a path inside this git tree
unless `--allow-in-repo` (tests only).

## Human quality gate (prepared, not a model launcher)

Mechanical benchmarking does not prove instruction following. Prepare one fixed,
benign review packet without contacting either model:

```powershell
python tools\powerinfer\quality_comparison.py prepare `
  --out D:\PowerInferModels\relu-llama-7b\<build-id>\validation\quality_review_packet.json `
  --candidate-model relu-llama-7b.q4.powerinfer.gguf `
  --baseline-model <current-ollama-model>
```

After the operator has separately approved both model loads and manually filled
the response/score fields, verify the rubric record:

```powershell
python tools\powerinfer\quality_comparison.py verify `
  --packet D:\PowerInferModels\relu-llama-7b\<build-id>\validation\quality_review_packet.json `
  --out D:\PowerInferModels\relu-llama-7b\<build-id>\validation\quality_review_result.json
```

This verifier does not start a server, call an endpoint, or promote the model.
It only confirms that the reviewer completed the fixed cases and that the
candidate met the declared score threshold. A passing result still needs an
explicit registry/promotion decision.

## TurboSparse-Mistral projected abliteration (research, parked)

The 4-bit measurement stall at Transformers `Loading checkpoint shards` 2/4 was
**host-RAM pressure from full-shard `safetensors.torch.load_file`**, not Bamboo
incompatibility, a bitsandbytes/sm_120 hang, FlashAttention scanning, or a wrong
`device_map`. Remediation is the streaming loader:

```text
tools/powerinfer/abliterate_loader.py
tools/powerinfer/abliterate_turbosparse_v2.py
```

**Only this edited checkpoint is usable:**

`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

Do **not** use `...\turbosparse-mistral-abliterated-projected-20260830` (no `b`).
Do **not** write the source snapshot
`...\turbosparse-mistral-instruct-source-20260830`.

Verified on that `20260830b` tree:

- 32/32 `o_proj.weight` residual-stream writers edited
- 32/32 `down_proj.weight` matrices unchanged
- maximum Frobenius-norm relative drift **2.1e-4**
- Bamboo/ReLU reload (`model_type=bamboo`, `hidden_act=relu`) and a bounded
  1-layer forward with finite hidden states `[1, 3, 4096]`

Calibration used eight synthetic pairs (`calibration_pairs.synthetic.jsonl`) —
exploratory smoke data only, not a scientifically identified refusal direction.
**Present tense:** predictors and activations have **not** been rebuilt for
this edited tree; no quality benchmark has been run; no GPU dump, train,
convert, benchmark, or ComfyUI process was started for it. Keep the checkpoint
parked. Predictor regeneration from this exact tree is mandatory before any
future quality claim, and that work must not start until operator-approved
harmful/harmless pairs exist. The required JSONL contract and strict local gate
are in `CALIBRATION_PROTOCOL.md` and
`validate_approved_calibration_pairs.py`. The original `abliterate_turbosparse.py` remains
the pre-fix script and still uses the stalling `from_pretrained` 4-bit path.

### Exact prompt contract and agentic gate

The local TurboSparse tokenizer is the authority. Its verified hash is
`151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`; it
uses checkpoint ChatML, not the generic Mistral `[INST]` wrapper:

```text
<|im_start|>system
SYSTEM<|im_end|>
<|im_start|>user
USER<|im_end|>
<|im_start|>assistant
```

Read-only receipt generation (no model or GPU load):

```powershell
python tools\powerinfer\capture_turbosparse_prompt_contract.py `
  --source A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b `
  --out A:\PowerInferModels\turbosparse-mistral\prompt_contract_<timestamp>.json
```

Before requesting GPU approval, validate the approved pairs, raw source, exact
template, and a fresh output path without loading model weights:

```powershell
python tools\powerinfer\preflight_turbosparse_rebuild.py `
  --source A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-instruct-source-20260830 `
  --pairs A:\PowerInferModels\turbosparse-mistral\approved_pairs.jsonl `
  --output A:\PowerInferModels\turbosparse-mistral\turbosparse-<new-build-id>
```

`preflight_turbosparse_rebuild.py` creates nothing. A `ready_for_explicit_gpu_approval`
result means only that the inputs are structurally traceable; it is not a model
quality or safety approval.

After a new approved-pair edit is profiled, converted, and launched manually on
**loopback only**, the strict two-turn JSON gate can be prepared and captured.
It never starts a backend and never executes a file tool call:

```powershell
python tools\powerinfer\turbosparse_agentic_quality_gate.py prepare `
  --prompt-contract A:\PowerInferModels\turbosparse-mistral\prompt_contract_<timestamp>.json `
  --out A:\PowerInferModels\turbosparse-mistral\quality_gate_prepared.json

python tools\powerinfer\turbosparse_agentic_quality_gate.py capture `
  --packet A:\PowerInferModels\turbosparse-mistral\quality_gate_prepared.json `
  --endpoint http://127.0.0.1:8080 `
  --out A:\PowerInferModels\turbosparse-mistral\quality_gate_result.json
```

The candidate must emit exact JSON tool calls in both turns. Prose, Markdown,
invalid JSON, invented terminal output, or an unsafe/wrong next action fail the
gate. This is necessary evidence but not sufficient for registry promotion.
