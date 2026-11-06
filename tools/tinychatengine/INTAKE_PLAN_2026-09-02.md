# TinyChatEngine intake plan — research + staged evaluation, 2026-09-02

## What this is, and what it isn't

This is a **plan**, following the same gated-intake discipline this project
already uses for PowerInfer (`tools/powerinfer/README.md`,
`work/POWERINFER_STATUS_2026-08-30.md`): hash-pinned sources, no GPU load
without explicit approval, no registration into the local agent without a
passed quality gate, evidence preserved either way. **No stage below has been
executed.** No clone, no build, no download, no GPU use.

This is Phase 1 / Task 2 work (engine architecture evaluation), not Phase 2.
It does not touch context/memory optimization, which stays blocked per
`TODO.md`'s Phase 1 gate.

## Disambiguation (carried over from prior research, restated so this doc
stands alone)

"TinyEngine" (`mit-han-lab/tinyengine`) is a **microcontroller-only**
library — MCUNet family, benchmarked on an STM32H743 with 512 KB peak
memory. It has no GPU/desktop path and is explicitly out of scope; this plan
is for **`mit-han-lab/TinyChatEngine`**, a separate project from the same
lab that actually targets x86/ARM/CUDA desktop and edge inference.
TinyChatEngine's own README lists TinyEngine as a "related project," which
confirms the two are siblings, not the same codebase.

## Research findings (read directly from the upstream README, 2026-09-02)

- **License: MIT.** No model-specific license entanglement at the engine
  level (individual models retain their own licenses, same caveat as any
  other engine).
- **Architecture:** pure from-scratch C/C++ (79% C++, 10% CUDA, 8% Python
  tooling for model download/conversion only). No llama.cpp/GGML dependency.
  Compression via SmoothQuant and AWQ (Activation-aware Weight
  Quantization) — MLSys 2024 Best Paper.
- **No HTTP server.** It ships a CLI chat binary (`./chat <model> <precision>
  [threads]`) and a separate VLM CLI (`./vila`). There is **no
  OpenAI-compatible or any other HTTP API**, unlike Ollama or the
  `local_agent/powerinfer_openai_proxy.py` bridge already built for
  PowerInfer. Integrating this engine into the local agent's router would
  require writing an equivalent proxy/wrapper — this is real, non-trivial
  work, not a config change.
- **CUDA backend is real but narrow.** Released 2023/10 for "Nvidia GPUs with
  compute capability >= 6.1, both server and edge GPUs." Precision support
  table shows **Nvidia GPU column only has W4A16** (int4 weight, fp16
  activation) — no FP32, no W8A8, no W4A8 on GPU (those are CPU/ARM-only
  rows).
- **Model zoo CUDA coverage is materially behind what the CPU/ARM backends
  support, and behind current agent usage:**
  - CUDA backend **exists** (int4 AWQ) for: `LLaMA2_13B_chat`,
    `LLaMA2_7B_chat`, `LLaMA_7B`, `CodeLLaMA_13B_Instruct`,
    `CodeLLaMA_7B_Instruct`.
  - CUDA backend is **absent** for: `LLaMA_3_8B_Instruct`,
    `Mistral_7B_v0.2_Instruct`, both VILA/LLaVA VLMs, StarCoder, and the OPT
    family — those rows show x86/ARM checkmarks only, no CUDA checkmark.
  - Net effect: the model families this engine can actually run **on the
    RTX 5080** are Llama-2-generation and CodeLlama, not Llama-3, not
    Mistral. That is older than the currently-routed Ollama models. Getting
    a competitive model onto the GPU path would mean converting/quantizing
    a newer checkpoint through TinyChatEngine's own AWQ pipeline — undocumented
    for architectures the zoo doesn't already cover, and unproven here.
  - VLM (VILA/LLaVA) inference is CPU/ARM only per this table — no CUDA path
    for vision at all.
- **Windows CUDA build is marked "Experimental"** by the project itself, and
  requires manually editing the `Makefile`'s `-arch=sm_xx` line for the
  target GPU. **The RTX 5080 is Blackwell (`sm_120`)** — the same
  architecture that required a fresh CUDA 12.8 + `sm_120` build for
  PowerInfer in this repo, documented as new/fragile territory even for that
  project. TinyChatEngine's CUDA kernels were released in 2023 against
  older architectures; **compatibility with `sm_120` is unverified by
  upstream and unverified here.** This is the single largest technical risk
  in this plan.
- **Project activity:** MIT license, no tagged releases ever published, 35
  open issues / 6 open PRs, most recent visible commit is a README update;
  an open issue exists from November 2025, so the repo isn't abandoned, but
  it is a research-lab project without a release cadence, not a
  production-maintained serving stack like Ollama or vLLM.
- **No batching, no continuous serving, no speculative decoding, no
  multi-request concurrency** documented — this is a single-session
  real-time chat CLI, not a serving engine. That matters for this project's
  actual goal (a responsive interactive agent loop, not batch throughput),
  so it's a plausible fit *if* the CUDA/model-coverage gaps above are
  acceptable — but it is not a drop-in Ollama replacement for anything the
  agent currently does with concurrent/background model calls.

## Comparison against what PowerInfer already proved on this exact host

