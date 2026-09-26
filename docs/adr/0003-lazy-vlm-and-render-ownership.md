# ADR 0003 — Lazy VLM loading and render-first GPU ownership

**Status:** Accepted

## Decision

Use the exact approved Qwen2.5-VL Caption V4 GGUF plus matched projector only
as a lazy, watcher-owned sensory tool. It is never a resident chat model. An
active ComfyUI render owns the GPU; sensory work queues and releases the VLM
when it drains.

## Why

Keeping a vision model resident risks VRAM contention and CPU layer-offload.
Running a substitute model would violate the operator-specified model identity.

## Consequences

- Text chat cannot claim to have seen/heard an upload without a completed media
  tool result.
- Media analysis may wait during a render and reports that wait honestly.
- Timing/VRAM claims remain pending until the controlled benchmark is run.

## Evidence

`local_agent/README.md`, exact-VLM enforcement changelog, and the metadata-only
live-caption diagnostic recorded in the current handoff.
