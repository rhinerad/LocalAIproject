# 2026-08-29 — PowerInfer native CUDA build verified

## Result

- Visual Studio 2022 Build Tools with the C++ workload is now installed.
- The upstream PowerInfer source compiled successfully with CUDA 12.8, cuBLAS,
  Ninja, and `CMAKE_CUDA_ARCHITECTURES=120` for the RTX 5080.
- Verified local binaries: `main.exe`, `server.exe`, and `quantize.exe` in
  `A:\PowerInferBuild\bin`.

## Windows path-length correction

The initial supported VS 2022 compilation failed only because an optional
converter target inherited the repository's deep path. No source, evidence, or
old build cache was changed or removed. The controlled build now uses:

- source junction: `A:\PowerInferNative` → canonical `external\PowerInfer`
- build output: `A:\PowerInferBuild`

`tools/powerinfer/run_pipeline.ps1` now creates/uses the short source junction
only when absent, refuses to replace a non-junction path, invokes the VS 2022
developer environment, and builds with VS-bundled Ninja.

## Safety state

No candidate model, predictor, activation asset, server, GPU inference, or
render was started. The next gate remains an explicit, separately authorized
download and verification of a supported sparse model with its matching assets.

## 2026-08-30 staging update

- Downloaded the configured supported sparse PoC, `SparseLLM/ReluLLaMA-7B`,
  into the external vault at
  `A:\PowerInferModels\relu-llama-7b\relu-llama-7b-source-20260829\source\hf`.
  The recorded source-tree combined SHA-256 is
  `6bb8db502f6bec097eb7b67490edef5ec63bd4e57cd6b87cf31e6ebc4a514155`.
- The strict ReLU gate passed: `hidden_act=relu`, `model_type=llama`,
  `hidden_size=4096`, `intermediate_size=11008`, and 32 layers.
- Created a public, non-private 8,000-record C4 calibration manifest. Its JSONL
  SHA-256 is `b8e285b6972c7fd64026c37596c84b1a388a90625ec78fc79030f03d357aa6f4`.
- No model weights have been loaded, no profiling/dump has run, and no native
  server or inference process has been started. The next stage (`dump`) is the
  first GPU model load and remains an explicit operator approval boundary.

## 2026-08-30 controlled activation dump completed

- After explicit operator approval, only the loaded Ollama Qwen3.8 model was
  released. ComfyUI and all render processes remained untouched.
- The controlled `--load-4bit` dump completed with 400,000 samples for every
  one of 32 layers. Recorded activation-tree combined SHA-256:
  `a4d5a90f2b5cce2149250950ae12a74c00fa14816b08f86addb24c6486b518`.
- Per-layer mean sparsity ranges from approximately 0.776 to 0.880. The dump
  released its GPU memory cleanly: 15.9 GB was free afterward.
- Its predictor-data input is complete: 64 memory maps (x and label for each
  layer), approximately 360.11 GiB, with no missing expected files.
- The initial dump attempt failed before loading weights due to missing
  `protobuf` and `tiktoken`. Both are now explicit runner dependencies and the
  isolated environment’s tokenizer check passes.
