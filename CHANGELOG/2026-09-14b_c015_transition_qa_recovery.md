# 2026-09-14b — C015 still-transition QA recovery

## Scope

Backrooms prompt-pack stills only. Videos remain blocked pending completion of
the still phase and explicit operator approval. Existing attempts and receipts
were preserved.

## Fixed

- Corrected facial-hair normalization: an exact-VLM description of
  `beard, mustache` is now compared as a beard, rather than being incorrectly
  reduced to a mustache-only class.
- Extended the bounded lazy exact-Qwen runtime readiness window from 90 to 150
  seconds. This prevents a normal ComfyUI-to-VLM VRAM-release handoff from
  being recorded as a semantic content failure.
- Added C015 start recovery: after two rejected SDXL attempts, one hash-pinned
  identity-preserving forward-lunge candidate is reviewed through the normal
  exact-Qwen gate.
- Added C015 last recovery: after two visibly invalid apartment/camera renders,
  one hash-pinned clean tilted Backrooms POV endpoint is reviewed against its
  authored transition brief. The transition intentionally has no person, so
  cross-scene identity comparison is explicitly skipped only for that control
  mode; all direct setting, equipment, and composition checks remain required.

## Verification

`python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q`

118 tests passed. The C015 start and clean C015 last candidates both passed the
exact Qwen2.5-VL Caption V4 / llama.cpp gate. No video job was started.
