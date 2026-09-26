# Local-agent CPU/GPU handoff hardened — 2026-08-22

## What changed

- `local_agent/router.py` now queries Ollama's `/api/ps` endpoint and unloads
  every model actually resident on the GPU server when routing to CPU.
- An empty GPU server no longer receives a pointless unload request.
- `local_agent/test_router_switching.py` covers automatic GPU → CPU → GPU
  switching, resident vision-model eviction, CPU thread/GPU limits, an empty
  GPU server, and refusal of forced GPU use while busy.
- The native-tool regression suite now compares schema count to the live tool
  registry instead of the obsolete literal 22; the registry currently contains
  24 tools after the batch-render actions were added.

## Why

The previous eviction chose from `/api/tags`, which lists installed models, not
resident ones. It could target the preferred text model while a different model
(such as vision) actually held VRAM.

## Safety preserved

- Routing is still evaluated before every operator reply.
- Any queue owner, port 8188 listener, excessive VRAM use, foreign compute
  process, or unknown NVIDIA state forces CPU.
- CPU remains `num_gpu: 0`, four threads.
- A manual GPU preference still cannot override a busy signal.
- No model or dependency was downloaded and no render/backend was stopped.

## Verification

- `python local_agent\test_router_switching.py`: **3/3 passed**, including the
  GPU → CPU → GPU sequence and exact resident-model eviction.
- `python local_agent\test_native_tool_calling.py`: **8/8 passed**.
- `python local_agent\test_media_analysis.py`: **4/4 passed**.
- `python local_agent\validate_h3_prompt.py --dir
  outputs\equal_shares\prompts_native_r2v`: **124/124 valid**.
- After reloading the app, live `/api/status` selected **CPU**, `qwen3:8b`,
  `127.0.0.1:11435` because ComfyUI was listening on 8188.
- Live GPU Ollama `/api/ps` returned no resident models after the yield; NVIDIA
  measured **29 C, 0% utilization, 432 MB**.

The idle return path was tested with deterministic mocks so the live ComfyUI
backend was not disturbed.

## Still unverified

A live GPU generation was deliberately not started while ComfyUI owned port
8188. The deterministic test exercises the identical routing and host-selection
code without violating GPU ownership.
