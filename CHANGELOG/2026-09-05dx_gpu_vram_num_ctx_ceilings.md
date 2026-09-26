# 2026-09-05dx — GPU `num_ctx` ceilings from this card's VRAM math

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dx**.

`router.Decision.options()` no longer uses round-number `num_ctx`
hardcodes (8192 / 20480 / 32768 / `CAPABILITY_GPU_NUM_CTX`). Every
GPU-resident routing model now gets 95% of the maximum FP16-KV context
that actually fits this RTX 5080 (16303 MiB) with the model **alone** on
the GPU, capped at the model's native context. Math:
`MODEL_VRAM_BUDGET.md` addendum 2026-09-05.

**Routing is unchanged.** `decide()` still picks the same tags. Farm /
Qwythos still uses `CAPABILITY_GPU_NUM_CTX=8192` (Mac, not this card).
`PRIMARY_SAFE_PROMPT_TOKENS` stays 16000.

## Method (same as 2026-09-04, two tightenings)

1. Deployed GGUF bytes from `ollama show` → `FROM` blob on this disk.
2. Per-model GQA: `2 × layers × kv_heads × head_dim × 2` from `/api/show`
   `model_info` (Qwen3-14B is 40 layers, not Qwen2.5-14B's 48).
3. 1.25 GiB OS/CUDA leftover, same convention.
4. Compute/graph buffer made explicit: measured 15.21% on top of formula
   KV from a 2048→8192 delta on the primary 14B (`/api/ps` size
   +1,159,735,542 B over 6144 tokens).

## Per-model table

| Tag | Role | Previous | New | Binding |
|---|---|---|---|---|
| `huihui_ai/qwen3-abliterated:14b` | primary | 20480 | **33976** | VRAM 95% |
| `huihui_ai/qwen3-abliterated:8b` | GPU fallback | 32768 | **40960** | native 40960 |
| DeepSeek-14B Q4_K_M | CAP_LOGIC | 8192 | **28371** | VRAM 95% |
| Josiefied-14B Q4_K_M | CAP_CODE | 8192 | **28371** | VRAM 95% |
| r1-tools / official-tools retags | same blobs | 8192 if pinned | **28371** | same |
| `gpt-oss-20b-heretic` | GPU-only opt-in | 8192 | **1742** | leftover + 95% |
| Farm Qwythos | Mac | 8192 | **8192** | not this math |

Heretic Q4_K_M GGUF is 15,853,797,344 B. Paper envelope (weights +
1.25 GiB leftover) is already 96 MiB over the card before KV. Live at
`num_ctx=2048`: 15028 MiB used / 950 MiB free; Ollama would not keep it
resident. Quantized KV cannot close a weights gap. 1742 is the VRAM-legal
ceiling; it is smaller than the ~10k-token tool catalog — a hardware
result, not a missed lever.

Uninstalled `GPU_MODELS` tags (32B, 27B, equal-shares, Huihui 14B Qwen2.5,
coding 7B) have no live GGUF; no size-class guess. Unknown GPU tags still
fall through to `GPU_OPTIONS` 16384, which is **not** a VRAM proof.

## Live cross-check

Primary 14B at the new ceiling, GPU otherwise idle (71 MiB):

- `ollama show huihui_ai/qwen3-abliterated:14b` → qwen3, Q4_K_M, native
  40960, 14.8B
- generate `num_gpu=99` `num_ctx=33976` `num_predict=4`: `done=true`,
  `done_reason=length`, load 59.2 s
- nvidia-smi: **13986 MiB used / 1992 MiB free** of 16303
- `/api/ps`: `context_length=33976`, `size_vram=14309927157` (fully GPU)

Paper prediction was ~14777 MiB used. Measured is 791 MiB under (flash-attn
graph tax shrinks at 34k vs the 8k delta). Free 1992 ≥ 1280 leftover. No
OOM. Unloaded with `keep_alive:0` after the sample.

## Code

- `local_agent/router.py`: `GPU_VRAM_NUM_CTX` + `gpu_vram_num_ctx()`;
  `Decision.options()` uses the table on the GPU tier.
- Tests: `test_gpu_vram_num_ctx.py` (routing tags unchanged, farm still
  8192); `test_capability_routing.py` / `test_router_switching.py`
  expected `num_ctx` updated.
- 84 tests OK:
  `python -m unittest test_gpu_vram_num_ctx test_capability_routing test_router_switching test_ollama_context_options`
