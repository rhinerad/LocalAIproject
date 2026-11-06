# 2026-08-29 — Encrypted archive plan and Pixel model selection

## Encrypted archive plan

Added `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`. It selects a versioned,
client-side encrypted Restic repository for raw media, evidence, and large
private artifacts; preserves source material; requires explicit destination and
recovery-secret custody; and requires a checksum-verified restore drill before
acceptance. No archival destination was initialized and no data was moved,
encrypted, deleted, or uploaded.

## Pixel PowerInfer selection

Selected the exact upstream sparse deployment target:
`Tiiny/SmallThinker-21BA3B-Instruct-GGUF` /
`SmallThinker-21B-A3B-Instruct.Q4_0.gguf`. The 4B Q4_0 SmallThinker model is a
required runtime/thermal smoke test, not the final target. The 21B model's
documented limited-memory mode is a test gate; its capability, thermals, and
normal-mode fit have not been claimed or verified on the Pixel 10 Pro.

No Android binary, model, NDK, or model download was started.
