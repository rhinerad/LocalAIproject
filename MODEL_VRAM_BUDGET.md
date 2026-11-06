# Model VRAM budget — DeepSeek-R1-Distill-Qwen-14B on RTX 5080 (16GB)

Written 2026-09-04. Math only — no model pulled, no engine started, no
`num_ctx`/quant setting applied to any live config by this doc. Feeds the
dynamic-model-routing decision recorded in `TODO.md` (2026-09-04) and the
`keep_alive: 0` swap mechanism already used by `context_compactor.py`.

**2026-09-05 addendum (this file, below):** every GPU-resident routing
model now has a 95%-of-VRAM-fit `num_ctx` derived from *this machine's*
deployed GGUF blobs and `/api/show` architecture, wired into
`router.Decision.options()`. The 2026-09-04 DeepSeek-14B recommendation
(`Q4_K_M` @ 8192 with comfortable headroom) is historical; it is not the
live ceiling any more.

## Method and sources

Weight footprints below are **real published GGUF file sizes**
(bartowski's quantizations), not formula estimates — quantization overhead
per block varies enough between quant schemes that a bits-per-weight
formula alone would be off by several percent.

KV cache sizes are computed from the standard GQA formula, verified against
each model family's actual public config (not assumed uniform across
sizes — the 14B and 32B Qwen-family distills do **not** share the same
layer count, which matters a lot below):

```
KV bytes/token = 2 (K and V) × num_layers × num_kv_heads × head_dim × bytes_per_element
```

| Model | Base arch | Layers | KV heads | Head dim | FP16 KV bytes/token |
|---|---|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-**14B** | Qwen2.5-14B | 48 | 8 | 128 | 196,608 B (192 KiB) |
| DeepSeek-R1-Distill-Llama-**8B** | Llama-3.1-8B | 32 | 8 | 128 | 131,072 B (128 KiB) |
| DeepSeek-R1-Distill-Qwen-**32B** | Qwen2.5-32B | 64 | 8 | 128 | 262,144 B (256 KiB) |

Q8 KV cache halves the FP16 bytes/token figure; Q4 KV cache quarters it.

**OS/CUDA runtime reserve:** using the requested 1.0–1.5GB convention
(1.25GB used in the tables below as a working middle value) rather than
this machine's own measured GPU-idle baseline (56–87 MiB, seen repeatedly
in this project's own changelog entries with nothing loaded) — the idle
figure undercounts what's actually available once Windows' desktop
compositor, multiple monitors, and whatever else is open are accounted for,
so the more conservative published convention is the safer number to
design against, not the best-case idle reading.

**Not included below, flagged as an added safety margin to keep in mind:**
llama.cpp/Ollama also allocate a compute/graph buffer beyond weights + KV
(typically a few hundred MB, scaling loosely with context and batch size).
The tables below do not subtract it explicitly; treat the "headroom"
column as the real margin for that buffer plus anything else running.

## Step 1 — VRAM envelope, DeepSeek-R1-Distill-Qwen-14B (target model)

**Weights (bartowski GGUF, published sizes):**

| Quant | Weight size |
|---|---|
| Q4_K_M | 8.99 GB |
| Q5_K_M | 10.5 GB |
| Q8_0 | 15.7 GB |

**KV cache at 192 KiB/token (FP16), by context length:**

| Context | FP16 KV | Q8 KV | Q4 KV |
|---|---|---|---|
| 4,096 | 0.75 GB | 0.375 GB | 0.19 GB |
| 8,192 | 1.5 GB | 0.75 GB | 0.375 GB |
| 16,384 | 3.0 GB | 1.5 GB | 0.75 GB |

**Total VRAM (weights + KV + 1.25GB OS/CUDA reserve), 16GB budget:**

| Quant | @4k (FP16 KV) | @8k (FP16 KV) | @16k (FP16 KV) |
|---|---|---|---|
| Q4_K_M | 10.99 GB (**5.0 GB headroom**) | 11.74 GB (**4.3 GB headroom**) | 13.24 GB (**2.8 GB headroom**) |
| Q5_K_M | 12.5 GB (**3.5 GB headroom**) | 13.25 GB (**2.75 GB headroom**) | 14.75 GB (**1.25 GB headroom, tight**) |
| Q8_0 | 17.7 GB (**OOM — 1.7 GB over budget, even at 4k**) | doesn't fit | doesn't fit |

