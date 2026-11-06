# 2026-08-31 — VLM residency status is now truthful

## Finding

The media watcher correctly refuses to terminate a Qwen2.5-VL llama.cpp server
without its ownership record. Its old completion log nevertheless said that the
VLM had been released. That could make the operator believe the GPU was free
while the unowned server still held VRAM and forced chat routing to CPU.

## Change

`media_watcher._release_vision_batch()` now records the actual outcome:

- an owned runtime was released; or
- an unowned runtime remains resident and the GPU stays reserved.

Media pressure is cleared in either case because the watcher no longer owns a
batch; router process/VRAM checks remain authoritative for model routing.

## Verification

- `python local_agent/test_media_watcher_exact_qwen.py` — 7 passed.
- `python local_agent/test_media_analysis.py` — 20 passed.

No model was loaded, unloaded, or downloaded for these tests. The current
unowned VLM process was intentionally left untouched.
