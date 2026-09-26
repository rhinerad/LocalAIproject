# Fix: extract_video_actions truncating at ~13 seconds

**Date:** 2026-08-23  
**Revision bump:** r11 → r12

## Problem

`extract_video_actions` stopped producing output at approximately second 13 of
any video regardless of length. On a 70-second video the action log covered only
0–13 s, leaving ~57 s unanalyzed.

## Root cause

`_run_vision_gpu` used a fixed `num_ctx: 16384`. MiniCPM-V 2.6 encodes each
768px-wide video frame into roughly 1000–1500 visual tokens. With a batch of 30
frames the model was offered ~30 000–45 000 image tokens but had only 16 384
slots available. Ollama silently truncated the input to whatever fit, so the
model saw only the first ~13 frames and stopped generating at second 13. The
remaining batches (frames 30–69) ran but suffered the same truncation, and their
output was assembled into the action log — but since each batch also truncated
at ~13 of its own 30 frames, the output appeared to cover only the first 13
seconds of each window.

## Fix

**`local_agent/media_tools.py`**

1. Added `num_ctx: int = 16384` parameter to `_run_vision_gpu`. All existing
   callers (`_vision_direct`, `_vision`) pass nothing and keep 16 384 — that is
   correct for single- and two-image calls used in `analyze_video`.

2. `extract_video_actions` now calls `_run_vision_gpu(..., num_ctx=32768)`.
   At 32 768 context and ~1250 tokens/image, 20 images fit with comfortable
   margin before instruction text.

3. `_ACTION_BATCH_SIZE` reduced from 30 to 20. At 32 768 context 20 frames fit
   safely; 30 would still risk truncation at the high end of the token-per-image
   range.

**`local_agent/server.py` / `START_LOCAL_AGENT_GUI.ps1`**

`APP_REVISION` and `$ExpectedAgentRevision` bumped to `r12` to force
`Stop-StaleAgent` to kill the r11 process and reload the corrected
`media_tools.py`.

## VRAM impact

32 768 context adds ~1–2 GB to the MiniCPM-V KV-cache versus 16 384. The VRAM
gate in `extract_video_actions` already confirmed free VRAM ≥ 8 750 MB before
this path runs, so the extra cache fits within the available headroom.

## Coverage after fix

A 70-second video at 1 fps → 70 frames → 4 batches of 20/20/20/10. Each batch
is labeled with its time window. All 70 seconds are analyzed.