**Q8_0 fails the 16GB check outright.** 15.7GB of weights alone leaves only
~0.3GB after the OS reserve, before a single token of KV cache — this
quant is not viable on this card for this model without CPU layer
offloading, at any context length.

## Threshold check — maximum context in pure VRAM, zero CPU offload

Using 14.75GB usable (16GB − 1.25GB OS/CUDA reserve) as the ceiling, solved
for `remaining_after_weights / KV_bytes_per_token`:

| Quant | VRAM left for KV after weights | Max context, FP16 KV | Max context, Q8 KV | Max context, Q4 KV |
|---|---|---|---|---|
| Q4_K_M | 5.76 GB | **~31,500 tokens** | **~63,000 tokens** | **~126,000 tokens** (approaches the model's own ~131k trained ceiling — becomes model-limited, not VRAM-limited, at this point) |
| Q5_K_M | 4.25 GB | **~23,200 tokens** | **~46,400 tokens** | **~92,800 tokens** |
| Q8_0 | negative | 0 (doesn't fit) | 0 (doesn't fit) | 0 (doesn't fit) |

**Q4_K_M with FP16 KV comfortably covers any realistic Chain-of-Thought
reasoning length this project would use** (8k–16k) with multiple GB of
headroom to spare — quantized KV cache isn't even necessary at the context
lengths this harness actually needs, and is worth keeping in reserve as a
lever rather than using by default (quantized KV cache costs some
generation quality, not free).

## Step 2 — comparison against 8B and 32B alternatives

**8B (DeepSeek-R1-Distill-Llama-8B), Q4_K_M = 4.92GB weights, 128 KiB/token KV:**

| Context | FP16 KV | Total (incl. 1.25GB OS) | Headroom |
|---|---|---|---|
| 8,192 | 1.0 GB | 7.17 GB | **8.83 GB free** |
| 16,384 | 2.0 GB | 8.17 GB | **7.83 GB free** |

Enormous headroom — this card could run the 8B at Q8_0 (weights ~8.5GB
estimated by the same scaling bartowski's 14B/32B figures imply) with
plenty of room left for a large context, or run it alongside something
else entirely. The tradeoff is reasoning depth, not fitting: the 8B distill
is a smaller base model, and DeepSeek's own published benchmarks show a
real reasoning-quality gap versus the 14B and 32B distills on math/coding
chain-of-thought tasks — this is a capability tradeoff, not a VRAM one, so
sizing math alone doesn't settle whether 8B is "enough."

**32B (DeepSeek-R1-Distill-Qwen-32B), 3-bit quants (bartowski, published):**

| Quant | Weight size |
|---|---|
| Q3_K_S | 14.4 GB |
| Q3_K_M | 15.9 GB |
| Q3_K_L | 17.2 GB |

64 layers (not 48) means KV cache costs **33% more per token** than the
14B at the same context (256 KiB/token vs 192 KiB/token):

| Quant | Weights | + KV @ 4k FP16 (1.0GB) | + 1.25GB OS | Total | Fits 16GB? |
|---|---|---|---|---|---|
| Q3_K_S | 14.4 GB | 15.4 GB | 16.65 GB | **16.65 GB** | **No — over budget even at 4k context** |
| Q3_K_M | 15.9 GB | 16.9 GB | 18.15 GB | **18.15 GB** | **No** |

**Confirmed: the 32B distill does not fit this card at any practical
context length, even at the most aggressive commonly-used 3-bit
quantization, even before considering that 3-bit quantization already
costs meaningful quality versus 4-bit.** This isn't close — Q3_K_S misses
by ~0.65GB at a bare 4k context with zero safety margin; real-world usage
(any larger context, the compute buffer, anything else sharing the GPU)
pushes the gap wider. The 32B "chokes the KV cache" concern named in the
prompt is real, but the bigger problem is even simpler: the weights alone,
at the loosest quant anyone reasonably runs, don't leave room for a usable
context window on a 16GB card.

## Step 3 — recommendation and harness integration

**Recommended: Q4_K_M, `num_ctx` = 8192.**

- 8.99GB weights + 1.5GB FP16 KV cache + 1.25GB OS reserve = **11.74GB**,
  leaving **~4.3GB headroom** — comfortable margin for the unaccounted
  compute/graph buffer, desktop compositor, and anything else briefly
  sharing the GPU, without needing quantized KV cache as a crutch.
- Q5_K_M is viable too (13.25GB @ 8k, 2.75GB headroom) if the quality
  difference from Q4_K_M → Q5_K_M matters more than the extra ~1.5GB of
  margin — a real judgment call, not a math one, and not this doc's call
  to make unilaterally.
- 16k context is reachable on Q4_K_M (13.24GB, 2.8GB headroom) if a
  reasoning chain genuinely needs it, without falling back to quantized KV.

**Ollama flags to lock 100% GPU, zero CPU offload:**

- `num_gpu` set high enough to cover every layer (Ollama's own
  auto-detection already does full-GPU offload when VRAM allows; setting
  it explicitly, e.g. `num_gpu: -1` / all layers, removes ambiguity and
  documents the intent rather than relying on auto-detection silently
  doing the right thing).
- `num_ctx: 8192` per the recommendation above.
- Do **not** set `low_vram` / partial-offload flags — this budget is sized
  specifically so none are needed.
- This mirrors the existing pattern in `context_compactor.py`, which
  already sets explicit `options={"num_gpu": 0, ...}` for its CPU-only
  calls — the GPU-resident reasoning model needs the same explicitness in
  the opposite direction (`num_gpu` forced on, not off).

**Cooperating with the `keep_alive: 0` swap mechanism:** because only one
14B needs to be resident at a time (per the dynamic-routing design), this
budget doesn't need to share VRAM with the Coder model — the flush-then-load
sequence means each model gets this full envelope to itself while it's the
active one. The harness's swap logic should wait for the flush
confirmation (the `keep_alive:0` call completing, model actually unloaded)
before issuing the load call for the next model — loading a second 14B
before the first is confirmed flushed would exceed this budget immediately
regardless of quant choice, since the numbers above assume exactly one
resident 14B, not two overlapping during a transition.

## Verification summary

- **Base model VRAM (Q4_K_M):** 8.99 GB
- **KV cache VRAM @ 8k context (FP16):** 1.5 GB
- **OS/CUDA reserve:** 1.25 GB
- **Total: 11.74 GB**
- **16GB safety check: PASSES, with 4.26 GB headroom.**
- Q8_0 fails the check outright (doesn't fit even at 4k, before KV cache).
- The 32B distill fails the check at every practical quant/context
  combination tested. The 8B distill passes with very large headroom to
  spare, at the cost of reasoning depth rather than VRAM fit.

---

# Addendum 2026-09-05 — all GPU-lineup models, 95% VRAM ceilings

Live on this machine (RTX 5080, nvidia-smi **16303 MiB**). Each GPU-resident
model is assumed **alone on the card** (same exclusivity as `gpu_busy()` /
timeshare — no concurrent ComfyUI reservation). Ceilings are wired into
`router.Decision.options()` via `GPU_VRAM_NUM_CTX`. **Routing is unchanged:**
`decide()` still picks the same tags; only `num_ctx` moved.

This addendum uses the 2026-09-04 method above, with two tightenings the
original tables left implicit:

1. Weight sizes are the **deployed GGUF blobs** (`ollama show` → `FROM`
   sha256 on disk), not bartowski published class sizes.
2. The compute/graph buffer the 2026-09-04 tables parked in "headroom" is
   **folded in explicitly**, because the live ceiling is 95% of max-fit,
   not a comfortable 8k.

Quantized KV is **not** used. Every dense model below fits a usable FP16
window. Heretic is the exception: the Q4_K_M blob already collides with
the 1.25 GiB leftover, so shrinking KV (quantized or shorter) cannot buy
a tool-sized window.

## Envelope

| Quantity | Value | Source |
|---|---|---|
| Card | **16303 MiB** = 17,094,934,528 B | `nvidia-smi` 2026-09-05, RTX 5080 |
| OS/CUDA leftover | **1.25 GiB** = 1,342,177,280 B = 1280 MiB | same convention as 2026-09-04 |
| Usable after leftover | **15023 MiB** = 15,752,757,248 B | 16303 − 1280 |
| KV dtype | FP16 (`bytes_per_element = 2`) | 2026-09-04 conclusion: quantized KV not needed at project lengths |
| Tightness | floor(95% of max VRAM-fit ctx), then `min(that, native context_length)` | operator |
| Concurrency | one model | timeshare exclusivity |

GiB = 1024³, MiB = 1024². Matching the 2026-09-04 tables (those ~31,500
token figures only reproduce if GB means GiB).

## KV formula (per model, not per family)

```
KV bytes/token (FP16) = 2 × num_layers × num_kv_heads × head_dim × 2
```

Architecture from `POST /api/show` `model_info` on the **installed** tags.
`head_dim` is `attention.key_length` when present; otherwise
`embedding_length / attention.head_count`. Qwen3-14B is **40** layers, not
the 48 of Qwen2.5-14B — same class of mistake the 2026-09-04 doc caught
between 14B and 32B Qwen2.5.

| Tag | Arch | Layers | KV heads | Head dim | Native ctx | FP16 KV B/token |
|---|---|---|---|---|---|---|
| `huihui_ai/qwen3-abliterated:14b` | qwen3 | 40 | 8 | 128 | 40960 | 163,840 (160 KiB) |
| `huihui_ai/qwen3-abliterated:8b` | qwen3 | 36 | 8 | 128 | 40960 | 147,456 (144 KiB) |
| `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M` | qwen2 | 48 | 8 | 128 | 131072 | 196,608 (192 KiB) |
| `deepseek-r1-abliterated-14b:r1-tools` | same blob as DeepSeek | 48 | 8 | 128 | 131072 | 196,608 |
| `josiefied-qwen2.5-coder-14b:q4_k_m` | qwen2 | 48 | 8 | 128 | 32768 | 196,608 (192 KiB) |
| `josiefied-qwen2.5-coder-14b:official-tools` | same blob as Josiefied | 48 | 8 | 128 | 32768 | 196,608 |
| `qwen2.5-coder:14b` (coding-pin fallback) | qwen2 | 48 | 8 | 128 | 32768 | 196,608 |
| `gpt-oss-20b-heretic:latest` | gpt-oss MoE | 24 (12 full attn + 12 SWA-128) | 8 | 64 | 131072 | 24,576 full-attn + 3.00 MiB SWA fixed |

gpt-oss even layers are sliding-window 128, odd layers dense. llama.cpp
accounts for that: published KV @ 8192 is 0.2 GB = 24.4 KiB/token, which
matches `2 × 12 × 8 × 64 × 2 = 24,576`, not a naive 24-layer 48 KiB/token.

Qwen2 metadata does not ship `key_length`; 5120/40 = 128, matching the
2026-09-04 Qwen2.5-14B row.

## Deployed GGUF sizes (this disk, not a size class)

`ollama show` `FROM` blobs under `A:\Users\rhine\.ollama\models\blobs\`.

| Tag | Blob sha256 prefix | Bytes | GiB | Quant |
|---|---|---|---|---|
| qwen3-14b | `25bb9ad6…` | 9,001,748,832 | 8.383532 | Q4_K_M |
| qwen3-8b | `6da140c1…` | 5,027,779,392 | 4.682484 | Q4_K_M |
| DeepSeek-14b and r1-tools | `38b5e200…` | 8,988,110,400 | 8.370830 | Q4_K_M |
| Josiefied and official-tools | `d5e3ff3e…` | 8,988,114,880 | 8.370834 | Q4_K_M |
| stock `qwen2.5-coder:14b` | `ac9bc7a6…` | 8,988,110,784 | 8.370830 | Q4_K_M |
| gpt-oss-20b-heretic | `81b61c92…` | 15,853,797,344 | 14.764999 | Q4_K_M |

## Explicit compute/graph margin

2026-09-04: "typically a few hundred MB, scaling loosely with context and
batch size. The tables below do not subtract it explicitly; treat the
headroom column as the real margin."

This addendum measures that term on this card's Ollama (flash-attn path)
with the primary 14B at two `num_ctx` values, GPU otherwise idle
(76 → 73 MiB):

| num_ctx | nvidia-smi used | ollama `/api/ps` size |
|---|---|---|
| 2048 | 8958 MiB | 9,034,279,157 B |
| 8192 | 10064 MiB | 10,194,014,699 B |

Delta 6144 tokens → **1,159,735,542 B** ollama size (smi delta 1106 MiB =
1,159,725,056 B, same to 0.001%).

```
all-in bytes/token = 1,159,735,542 / 6144 = 188,759.04
GQA FP16 for Qwen3-14B = 163,840
scale = 188,759.04 / 163,840 = 1.152094
```

So llama.cpp/Ollama's context-scaling overhead on this card is **15.21%
on top of formula KV** (compute/graph workspace, not a second copy of
weights). Fixed intercept is ~0 once GGUF weights are used as the base —
the 2048 point sits 25 MiB *under* `weights + formula KV + idle`, the
8192 point 123 MiB over; the linear fit through the delta is the honest
graph term.

Dense GQA models below use:

```
effective_B/token = GQA_FP16_B/token × 1.152094
max_ctx = (card − 1.25 GiB − GGUF_bytes) / effective_B/token
ceiling  = min(floor(0.95 × max_ctx), native_context_length)
```

A fixed 512 MiB graph addend would **under**-cover at the 30k-token
region this math actually lands in (15.21% × 30k × 160 KiB ≈ 0.7 GiB),
which is why the measured *scale* is used instead of a round lump.

## Per-model math

### 1. `huihui_ai/qwen3-abliterated:14b` — PRIMARY_REASONING_MODEL

Was `num_ctx=20480`.

```
room = 15,752,757,248 − 9,001,748,832 = 6,751,008,416 B (6438.26 MiB)
eff  = 163,840 × 1.152094 = 188,759.04 B/token
max  = 6,751,008,416 / 188,759.04 = 35,765.22
95%  = 33,976.96
native = 40,960  → ceiling 33,976  (VRAM-limited)
```

Previous 20480 was ~57% of VRAM-max, not 95%.

### 2. `huihui_ai/qwen3-abliterated:8b` — FALLBACK_REASONING_MODEL

Was `num_ctx=32768`.

```
room = 15,752,757,248 − 5,027,779,392 = 10,724,977,856 B (10228.14 MiB)
eff  = 147,456 × 1.152094 = 169,883.14 B/token
max  = 63,131.50
95%  = 59,974.93
native = 40,960  → ceiling 40,960  (model-limited, not VRAM-limited)
```

The card could hold ~63k FP16 tokens; the model only trains to 40,960.

### 3. `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M` — DEEPSEEK_MODEL

Was `CAPABILITY_GPU_NUM_CTX=8192`. Same 48-layer Qwen2.5-14B KV as the
2026-09-04 doc (192 KiB/token), but the *live* GGUF is 8.370830 GiB, not
bartowski's 8.99 GB class figure.

```
room = 15,752,757,248 − 8,988,110,400 = 6,764,646,848 B (6451.27 MiB)
eff  = 196,608 × 1.152094 = 226,510.85 B/token
max  = 29,864.56
95%  = 28,371.33
native = 131,072  → ceiling 28,371  (VRAM-limited)
```

`deepseek-r1-abliterated-14b:r1-tools` reuses blob `38b5e200…` → **same
ceiling**. Not a `decide()` default (retag was not promoted).

### 4. `josiefied-qwen2.5-coder-14b:q4_k_m` — JOSIEFIED_CODER_MODEL / CODING_MODEL

Was 8192. Identical 48/8/128 GQA; blob 4,480 B larger than DeepSeek.

```
room = 15,752,757,248 − 8,988,114,880 = 6,764,642,368 B
max  = 29,864.54
95%  = 28,371.31
native = 32,768  → ceiling 28,371  (VRAM-limited)
```

`josiefied-qwen2.5-coder-14b:official-tools` reuses blob `d5e3ff3e…` →
**same ceiling**. Stock `qwen2.5-coder:14b` (blob `ac9bc7a6…`, 8,988,110,784 B,
native 32768) is not in `GPU_MODELS` but `is_coding_model()` will pin it
to this same 28,371 if someone selects it on the GPU tier.

### 5. `gpt-oss-20b-heretic` — GPU_ONLY_OPT_IN

Was 8192.

Paper envelope **does not close**:

```
15,752,757,248 − 15,853,797,344 = −101,040,096 B (−96.36 MiB)
```

Weights + 1.25 GiB leftover already oversubscribe the card before one
token of KV. Quantized KV cannot fix a weights-vs-leftover gap, so it is
not used.

Live load 2026-09-05, `num_ctx=2048`, `num_gpu=99`: nvidia-smi peaked at
**15028 MiB used / 950 MiB free** (15220 / 758 at the last generate
slice). Ollama then dropped the resident (`keep_alive=10m` did not stick
— the card is already at the leftover line). Hybrid FP16 KV at 2048 is
only 48 MiB, so almost all of 15028 is weights + MoE compute.

Calibrate max ctx from that live footprint, still requiring
`used ≤ 16303 − 1280 = 15023 MiB`:

```
non-KV = 15028 − 48 = 14,980 MiB
KV room = 15023 − 14980 = 43 MiB
max    = 43 MiB / 24,576 B/token = 1,834.67
95%    = 1,742.93  → ceiling 1,742
native = 131,072   → 1,742 (VRAM-limited; leftover-limited)
```

**Caveat:** native tool schemas + operating policy are ~10k tokens. 1742
cannot carry a tool-capable turn. That is a true hardware result for this
quant on this card under the 1.25 GiB leftover, not a missed lever.
Previous 8192 already spent the leftover (and more). Heretic remains
opt-in / GPU-only; this change does not auto-route to it.

## Summary — live `num_ctx` vs previous hardcodes

| Model | Role | Previous | New ceiling | Binding limit |
|---|---|---|---|---|
| `huihui_ai/qwen3-abliterated:14b` | primary reasoning | 20480 | **33976** | VRAM 95% |
| `huihui_ai/qwen3-abliterated:8b` | GPU fallback | 32768 | **40960** | native 40960 |
| DeepSeek-14B Q4_K_M (+ r1-tools blob) | CAP_LOGIC | 8192 | **28371** | VRAM 95% |
| Josiefied-14B Q4_K_M (+ official-tools blob) | CAP_CODE | 8192 | **28371** | VRAM 95% |
| `gpt-oss-20b-heretic` | GPU-only opt-in | 8192 | **1742** | leftover + 95% |
| Farm / Qwythos | Mac, not 5080 | 8192 | **8192** (unchanged) | not this math |

`PRIMARY_SAFE_PROMPT_TOKENS` stays 16000 — that is a *routing* tripwire
onto the 8B, not a context ceiling.

## GPU_MODELS tags not installed on this machine

No live GGUF → no ceiling invented from a size class:

`equal-shares-gpu`, `equal-shares`, `huihui_ai/qwen3.6-abliterated:27b`,
`huihui_ai/qwen2.5-coder-abliterate:32b`, `huihui_ai/qwen2.5-abliterate:32b`,
`huihui_ai/qwen2.5-abliterate:14b`, `huihui_ai/qwen2.5-coder-abliterate:14b`,
`huihui_ai/qwen2.5-coder-abliterate:7b` (CPU list / coding fallback).

If `decide()` ever selected one, `Decision.options()` would still fall
through to `GPU_OPTIONS["num_ctx"]=16384`. That number is **not** a VRAM
proof. The 2026-09-04 32B row already shows a 32B does not fit this card.

PowerInfer is not an Ollama GPU resident (`backend=powerinfer`). Qwythos
is farm. Qwen3-VL / MiniCPM vision paths are sensory tools, not this
conversation-tier table.

## Live cross-check (primary 14B at the new ceiling)

2026-09-05, GPU otherwise idle (71 MiB). Generate
`huihui_ai/qwen3-abliterated:14b` with `num_gpu=99`, `num_ctx=33976`,
`num_predict=4`, `keep_alive=6m`. `ollama show` still reports Q4_K_M,
40,960 native context, 14.8B.

| | Predicted (GGUF + scaled KV) | Measured |
|---|---|---|
| nvidia-smi used | ~14,777 MiB | **13986 MiB** |
| nvidia-smi free | ~1,526 MiB | **1992 MiB** |
| `/api/ps` size_vram | — | 14,309,927,157 B (13,647 MiB) |
| `/api/ps` context_length | 33976 | **33976** |

Measured used is **791 MiB under** the linear 2048→8192 extrapolation.
Flash-attn graph does not keep the 15.21% tax all the way to 34k, so the
paper ceiling is conservative, not optimistic. Free 1992 MiB still clears
the 1280 MiB leftover. `done=true`, `done_reason=length` (4 tokens), no
OOM, no CPU offload (`size_vram` equals `size`).

