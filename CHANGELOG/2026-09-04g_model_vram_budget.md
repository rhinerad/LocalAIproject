# 2026-09-04g — DeepSeek-R1-Distill-Qwen-14B VRAM budget math

## Scope

Math-only sizing check for the dynamic-model-routing plan (`TODO.md`,
2026-09-04): does DeepSeek-R1-Distill-Qwen-14B actually fit the RTX 5080's
16GB, at what quant/context, and how does it compare to 8B/32B
alternatives. No model pulled, no engine started, nothing applied to a live
config.

## What was written

`MODEL_VRAM_BUDGET.md` (project root). Method: real published bartowski
GGUF weight sizes (not formula estimates — quant overhead varies enough by
scheme to matter), plus the standard GQA KV-cache formula verified against
each model family's actual layer count (14B=48 layers, 8B=32 layers,
32B=64 layers — the 32B is not just "bigger," its KV cache costs 33% more
per token than the 14B at matched context, which matters for why it fails).

**Result:** Q4_K_M @ `num_ctx=8192` recommended — 8.99GB weights + 1.5GB
FP16 KV + 1.25GB OS reserve = 11.74GB, 4.3GB headroom. Q8_0 fails outright
(15.7GB weights alone leave no room for KV cache at any context). Max
context in pure VRAM at Q4_K_M/FP16-KV is ~31.5k tokens, ~126k tokens if
quantized KV cache is used (though not recommended by default — quality
cost, and not needed given 8k-16k is the realistic reasoning-chain range).

32B alternative (DeepSeek-R1-Distill-Qwen-32B): fails at every practical
quant/context combination checked — even Q3_K_S (14.4GB, the smallest
commonly-published quant) is already 16.65GB at a bare 4k context with the
OS reserve included, before considering the unaccounted compute buffer or
anything else sharing the GPU. 8B alternative (DeepSeek-R1-Distill-Llama-8B):
fits with large headroom (7.17GB @ 8k, ~8.8GB free) — real tradeoff is
reasoning depth vs. the 14B/32B, not VRAM fit.

Cooperation with the `keep_alive:0` swap mechanism noted explicitly: this
budget assumes exactly one resident 14B at a time, matching
`context_compactor.py`'s existing pattern of explicit `num_gpu` options —
the swap logic must wait for flush confirmation before loading the next
model, since loading a second 14B before the first is confirmed unloaded
would blow the budget regardless of quant.

## What was not done

No model downloaded, no Ollama config changed, no `num_ctx`/quant applied
anywhere live. This is the sizing reference for whoever implements the
dynamic-routing tickets already in `TODO.md`, not an implementation.
