# 2026-08-25 — Exact Qwen2.5-VL Caption V4 enforcement

## What changed

- Corrected `local_agent/setup_qwen25_vl_caption.ps1` so its paired-projector
  guard accepts the verified 732,298,784-byte Q8_0 projector. The previous
  arbitrary 1 GB floor incorrectly reported the complete exact pair missing.
- Restricted `local_agent/capabilities.py` and `local_agent/media_tools.py` to
  the exact local Qwen2.5-VL Caption V4 Q4_K_M GGUF plus its version-matched
  Q8_0 `mmproj`. Visual work now either runs through the watcher-owned CUDA
  llama.cpp runtime or waits in the media queue; it cannot silently substitute
  an Ollama vision model.
- Corrected the compatibility reference to describe llama.cpp rather than
  Ollama, and added regression coverage for the exact runtime’s structured
  system/user/image request.
- Corrected the capability status label to say `lazy llama.cpp; not loaded`
  while the watcher-owned runtime is off. It no longer claims an Ollama
  fallback exists.
- Updated the active upgrade index so retrieval does not present the older
  Qwen3-VL tiered-fallback plan as the current vision architecture.
- Replaced stale README model recommendations with the configured abliterated
  14B/8B reasoning pair and the actual guarded desktop-render behavior, so new
  chats do not retrieve obsolete non-abliterated model advice.
- Added mocked watcher regression coverage for lazy runtime ownership and the
  exact-model boundary. The tests cannot load a model or affect a render.
- Added an explicit `verify_qwen25_vl_caption.py` diagnostic for the one
  live-caption check: it refuses ComfyUI ownership, prints only verification
  metadata rather than user media content, and releases the VLM in `finally`.
- Added an optional metadata-only report for the live check so completion can
  be recorded without retaining or displaying a generated caption.
- Fixed lazy-runtime cleanup for the Windows race where llama.cpp exits before
  `taskkill` runs. A stale ownership file is now removed only when its PID is
  confirmed gone; a still-live runtime remains protected for a later retry.
- Updated the private GUI revision to `2026-08-25-exact-qwen-vision-r54` so
  the launcher detects an older running server and refreshes it safely.

## Why

The operator required this exact VLM and projector, with no substitute. The
model files and CUDA runtime were already installed; the incorrect size check
and leftover generic fallback path made that state appear unavailable and risked
misreporting the model used for media analysis.

## Evidence

- Verified base file: 4,684,339,808 bytes.
- Verified matching projector: 732,298,784 bytes.
- `local_agent/setup_qwen25_vl_caption.ps1` reports `Ready` after the corrected
  check without downloading or loading any model.

## Verification

- `python local_agent/test_media_analysis.py` — 20 passed.
- `python local_agent/test_media_gpu_queue.py` — 26 passed.
- `python local_agent/test_vram_arbitration.py` — 5 passed.
- `python local_agent/test_qwen25_setup_script.py` — 1 passed.
- Full local-agent suite — 155 passed.
- `python local_agent/agentic_eval.py` — 5/5 mocked harness checks passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
  — 124/124 valid.

## Live hardware validation

- `python local_agent/verify_qwen25_vl_caption.py <controlled-image> --report
  local_agent/runtime/benchmarks/qwen25_vl_caption_live_2026-08-25.json`
  confirmed the exact model through `llama.cpp` at `127.0.0.1:11436`.
- The generated result was non-empty (334 characters). Its metadata-only SHA-256
  is `f14e1cf6f6759257f8f7c5e4cd1c1c5537e76521502ac2debab9202bf8dd6c9a`.
  The diagnostic released the CUDA VLM afterward; no caption content was added
  to the report.
