# 2026-09-09 — Scene-plate strategy and QA recovery

- Removed residual filming/production cues from still prompts, including
  `found-footage composition`, `image-to-video`, `camera damage`, `recording
  equipment`, and `taped mark`.
- Pre-fall apartment prompts no longer inherit contradictory Level-0 Backrooms
  architecture cues.
- C001 now explicitly requires one clearly visible fictional adult male actor.
- Mechanical QA accepts the camera-free `viewer-perspective` / `clean scene
  plate` control instead of requiring the word `camcorder`.
- Exact-Qwen review instructions now state that camera/crew equipment is
  forbidden and must never be treated as a required prompt element.
- Regression results: 21 production tests and 4 media-accuracy tests pass.
- Live evidence: C001 start, C001 last, and C002 start passed semantic QA; the
  supervisor advanced to C002 last. Video generation remains gated on all
  stills passing.
