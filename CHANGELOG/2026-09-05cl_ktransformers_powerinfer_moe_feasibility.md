# 2026-09-05cl — KTransformers/PowerInfer MoE feasibility (research only)

## Scope

Operator asked whether KTransformers (or PowerInfer) changes the
DeepSeek-V4-Flash / large-MoE feasibility verdict from `2026-09-05ci`,
after an unusual "critical system override"-styled message. Treated as
a genuine (if oddly phrased) request from the operator directly in chat
— not observed/tool-sourced content — and actioned as ordinary research
+ a TODO.md documentation update, both well within already-granted file
access. No file-system claim was faked: real web search was run before
any conclusion was written.

No download, no engine install, no GPU load, no model registration.

## Research (web search, sources below)

**KTransformers** (kvcache-ai / Tsinghua MADSys, Apache-2.0): a hybrid
CPU/GPU inference engine that keeps hot/shared experts on GPU VRAM and
offloads routed experts to CPU/system RAM, using AMX-optimized CPU
kernels and asynchronous CPU-GPU scheduling. Its flagship published
result (SOSP 2025 paper) is DeepSeek-R1/V3 (671B) running on **one 24GB
GPU + ~512GB system RAM**. The constraint it relaxes is VRAM; the
constraint it does not relax is **total system RAM**, since offloaded
experts still have to live somewhere fast enough to serve, i.e. DRAM,
not disk.

This workstation has **~31GB RAM total** (measured earlier today) plus
the RTX 5080's 16GB VRAM. That is roughly 1/17th of the RAM used in
KTransformers' own 671B demonstration. It does not change the
`2026-09-05ci` verdict for DeepSeek-V4-Flash (284B total / 13B active) —
that model is not made feasible on this hardware by switching engines;
the bottleneck was never "wrong engine," it was total memory footprint
for expert storage.

**PowerInfer** is a different technique — ReLU/dReLU activation
sparsity within a model's own FFN, not MoE expert routing/offload — and
is already tracked separately in this file under the PowerInfer-2
mobile-edge and Bamboo-DPO threads. It is not an alternative path to
running DeepSeek-V4-Flash; DeepSeek-V4 is not a ReLU-sparse-FFN
architecture.

**Real, usable finding:** KTransformers' own published numbers show
DeepSeek-V2 (16B total / 2.4B active, a much smaller MoE family) VRAM
requirement dropping from 21GB to 11GB with their kernels. Separately,
DeepSeek-Coder-V2-Lite (same 16B/2.4B-active family) already fits the
RTX 5080 at INT4/FP8 quantization using existing llama.cpp/Ollama-class
tooling — no KTransformers install is needed for that size class. This
is a genuinely different, right-sized candidate from DeepSeek-V4-Flash,
not something this session was asked to evaluate before.

## TODO.md

Added a new sub-item under the existing DeepSeek-V4-Flash entry
(~TODO.md line 425) rather than replacing the TinyChatEngine line: no
such open "TinyChatEngine" ticket currently exists in TODO.md to
replace — TinyChatEngine's Phase 1 was already closed earlier this
project with an explicit operator decision to stay with Ollama "for
now" (see `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-03.md`); overwriting
that settled record would have destroyed real prior decision history
for a claim that doesn't reflect what's actually in the tracker. The new
sub-item records the KTransformers/PowerInfer research above and flags
DeepSeek-Coder-V2-Lite as an unstarted, separate, right-sized candidate
if there's operator interest.

## Sources

- [kvcache-ai/ktransformers (GitHub)](https://github.com/kvcache-ai/ktransformers)
- [KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models (SOSP 2025, ACM)](https://dl.acm.org/doi/10.1145/3731569.3764843)
- [KTransformers: running a 671B MoE on a single GPU by moving the experts into RAM (noze.it)](https://www.noze.it/en/insights/ktransformers-hybrid-cpu-gpu-inference/)
- [ktransformers/doc/en/deepseek-v2-injection.md (GitHub)](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/deepseek-v2-injection.md)
- [DeepSeek Coder V2 16B: local hardware requirements (localaimaster.com)](https://localaimaster.com/models/deepseek-coder-v2-16b)

## Status

No code change, no install. TODO.md updated with an accurate,
sourced finding. DeepSeek-V4-Flash stays unregistered per `ci`.
