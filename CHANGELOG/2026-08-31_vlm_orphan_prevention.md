# 2026-08-31 — Qwen2.5-VL orphan prevention

## Incident

After a completed phone image analysis, `llama-server.exe` remained idle but
held 10.6 GB of RTX VRAM. It had no runtime ownership record, so the safe
release function correctly refused to terminate it. This forced chat to CPU
until the exact confirmed VLM PID was stopped by operator-authorized recovery.

## Fix

`capabilities.ensure_qwen25_vl_runtime()` now:

- atomically writes its ownership record immediately after spawning the exact
  local Qwen2.5-VL server;
- terminates only that freshly spawned PID if ownership recording fails; and
- releases the owned server if its readiness window expires.

This closes both paths where a failed local launch could leave an unowned,
VRAM-resident server behind. A truly pre-existing manually launched listener
remains protected from automatic termination.

## Verification

- `test_qwen25_vl_identity.py` — 7 passed, including simulated ownership-write
  failure and readiness-timeout cleanup.
- `test_media_analysis.py` — 20 passed.
- `test_media_watcher_exact_qwen.py` — 7 passed.
- Live after recovery: VRAM 76 MB, port 8188 closed, no foreign compute
  process, router selects `huihui_ai/qwen3-abliterated:14b` on GPU.

The idle watcher was restarted only after its queue was verified empty.
