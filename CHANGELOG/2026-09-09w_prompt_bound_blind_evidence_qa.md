# 2026-09-09 — Prompt-bound blind-evidence still QA

## Root causes proven from live evidence

- `media_tools._build_prompt()` discarded the operator's expected generation
  prompt whenever the semantic reviewer supplied a custom rubric. The VLM was
  therefore grading generic plausibility instead of the requested scene.
- A single prompt-conditioned VLM pass produced false approvals. It claimed a
  neutral actor had raised a hand, claimed cropped people were full-body, and
  called a doorway-centered hallway a living room.
- Fixed image-to-image denoise `0.42` preserved the opening pose even when a
  last-frame prompt required a visible smile, wave, turn, or other action.

## Changes

- Preserve the custom reviewer rubric and append the full operator request.
- Require structured per-criterion semantic checks; missing/false checks fail.
- Run an independent blind observation before the prompt comparison.
- Enforce blind evidence in Python for both visible feet on full-body prompts,
  raised-hand/wave actions, smile/grin expressions, forbidden camera equipment,
  explicit positive room types, C001's visible sofa/couch requirement, and its
  core locked clothing items. Forbidden alternatives and small omitted details
  are not accidentally promoted to hard requirements.
- Semantic gate version is `blind-evidence-enforced-v8`; every older semantic
  pass is invalid and cannot be reused.
- C001 now explicitly requires unmistakable living-room furniture and forbids
  hallway/doorway-only, kitchen, bedroom, and cropped compositions.
- Last-frame i2i starts at denoise `0.52`; rejected retries increase by `0.10`
  to a hard cap of `0.72`. Failed attempts and receipts remain immutable.
- Image-render cleanup now falls back to the exact owned `Popen` handle when
  Windows denies `taskkill`, while process liveness remains fail-closed.

## Live validation

- Known-bad empty-room, wrong-person, cropped, hands-down, and wrong-room images
  were manually inspected and rejected.
- The v5 gate overruled a VLM `pass` using literal blind evidence:
  `both_feet_visible: false`.
- Production remains in stills phase for task `3262c1f626974397`; video
  generation remains blocked until all current-v8 stills pass and receive the
  existing explicit hash-bound approval.

## Tests

- `test_media_accuracy_gate.py`: 5 passed.
- `test_image_render_cleanup.py`: 3 passed.
- `test_production_integrity.py`: 23 passed.
- `test_prompt_pack_production.py`: 5 passed.
- Production-focused discovery after the v8 changes: 30 passed.

No evidence was deleted or overwritten. No unknown process was stopped.
