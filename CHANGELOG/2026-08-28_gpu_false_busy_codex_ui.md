# 2026-08-28 — Correct false GPU-busy state from Codex desktop

## Fault

The router treated the Codex/ChatGPT desktop executable's small WDDM display
context as a foreign GPU compute process. With no ComfyUI listener, no render
owner, no resident Ollama model, 81 MB VRAM used, and 0% utilization, that still
forced the agent to CPU-only routing.

## Fix

- Classified `ChatGPT.exe` / Codex desktop alongside browser/Electron display
  contexts, which are already non-blocking telemetry on Windows WDDM.
- Preserved all real blockers: live queue ownership, port 8188, unknown GPU
  telemetry, high unowned VRAM, Python/ComfyUI compute processes, and all
  gateway permission controls.

## Verification

- Added regression coverage for the exact Codex UI process path and for a real
  foreign Python compute process.
- No model was loaded, evicted, or rendered while diagnosing or fixing this.

## Activation

The desktop launcher's revision is now `2026-08-28-gpu-idle-r63`, so it replaces
an earlier local-agent server and imports this router revision. This restart
only targets the loopback local-agent listener; it does not touch ComfyUI.
