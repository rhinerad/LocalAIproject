# 2026-08-24 — Qwen2.5-VL Caption V4 local vision runtime

## What changed

- Replaced the local agent's preferred visual-analysis and dense video-action
  model with the explicitly permitted
  `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF` Q4_K_M release.
- Added explicit local model/projector paths for
  `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf` and its matching
  `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf`.
- Added `local_agent/Modelfile.qwen25-vl-nsfw-caption` and opt-in
  `local_agent/setup_qwen25_vl_caption.ps1`; normal agent startup never
  downloads or initializes either model.
- Changed visual inference to send a Qwen2.5-VL-compatible system/user chat
  turn with structured image input to the loopback-only CUDA llama.cpp server,
  leaving native image-token expansion to the model template rather than
  injecting tokens into user text.
- Replaced the action-extraction path that selected the 32B model (and could
  CPU-offload) with the same 7B Qwen2.5-VL import, requiring 8 GB free VRAM plus
  the existing 1 GB safety reserve.
- Recorded the optional `starsfriday/Qwen-Image-NSFW` checkpoint as a lazy,
  non-startup diffusion capability only. It is not used for captioning,
  image/video analysis, or any render path.
- Changed video-analysis intermediates from MJPEG to lossless PNG and leaves a
  0.25-second tail decode margin, fixing non-full-range-YUV encoding failures
  and container-duration overshoot on short MP4s.
- Repaired the launcher so its CPU-only Ollama child receives its environment
  through the process environment. CPU Whisper-tiny can run while the VLM owns
  the GPU, but it stays queued during an actual ComfyUI/render owner.

## Why

The requested V3 Q4_K_M GGUF plus matching f16 projector loaded fully on the
GPU, but a live text-only and image inference test each returned literal
question-mark output. V4 was expressly permitted by the user and is now the
primary. V3 files remain untouched as evidence. The previous dense-action path
also selected a 32B model that could spill layers to CPU; it now uses this 7B
Qwen2.5-VL import only.

## Evidence

The working paired download is approximately 5.33 GB (4.68 GB + 0.70 GB).
The V4 f16 projector was also tested, but produces invalid visual output;
the repository's version-matched Q8_0 projector gives grounded image results
and is therefore the configured companion. Current
Ollama rejects this caption GGUF without llama.cpp compatibility patches, so
the launcher explicitly supplies both paths to CUDA llama.cpp at
`127.0.0.1:11436`. The download script never runs at ordinary startup and leaves
a failed zero-byte transfer untouched rather than overwriting evidence.

## Verified after

Passed after this session's static/import regression suite:

- `python local_agent\\test_media_analysis.py` — 12/12
- `python local_agent\\test_media_gpu_queue.py` — 15/15
- `python local_agent\\test_native_tool_calling.py` — 10/10
- `python local_agent\\validate_h3_prompt.py --dir outputs\\equal_shares\\prompts_native_r2v` — 124/124

## Live verification

- Downloaded V4 Q4_K_M plus matching Q8_0 projector into the configured local
  directory; the V3 files and failed V4 f16 test files were kept unchanged.
- CUDA llama.cpp loaded both configured V4 files, reported vision/video support,
  and stayed private at `127.0.0.1:11436`.
- A real image call returned a grounded detailed description of two people,
  their indoor setting, objects, composition, and visible action. The Q8_0
  projector is not an alternate model: it is the same repository's matching
  projector quantization.
- A live per-second video call extracted lossless frames and returned separate
  visual states and pairwise motion comparisons for 0, 1, and 2 seconds of a
  9.417-second uploaded video, plus the existing audio measurement boundary.
- This is a local-agent-only change; it did not start or modify a MiniMax render.
- The refreshed GUI reports revision `2026-08-24-qwen25-vl-caption-v4-r18`, a
  live CPU model server, and the GPU VLM runtime; the router correctly selects
  CPU while the VLM occupies the card.
