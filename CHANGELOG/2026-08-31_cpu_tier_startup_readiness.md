# 2026-08-31 — CPU-tier startup readiness

## Problem

When ComfyUI owned the GPU, the local agent correctly selected its CPU route,
but a just-started CPU-only Ollama server on `127.0.0.1:11435` could be reported
as down. Ollama 0.32 first opens the loopback listener and then hydrates its
local model-list cache; the initial `/api/tags` request on this workstation took
slightly more than the launcher's previous three-second probe.

## Fix

`local_agent/START_LOCAL_AGENT_GUI.ps1` now allows 12 seconds for an initial
`/api/tags` response and retains its CPU-only startup probe for up to 42 seconds.
The check only reads the local Ollama catalogue: it does not load a model,
contact the network, or touch GPU VRAM.

## Verified state

The CPU-only Ollama listener is now available at `127.0.0.1:11435`, exposes the
configured `huihui_ai/qwen3-abliterated:8b` fallback, and the local-agent status
endpoint reports `cpu_server_up: true` while port 8188 remains reserved for the
existing ComfyUI process.

No ComfyUI/render process was stopped or started, no model was loaded for this
verification, and no evidence or media was altered.
