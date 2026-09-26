# 2026-08-24 — Video-action queue runtime fix

## What changed

- Restored `router.gpu_free_mb()` in `local_agent/router.py`.  Its
  `nvidia-smi --query-gpu=memory.free` implementation had been accidentally
  stranded after `plan_vision_vram()`, making every real telemetry check return
  `None`.
- Added a regression test that parses a mocked `15830 MB` telemetry reply.
- Corrected `local_agent/START_LOCAL_AGENT_GUI.ps1` to expect server revision
  `2026-08-24-qwen25-vl-caption-v4-r25`.
- Fixed the action extractor so a watcher-owned Qwen runtime is used after it
  consumes its expected VRAM; it is no longer re-queued by its own allocation.
- Raised the temporary Qwen runtime context from 16K to 32K.  The attempted
  detailed one-second action request measured 20,978 prompt tokens, which is
  above the former 16K server ceiling.
- Hardened VLM cleanup so a failed Windows termination retains its ownership
  record instead of orphaning GPU memory invisibly.

## Why

The exact Qwen2.5-VL Caption V4 GGUF and matching mmproj were present, but the
watcher saw unknown free VRAM and correctly failed closed.  It therefore never
started the already-queued video action job.

## Evidence and verification

- The local `nvidia-smi` command reports 15,830 MB free VRAM.
- `python local_agent/test_vram_arbitration.py`: 5/5 passed.
- `python local_agent/test_media_analysis.py`: 16/16 passed.
- `python local_agent/test_media_gpu_queue.py`: 18/18 passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  124/124 valid.

## Still to verify

The operator cleared the retry through the GUI while it was loading, so it was
not re-enqueued. The temporary VLM was then terminated and GPU memory released.
No render was started by this change.
