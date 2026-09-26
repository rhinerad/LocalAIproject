# 2026-08-29 — PowerInfer control-plane evaluation scaffold

## What changed

- Added `local_agent/powerinfer_openai_proxy.py`: a dependency-free, loopback-only OpenAI-style `/v1/chat/completions` and `/v1/models` adapter for a separately running local PowerInfer `server` process. It translates text-only Llama-2-family chat messages to PowerInfer `/completion`, supports normal and SSE replies, bounds requests, and refuses non-loopback binds, unsupported roles, and unavailable backends safely.
- Added `local_agent/test_powerinfer_openai_proxy.py` for offline rendering, alternation, completion-cap, and loopback-bind refusal coverage.
- Added `docs/POWERINFER_CONTROL_PLANE_PLAN_2026-08-29.md` and a tracked opt-in evaluation section in `TODO.md`.

## Deliberate non-changes

- Did not clone, build, download, convert, launch, or route PowerInfer.
- Did not alter Ollama, the local-agent launcher, the GPU gateway, ComfyUI, media/VLM paths, the worker farm, remote access, or phone permissions.
- PowerInfer's sparse acceleration is not assumed for arbitrary existing GGUF or Qwen/Ollama models. A real model/profiler/benchmark acceptance remains required.

## Evidence

- Upstream source verified on 2026-08-29: its CUDA build uses `-DLLAMA_CUBLAS=ON`; sparse PowerInfer GGUF requires matching predictor and activation assets, while llama.cpp-compatible weights have no sparse performance gain. See the upstream README and server documentation linked in the plan.
- `python -m unittest test_powerinfer_openai_proxy -v` passed 4/4 and
  `python -m py_compile powerinfer_openai_proxy.py` passed. Live PowerInfer
  server/API/model benchmarking is intentionally still unverified.
- Updated the Claude-ready continuation note with the same unlaunched
  PowerInfer boundary and acceptance prerequisite.
