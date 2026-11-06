# 2026-08-29 — Native Windows PowerInfer conversion pipeline

## What changed

- Added `tools/powerinfer/`: parameterized runner for `prosparse-7b` (supported
  sparse PoC) and `llama31-8b-abliterated-relu` (research route, `f=14336`,
  `--vocabtype bpe`). Same dump/train/convert/quantize/package/bench scripts.
- Orchestrator is `tools/powerinfer/run_pipeline.ps1`. GPU, download, and
  CMake stages require `-Execute`. Default bind remains native
  `127.0.0.1:8080` so `local_agent/powerinfer_openai_proxy.py` does not need
  WSL2 port forwarding.
- Native CUDA combo: Visual Studio 17 2022 x64, `-DLLAMA_CUBLAS=ON`,
  `CMAKE_CUDA_ARCHITECTURES=120`, CUDA Toolkit 12.8+ (Blackwell `sm_120`).
- `bench` writes `validation/acceptance_gate.json`: cold and warm 20-turn
  latency, tokens/sec, host RAM, VRAM, solver/split log flags, and SHA-256 of
  the GGUF, predictor tree, and `activation/` files. Prompt text is not stored.
- Offline tests: `python -m unittest test_powerinfer_pipeline -v` from
  `local_agent/` — 8/8 passed. `py_compile` of the pipeline modules passed.
  `-Stage show` ran for both model IDs. No clone, download, CUDA build, profile,
  convert, or GPU load was performed.

## Deliberate non-changes

- Did not clone PowerInfer, download weights, start `server.exe`, or wire the
  OpenAI proxy into the launcher/picker.
- Did not ReLUfy any Llama-3.1 checkpoint. SiLU abliterated weights still fail
  `relu-gate` by design.
- Did not switch the control plane to WSL2.

## Evidence boundary

Live RTX 5080 CMake/`sm_120` compile, FFN split, and 20-turn numbers remain
unverified until `-Execute` is run on an idle GPU with a ReLU source.
