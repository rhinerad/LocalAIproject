# 2026-09-05bm — Qwen3.8-27B abliterated GPU eval (no routing change)

Date: 2026-09-05. Host: DuranGamingPC (RTX 5080 16303 MiB). Id from
`python scripts/next_changelog_id.py`: **2026-09-05bm**.

Eval only. `router.py` was not changed. No new Ollama pull.

Harness: `artifacts/benchmarks/2026-09-05_qwen38_27b_eval.py`
Receipts: `artifacts/benchmarks/2026-09-05_qwen38_27b_eval/*.json`

## Tag / quant on disk

`ollama list` already had **`huihui_ai/Qwen3.8-abliterated:latest`**
(digest `bdc5e13cd164`, 17 GB, modified 6 days ago). No pull.

| Field | Value |
|---|---|
| Architecture | `qwen35` (Ollama) / GGUF name `Huihui Qwen3.8 27B Abliterated` |
| Parameters | 27.32 B / 27.3B |
| Quant | **Q4_K_M** |
| Native ctx | 262144 |
| Weights blob | `sha256-6c2c13cef89238c3604d756b07b3ef5fafebbd61095feb8553ff449c95e4c1c6` **16031.9 MB** (byte-identical to `Qwen3.8-27B-Uncensored-GGUF\Qwen3.8-27B-Uncensored-Q4_K_M.gguf`) |
| Projector blob | `sha256-c9a090…` **888.0 MB** CLIP mmproj |
| Renderer / parser | `RENDERER qwen3.8` / `PARSER qwen3.5` / `TEMPLATE {{ .Prompt }}` |
| Capabilities | completion, vision, tools, thinking |
| Layers | 64 repeating + output; log: **offloaded 66/66 to GPU** at 2k ctx |

Hybrid layout (upstream, matches this GGUF): 16 × (3 × Gated DeltaNet→FFN + 1 × gated attention→FFN) = **48 linear-attention + 16 full-attention**. Only the 16 full-attention layers grow a sequence KV cache; GDN keeps a fixed recurrent state (`ssm_d_state=128`, `ssm_n_group=16` in the load log). That is why long context is cheap *in KV*, not why the **16 GB Q4_K_M weights** fit a 16 GB card.

