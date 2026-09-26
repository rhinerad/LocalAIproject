# PowerInfer Control-Plane plan — 2026-08-29

## Decision

Evaluate PowerInfer as an **opt-in interactive inference backend** on the Ryzen CPU + RTX 5080 control plane. It is not enabled, installed, downloaded, or routed into the local agent yet.

PowerInfer is a CPU/GPU hybrid engine that keeps frequently activated neurons on GPU and computes the remainder on CPU/RAM. Its sparse performance path requires a PowerInfer GGUF plus matching predictor and activation files; an ordinary llama.cpp-compatible GGUF may run in compatibility mode but does not gain the sparse acceleration. The upstream project currently lists sparse Llama-2, ProSparse Llama-2, Falcon/ReLU, and Bamboo families—not the existing Qwen/Ollama chat models. See the [upstream PowerInfer README](https://github.com/Tiiny-AI/PowerInfer) and [its server API documentation](https://github.com/Tiiny-AI/PowerInfer/blob/main/examples/server/README.md).

Model preparation is a separate mandatory track. See
`docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md`: a PowerInfer-ready
bundle needs model/predictor/activation lineage and acceptance evidence. Do not
assume a normal GGUF, arbitrary abliterated checkpoint, or post-LoRA merge can
be automatically profiled into a sparse PowerInfer model.

**Do not promise 70B “real-time” performance from the 16 GB GPU alone.** A suitable sparse model can shift hot activations to VRAM, but the rest still needs substantial system RAM and CPU/PCIe bandwidth. The operator's reported 32 GB system RAM may be insufficient for a 70B-class quantized model plus runtime and OS headroom. Profile a supported model and record RAM, VRAM, prefill, decode, and first-token latency before changing any production route.

## Local-only API boundary

`local_agent/powerinfer_openai_proxy.py` is a standard-library OpenAI-style adapter. It remains separate from `START_LOCAL_AGENT_GUI.ps1` and binds only to `127.0.0.1:8091` by default:

```text
Interactive Python agent
        │  OpenAI-style /v1/chat/completions
        ▼
PowerInfer OpenAI proxy (127.0.0.1:8091)
        │  PowerInfer /completion
        ▼
PowerInfer server (127.0.0.1:8080)
        │
 RTX 5080 hot neurons + Ryzen DDR5 cold neurons
```

The proxy accepts text-only `system`, `user`, and `assistant` messages and renders the Llama-2-family chat format used by currently supported sparse models. It supports normal and SSE streaming replies, model discovery, optional loopback API-key checking, bounded request/prompt/completion sizes, and prompt caching. It deliberately rejects image content and tools: PowerInfer's existing sparse model support does not establish safe multimodal or native tool-call semantics for this agent.

The existing local-agent GPU permission gateway remains the owner of permission to start/keep a PowerInfer workload. Do not expose this endpoint on Wi-Fi, LoRa, LXMF, LAN, or `0.0.0.0`.

## Allocation strategy

| Workload | Route | Reason |
|---|---|---|
| Real-time general chat, tool planning, difficult interactive coding | Existing Ollama tiers by default; PowerInfer only after a supported sparse model passes benchmarks and GPU approval | Preserve known chat/tool behavior until measured replacement quality exists. |
| Interactive Teacher turns and immediate critique/rewrite | Candidate for PowerInfer after acceptance | Latency-sensitive, human-in-the-loop requests can benefit from a large supported sparse model. |
| Harmon Town / Nothing Forever Stage generation | Candidate for PowerInfer only for text-only real-time stage dialogue after format and safety tests | It needs low response latency, but the Stage must retain its own moderation, pacing, state, and tool boundaries. |
| Judge evaluation, web/PDF/repository processing, embeddings, export distillation, bulk Teacher/Student generation | Celery/Redis worker farm and later cluster queues | Asynchronous, batchable tasks should not reserve the interactive GPU. |
| ComfyUI renders, VLM/video/audio analysis | Existing guarded media/ComfyUI paths | PowerInfer does not replace multimodal runtimes or render workflows. |

The worker farm receives compact encrypted artifact references, not live chat prompts or PowerInfer process control. It may consume completed logs for batch evaluation, but it must never start or stop the PowerInfer server.

## Build prerequisites and Windows commands

Use a Visual Studio **x64 Native Tools** PowerShell after confirming CUDA **12.8+** (Blackwell / RTX 5080), CMake 3.17+, Python 3.8+, Git, and the C++ desktop build tools are installed.

**Native Windows is the intended runtime**, not WSL2. The OpenAI proxy binds `127.0.0.1:8091` in native Python and expects `server.exe` on `127.0.0.1:8080`. WSL2 localhost forwarding can reach a Linux `./server`, but that is a fallback only if the native `sm_120` build cannot compile.

The upstream CUDA flag is `LLAMA_CUBLAS=ON`. For CUDA 12.8+, `CMAKE_CUDA_ARCHITECTURES=120` is the documented Blackwell arch (`sm_120`); pass it explicitly on this workstation.

```powershell
cd A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
.\tools\powerinfer\run_pipeline.ps1 -ModelId prosparse-7b -Stage setup -Execute
# equivalent manual cmake:
# cmake -S external\PowerInfer -B external\PowerInfer\build -G "Visual Studio 17 2022" -A x64 -DLLAMA_CUBLAS=ON -DCMAKE_CUDA_ARCHITECTURES=120
# cmake --build external\PowerInfer\build --config Release --parallel
```

The controlled Windows runner keeps the supported VS 2022/Ninja binary at
`A:\PowerInferBuild\bin\server.exe`, using `A:\PowerInferNative` as a short
junction to the canonical source. This avoids Windows compiler path-length
failures while preserving the source and old build caches. Before launching it,
reserve GPU capacity via the existing gateway and
select an explicit VRAM budget below what the gateway reports as free. Example
only after model verification:

```powershell
A:\PowerInferBuild\bin\server.exe -m D:\PowerInferModels\<verified>.powerinfer.gguf `
  --vram-budget <approved-GiB> -t <Ryzen-CPU-thread-count> -c <verified-context> `
  --host 127.0.0.1 --port 8080 -a powerinfer-local
```

Then, in a separate terminal, start the unlaunched adapter only on loopback:

```powershell
$env:POWERINFER_BACKEND_URL = 'http://127.0.0.1:8080'
$env:POWERINFER_MODEL_ALIAS = 'powerinfer-local'
$env:POWERINFER_PROXY_API_KEY = '<local-secret>'
python local_agent\powerinfer_openai_proxy.py
```

No command above should be run while ComfyUI owns the GPU. The adapter is implemented and tested but is not wired into launchers or routes automatically.

## Model sourcing and conversion

1. Prefer an upstream PowerInfer model repository containing `*.powerinfer.gguf` **and** the sibling `activation/` directory. Preserve that directory layout: PowerInfer generates a `*.generated.gpuidx` index beside the model at first use.
2. For an upstream-supported 70B experiment, use only the matching original sparse model and predictor pair listed by upstream, then convert with:

   ```powershell
   python convert.py --outfile D:\PowerInferModels\<model>.powerinfer.gguf `
     D:\PowerInferModels\<original-sparse-model> D:\PowerInferModels\<predictor>
   ```

3. Record SHA-256 hashes, source repository commit/revision, model license, predictor revision, activation-file inventory, Windows/CUDA/CMake versions, RAM/VRAM, and benchmark results before accepting it.
4. Never convert an arbitrary existing Qwen/Ollama model and label it PowerInfer-ready. The predictor is a required learned component, not a generic conversion option.

## Acceptance gates before routing any agent

- [ ] GPU gateway grant and idle-GPU preflight; ComfyUI/VLM owner absent.
- [ ] Exact sparse model, predictor, activation directory, license, and hashes recorded.
- [ ] Cold and warm 20-turn text chat benchmark: first token, tokens/sec, p50/p95 latency, host RAM, VRAM, and failure behavior.
- [ ] OpenAI adapter contract test against a real PowerInfer server: normal and streamed reply, unauthorized request, oversized request, backend outage.
- [ ] Tool/planner quality evaluation against the existing pinned Ollama model; no automatic model replacement without passing results.
- [ ] Harmon Town Stage format, pacing, state, and safety regression suite.
- [ ] Explicit operator decision before adding a model to the local-agent picker or routing any project traffic to the endpoint.
