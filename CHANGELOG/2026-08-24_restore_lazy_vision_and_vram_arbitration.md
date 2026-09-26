# 2026-08-24 — Restore lazy vision startup and VRAM arbitration

## What changed

- Removed unconditional Qwen2.5-VL startup from the desktop launcher.
- The media watcher now starts the exact local Qwen2.5-VL V4 GGUF/mmproj pair
  only for a queued sensory batch and releases it after the batch drains.
- Added `router.plan_vision_vram(tiers)` as the one decision point for the
  coexist → 14B downgrade → idle-chat eviction ladder.
- Added a chat-busy marker to protect streaming responses and a temporary media
  pressure marker that lets the next chat prefer the configured 8B fallback.
- Restored queue-first foreground image/video requests: only the watcher may
  reclaim chat VRAM or create a VLM runtime window.
- Kept the operator-requested clear-queue control and cancelled evidence records.
- Added the lazy-VLM and queue-evidence rule to `local_agent/memory.json` so it
  is included in the agent's persistent local memory.
- Fixed `extract_video_actions`: complete local VLM weights/projector now mean
  "queue-capable" while the lazy runtime is stopped, rather than falsely
  reporting the model as uninstalled.

## Why

The launcher was starting the VLM on every desktop launch, which made the GPU
look occupied with no media job and contradicted UPGRADE 09/15.

## Verification

- `test_media_gpu_queue.py`: 18 passed.
- `test_vram_arbitration.py`: 4 passed.
- `test_media_analysis.py`: 12 passed.
- `test_native_tool_calling.py`: 10 passed.
- Prompt validation: `124/124 valid`.
- Started the normal desktop launcher and verified the app reports revision
  `2026-08-24-qwen25-vl-caption-v4-r23`, CPU Huihui 8B routing, no listener on
  render port 8188, and no listener on the VLM's dedicated port 11436.
- Stopped one pre-existing stale VLM server that was listening on 11436. It was
  not watcher-managed and would otherwise have contradicted lazy VLM loading.

## Still live-unverified

The real 14B-resident → watcher reclaim → Qwen2.5-VL batch → release sequence
needs one deliberate media submission after the refreshed launcher starts. No
Equal Shares render was started for this change. A separate pre-existing
`FunGen` GPU process remained running, so the live agent correctly selected CPU
routing rather than taking the GPU.