Other quants exist in `Qwen3.8-27B-Uncensored-GGUF\` (IQ4_XS, Q3_K_M, …) but are **not** Ollama tags. Not imported this pass.

## llama.cpp #27623 baseline (dated 2026-09-05)

| Item | Record |
|---|---|
| Installed Ollama | **0.32.15** (`A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe`) |
| Pin file on v0.32.15 | `LLAMA_CPP_VERSION` = **`b10488`** |
| Live runner `--version` | `llama-server.exe` **0.1.2-dev (build 1, commit 9d77fa172)** |
| CUDA dir used | `lib\ollama\cuda_v13` |
| Issue | [ggml-org/llama.cpp#27623](https://github.com/ggml-org/llama.cpp/issues/27623) opened 2026-08-23 |
| Status today | **Still Open.** No comments, no linked fix PR. Reproduced by the reporter on **b10488** (same nightly Ollama 0.32.15 pins) and master `8144f31`. Cliff: ~33 t/s @ 68K → **1.4 t/s @ 91K**; pp stays ~1300 t/s. |
| Recheck trigger | Next Ollama bump that moves `LLAMA_CPP_VERSION` **past b10488**. 0.33.0 exists upstream (llama.cpp later, b10760 as of 2026-09-02) — **not installed**, not tested. |

Software ceiling if this tag is ever wired: **64K** (conservative side of the 64–80K reporter-safe band). This machine **cannot allocate 64K** with Q4_K_M (below).

## VRAM / speed (real Ollama timings)

GPU idle at start: **68–70 MiB**, 31 °C, `/api/ps` empty, :8188 down.

| Phase | num_ctx | prompt_eval_count (actual) | load_duration | pp tok/s | decode tok/s | nvidia-smi after |
|---|---|---|---|---|---|---|
| Idle load + short | 2048 | 19 | **111.903 s** | 20.8 (warmup) | **14.568** (4 tok) | **15933 / 16303 MiB** |
| ~20K requested fill | 20480 | **9375** (tokenizer denser than 3.4 c/tok) | **140.824 s** (reload) | **68.489** | **8.258** (4 tok) | **68 MiB** (evicted after) |
| 64K alloc, short prompt | 65536 | — | llama-server **`-c 65536`** then **exit 0xffffffff** @ 139 s | — | — | 68 MiB |

Load log at 2k: `CUDA0 model buffer size = 15339.44 MiB` + `CUDA_Host 682.03 MiB`; 66/66 layers on GPU. nvidia-smi **15933 MiB** leaves ~370 MiB free — the card is full of weights before a long KV even starts.

Ollama later logged `model predicted to exceed available memory` at `predicted_num_ctx=20480` while `available="0 B"`. 64K start line: `llama-server.exe … -c 65536` then `Load failed … NTSTATUS 0xffffffff`.

Reply at 2k and 9.4k fill was exactly `KV_CACHE_OK`.

**Do not treat 14.6 t/s as a 14B-class number.** This is a 27B Q4_K_M packed into 16 GB; decode already dropped to 8.3 t/s at 9.4k filled tokens. The #27623 80K cliff was not reachable: 64K would not load.

## Tool-calling (full GPU schema, 68 tools)

Same prompts as 2026-09-05b/n. Direct GPU `:11434`, `think=False`, `tools.schemas(include_project=True, profile="gpu")` — **68** functions (67 plus `comfy_job_status`).

| Case | Hop 0 native `tool_calls` | Inner executed | Hop 1 |
|---|---|---|---|
| `read_file` heading | **`read_file`** `{path: local_agent/README.md, limit: "40"}` | yes; file starts `# Local Agent — a local ChatGPT Desktop equivalent` | **500** `no user query found in messages` (0.06 s) |
| `run_code` clamp loop | **`run_code`** with the **buggy** `min(lo, max(x, hi))` + asserts | yes; AssertionError in sandbox | **500** after 97 s; `llama-server … terminated … 0xffffffff` |

Not DeepSeek catalog-drowning: hop 0 picked the right tool from 68 schemas, empty `content`, native `tool_calls` ids (`call_73rkqk8m`, `call_7peqs855`). Extra `limit` (schema is `max_chars`) was ignored by `read_file` and still returned the file. `run_code` omitted `language` (defaults to python) and correctly ran the failing asserts first.

Multi-hop is **not** proven: this tag’s `TEMPLATE {{ .Prompt }}` + `RENDERER qwen3.8` rejected the follow-up tool-result transcript (`no user query found`), and a second hop also crashed the runner (VRAM). Clamp was **not** fixed. Do not claim a complete agent loop.

## Context ceiling vs existing compaction

Already in `agent.py`:

- `_apply_ctx_ceiling(adaptive, ceiling)` = `min(adaptive, GUI ceiling)`
- when `prompt_tokens > num_ctx` → `_trim_context` (farm prefetch at 80% via `compaction_prefetch`, else `context_compactor` CPU `llama3.1:8b`, else continuity digest)

That **is** the generic mechanism. A later wire-in should set this tag’s `Decision.options()["num_ctx"]` the same way Heretic is 8k / capability 8k / primary 20k / fallback 32k — **not** a new summarizer.

Practical cap on this card+quant is **not** 64K. 64K is the #27623 software ceiling *if* a smaller quant ever fits. Today Q4_K_M cannot allocate `-c 65536`. A VRAM-safe `num_ctx` (2k–8k class) would already trigger trim/prefetch.

## Recommendation (still not wired)

Do **not** add `huihui_ai/Qwen3.8-abliterated:latest` to `GPU_MODELS`. Weights fill the 5080 at 2k ctx; 20k is slower and evicts; 64k load crashes. Tool hop 0 is promising; hop 1 is not. Revisit with a smaller local quant (Q3_K_M / IQ4_XS already on disk as GGUF, not an Ollama tag) and/or an Ollama build whose `LLAMA_CPP_VERSION` is past b10488 **and** #27623 is closed.
