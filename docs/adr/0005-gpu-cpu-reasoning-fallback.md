# ADR 0005 — GPU/CPU reasoning fallback without layer offload

**Status:** Accepted

## Decision

When the GPU is free, use the configured Huihui 14B reasoning model and its 8B
fallback fully on GPU. When ComfyUI owns the GPU, route general chat to the
dedicated CPU 8B service instead. Do not use CPU layer-offload for a GPU model.

## Why

Layer-offload causes unpredictable latency and can compete with the media and
render workloads the GPU must protect. A deterministic tier boundary makes
resource use visible and recoverable.

## Consequences

- Context above the configured threshold and recoverable 14B failures can route
  to 8B.
- GPU-tier model state is evicted when a render claims ownership.
- Performance claims require the pending matched 14B benchmark.

## Evidence

`local_agent/router.py`, `local_agent/agent.py`, launcher documentation, and
the GPU-yield/fallback test suite.
