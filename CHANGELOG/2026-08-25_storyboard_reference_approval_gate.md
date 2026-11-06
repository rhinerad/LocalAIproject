# 2026-08-25 — Storyboard reference approval gate

## What changed

- Added `work/storyboard_from_story.py`, the non-GPU state and validation layer
  for general storyboards.
- It accepts a structured character/shot plan, validates character references and
  required shot fields, then stores a pending `reference_review.json` under the
  story's own `outputs/stories/<story>/` directory.
- Reference-sheet filenames may be recorded only as simple filenames. The state
  cannot mark the overview approved without coverage for every listed character.
- Frame planning remains locked until an explicit approval call; it returns an
  inspectable frame plan only and never calls an image or video renderer.
- The desktop local agent now exposes the same guarded sequence through native
  tool calls: prepare pending review, record sheet filenames, explicitly approve
  the overview, then read the unlocked frame plan.

## Safety

- The helper does not call an LLM, load a model, start ComfyUI, use the GPU,
  generate an image, or start a video render.
- The approval state is per general story and never writes to Equal Shares.
- This is the persisted enforcement point for the founding requirement: reference
  sheets must be reviewed before mass storyboard work is possible.
- The three state-changing storyboard actions are in the remote permission gate,
  so paired phone identities are default-denied; read-only frame-plan inspection
  stays safe.

## Verification

- `python work/test_storyboard_from_story.py` — 4/4 passed.
- CLI help verified `init`, `record-sheets`, `approve-refs`, and `frame-plan`.
- `python local_agent/test_story_image_plan.py` — 5/5 passed, including phone
  denial for pending-review creation.
