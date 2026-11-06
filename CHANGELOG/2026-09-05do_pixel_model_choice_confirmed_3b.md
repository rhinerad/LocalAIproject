# 2026-09-05do — Pixel edge model confirmed: staying with SmallThinker-3B

## Scope

Operator tracking entry.

## Context

Operator proposed three larger candidates for the Pixel edge worker
(mradermacher/abliterated-llama-8b-GGUF, bartowski/Qwen2.5-Coder-7B-
Instruct-abliterated-GGUF, mlabonne/NeuralDaredevil-8B-abliterated).
Flagged the real tradeoff: Pixel 10 Pro has 16GB RAM; an 8B Q4 GGUF
weighs ~4.5-5GB before KV cache/Android overhead — plausible but a real
step up in OOM/thermal risk for what would be the very first real
on-device edge-worker test.

## Operator decision

Stick with the original plan: `huihui-ai/SmallThinker-3B-Preview-
abliterated` for the first bounded, battery/thermal-observed Pixel
test (TODO.md ~line 846). The larger candidates can be considered for a
follow-up test once the pipeline itself is proven at low risk.

## Status

Dispatching Pink to fetch this model and continue toward the real G10
`--once` run, alongside the pending Termux hash verification.