PowerInfer already demonstrates native `sm_120` CUDA compilation is
*achievable* on this workstation (VS 2022 + CUDA 12.8 + Ninja,
`A:\PowerInferNative`/`A:\PowerInferBuild` short-path pattern) — that
groundwork transfers directly to attempting the same for TinyChatEngine and
lowers the risk of stage 3 below. PowerInfer's own sparse ReluLLaMA-7B
candidate already failed the instruction-quality gate; TinyChatEngine's
best CUDA-eligible model (LLaMA2-7B-chat-int4-AWQ) is a plausible but
unproven quality bar to compare against both PowerInfer's result and the
current Ollama baseline.

## Staged plan — each stage requires the prior stage's evidence before starting

**Stage 0 — done, this document.** Research only; no execution.

**Stage 1 — CPU-only build, no model, no GPU.**
```
git clone --recursive https://github.com/mit-han-lab/TinyChatEngine <pinned-dir>
```
Record the exact commit hash cloned (upstream ships no releases, so a commit
hash is the only pin available — same discipline as PowerInfer's hash-locked
intake). Build the CPU/x86 backend only (`make chat -j` without the CUDA
Makefile edits) to prove the toolchain and dependencies work on this host
before spending any GPU-relevant effort. No model download yet.

**Stage 2 — CPU model smoke test.**
Download the smallest available model (`opt_125m_awq_int4` or
`opt_1.3B_awq_int4` — both x86-backed, tiny, fast to fetch and quantize) and
run one bounded, scripted chat exchange on CPU only. Purpose: prove the
binary actually loads a quantized model and produces coherent-looking text
before committing to a larger download or any GPU work. Preserve the
transcript as evidence, same pattern as PowerInfer's acceptance-gate JSON.

**Stage 3 — GPU/CUDA build, explicit approval required before this stage.**
This is the risk stage: edit the Makefile's `-arch=sm_120` (or the CMake
equivalent, following the same reasoning as
`tools/powerinfer/README.md`'s CMake/CUDA table), build with CUDA 12.8 +
the same VS 2022 developer environment already proven for PowerInfer, and
record whether it compiles at all. If `sm_120` fails, the fallback is
`sm_89` (Ada) compatibility mode if the build system supports forward
compatibility, or the CUDA path is closed out as not viable on this GPU —
either outcome is useful evidence and should be written down, not silently
dropped.

**Stage 4 — GPU model selection and download.**
Only after Stage 3 proves the binary runs on this GPU: download one
CUDA-eligible int4 AWQ model from the table above. `LLaMA2_7B_chat_awq_int4`
is the most directly comparable to existing local-agent usage (chat-tuned,
7B class). Record SHA-256 of the downloaded/converted weights, same as
every other model intake in this repo.

**Stage 5 — bounded acceptance gate.**
Mirror `tools/powerinfer/run_pipeline.ps1 -Stage bench`'s pattern: a fixed
number of cold + warm turns, latency, tokens/sec, VRAM, host RAM, recorded
to a timestamped JSON. Endpoint is not left running afterward. No agent
routing change.

**Stage 6 — human quality comparison.**
Reuse `tools/powerinfer/quality_comparison.py`'s prepare/verify pattern (it's
already generic — model-agnostic) against the current Ollama baseline model
on a fixed benign packet. This is the same gate ReluLLaMA-7B failed
(9/10 cases) — TinyChatEngine's candidate must clear a comparable bar before
being considered for anything beyond diagnostic evidence.

**Stage 7 — registry decision.**
Only with a passed Stage 6 result does this become a real candidate for
`local_agent` routing, which would additionally require building an
HTTP-proxy wrapper (no equivalent to `powerinfer_openai_proxy.py` exists yet
for this engine — that is new work, not a config point) before any wiring
into the router. No stage before this authorizes touching `agent.py`,
`router.py`, or the model picker.

## Open questions for operator decision before Stage 1 starts

1. Is the CUDA model-coverage gap (no Llama-3, no Mistral on GPU — only
   Llama-2/CodeLlama int4) acceptable to spend GPU build effort on, given
   PowerInfer already showed a comparable-generation sparse model
   (ReluLLaMA-7B) failed the quality gate?
2. Is it worth the Stage 3 `sm_120` compatibility risk at all before Stage 1
   (CPU-only, cheap, no GPU) has been run and produced a coherent smoke-test
   transcript? Recommendation: yes to Stage 1 as a cheap first look, hold
   Stage 3 for a separate explicit go-ahead regardless of Stage 1's outcome,
   consistent with this project's GPU-gateway-approval pattern.
3. Building the missing HTTP-proxy wrapper (Stage 7) is comparable in scope
   to what `powerinfer_openai_proxy.py` already took to build for PowerInfer
   — worth flagging now so it isn't a surprise if TinyChatEngine clears the
   quality gate later.

## Evidence and safety discipline carried over from PowerInfer's intake

- No writes outside a dedicated vault/scratch directory; no overwrite of any
  existing PowerInfer, Ollama, or agent state.
- No GPU stage runs while ComfyUI or another render owns the backend port,
  same as every other GPU rule in this repo.
- Every stage's output is preserved as timestamped evidence, never
  overwritten, never auto-promoted to production without an explicit human
  decision.
