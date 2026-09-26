# 2026-09-05ci — DeepSeek-V4-Flash abliterated: what the TODO mismatch actually is

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ci**.

Research only. No download, no engine install, no registration, no GPU
load. Fills the empty “hardware/tooling mismatch” note at TODO.md ~411
and `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`.

## 1. The repo exists

[cebeuq/DeepSeek-V4-Flash-0731-abliterated](https://huggingface.co/cebeuq/DeepSeek-V4-Flash-0731-abliterated)
is a live overlay of `deepseek-ai/DeepSeek-V4-Flash-0731`.

| Field | Card / hub |
|---|---|
| Kind | Abliterated **MoE**, not dense; rank-1 edit on attention `wo_b` only |
| Total params | Card **284B**; hub widget **306B** (likely counting DSpark MTP) |
| Active | **13B** (256 routed experts, **top-6**, + 1 shared) |
| Layers | 43, hidden 4096, hybrid CSA+HCA, mHC `hc_mult=4`, DSpark draft |
| Native ctx | 1,048,576 (they serve 262,144) |
| Precision | Native **FP4 experts + FP8** rest — **not a GGUF** |
| Disk | **~167 GB** (48 shards + 1.54 GB overlay) |
| Documented serve | **vLLM 0.25.2, TP=2, 2× NVIDIA DGX Spark (128 GB each)** |

This is not a 13B dense “Flash” that could sit on a 16 GB card. 13B is
the *activated* subset of a 284B MoE; all experts still have to live on
disk and be pageable.

## 2. This workstation cannot GPU-resident it at any quant

Measured this session (no GPU load): **~30.9 GB RAM** (32 GB class),
RTX 5080 **16 GB**. Combined RAM+VRAM ≈ **47 GB**.

Published weight files:

| Artifact | Size | Fits 16 GB VRAM? | Fits 32 GB RAM + 16 GB VRAM? |
|---|---|---|---|
| cebeuq native FP4+FP8 | ~167 GB | no | no |
| Huihui Q2 GGUF (0731) | **86.7–97.6 GB** | no | no |
| Huihui Q4 / MXFP4 | **153–156 GB** | no | no |
| Unsloth IQ1_S (smallest published family) | **~82.5 GB** | no | no |
| DSpark draft Q8 | 10.9 GB | extra, not standalone | — |

Unsloth’s own memory table for this family is **~110–135 GB** for 3-bit
and **~162 GB** for 4-bit (RAM+VRAM / unified). Validated Q2 recipes use
**128 GB unified** (one DGX Spark), not 16 GB + 32 GB.

**“On C:\\ SSD” is disk placement, not a GPU load.** Same pattern as
`C:\PowerInferVault`. C: had ~788 GB free (2026-09-05bk), so a Q2 file
would *fit on disk*. mmap/CPU-expert-offload from NVMe is a different
plan (option C below) and is not “loaded on the 5080.”

## 3. “tiny engine” is the TinyChatEngine name collision, and it still cannot run this

`tools/tinychatengine/INTAKE_PLAN_2026-09-02.md` already recorded:

- `mit-han-lab/tinyengine` = **MCU-only** (STM32, 512 KB). Wrong target.
- Intended sibling = **`mit-han-lab/TinyChatEngine`**. CUDA zoo is
  **Llama-2 / CodeLlama 7B–13B W4A16**. No DeepSeek, no MoE, no HTTP
  server. Windows CUDA experimental; **sm_120 unverified**.

That is the same mix-up, **plus** a second mismatch: even TinyChatEngine
has no path for a 284B DeepSeek-V4 MoE.

Other engines people actually use for *this* checkpoint:

- **vLLM** (what cebeuq documents) — 2×128 GB Sparks
- **llama.cpp** / **ds4** (`antirez/ds4`) — GGUF, still 87 GB+ working set
- Not PowerInfer: V4 is not a ReLU/dReLU sparse FFN model

## 4. Operator menu (no pick)

Same style as 2026-09-05bk. Do not treat any row as recommended.

| ID | Path | Requires | Cost / risk |
|---|---|---|---|
| **A** | **Skip this candidate.** Leave TODO open-or-wontfix. Keep Huihui-14B / existing GPU lineup. | Nothing | Zero download, zero new engine. Does not satisfy the 09-01 goal. |
| **B** | **Wait for a actually-small variant** (dense 13B or a published expert-pruned build that is << 32 GB). Huihui has talked about 192/224-expert prunes (~63–72 GB) and `0xSero/deepseek-v4-flash-0731-spark` (~60B). | Time; re-research when a file **< ~20 GB** exists | Still may not fit 16 GB VRAM once KV is added. Do not treat “13B active” as a downloadable 13B model. |
| **C** | **GGUF on C: + llama.cpp mmap / RAM+disk expert offload** (Huihui Q2 ~87 GB, not the cebeuq overlay). | ~90 GB C: disk; latest llama.cpp with `deepseek4`; Ollama 0.32.15 is **not** that stack | 32 GB RAM vs 87 GB file → SSD paging. Unsloth budgets assume 100 GB+ memory. Likely unusable tok/s; will contend with ComfyUI/timeshare. New engine, not registered. |
| **D** | **ds4** (`antirez/ds4`) on the same Q2 GGUF. | Windows CUDA build of ds4; same 87 GB+ file | Same memory wall. ds4 single-GPU recipes assume **128 GB** class (Mac / Spark). Extra serving surface. |
| **E** | **Serve cebeuq native on vLLM as documented.** | **2× ~128 GB** unified GPUs, TP=2, vLLM 0.25.2, `flashinfer_b12x` | Not this machine. ~167 GB download. |
| **F** | **TinyChatEngine** for this HF id. | — | **Impossible.** Zoo has no DeepSeek-V4. |
| **G** | **mit-han-lab/tinyengine** (MCU). | — | **Impossible.** Microcontroller library. |
| **H** | **Hosted** (Prem Router / a cloud Spark). | Account, spend, network | No local C: weights; policy/privacy; not in `router.py` without a later ticket. |
| **I** | **Different already-local abliterated model** (Huihui-14B is on GPU Ollama). | None new | Does not run V4-Flash. |

No row is wired. No file was pulled.

## Finding in one sentence

The TODO mismatch is: **a 284B/13B-active MoE (~167 GB native, ~87 GB
smallest GGUF) that the authors serve on 2×128 GB Sparks, aimed at a
32 GB RAM + 16 GB 5080 box, via an engine name that in this repo means
TinyChatEngine (Llama-2 7B/13B) or MCU TinyEngine.** C: can hold the
file; the 5080 cannot hold the model.
