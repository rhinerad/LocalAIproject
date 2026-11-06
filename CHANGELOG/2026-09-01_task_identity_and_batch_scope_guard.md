# 2026-09-01 — task identity and batch-render scope guard

## Fixed

- A model can no longer invoke `batch_plan`, `batch_render`, or
  `start_batch_render` solely because an older chat turn discussed a render.
  The current operator message must explicitly request a batch-render action.
- A PowerInfer calibration/configuration JSON is consequently not treated as an
  H3 video prompt set or a batch-render folder.
- `agentic_state.apply_proposed_plan()` now preserves the original operator
  goal. A local planner can update only the inert checklist and cannot replace
  a PowerInfer task with a made-up render-recovery task after compaction.

## Verification

- `python local_agent\\test_native_tool_calling.py` — 47 tests passed.
- Added regression coverage for the stale PowerInfer JSON → `batch_plan` path
  and for a planner attempting to replace the task goal.

## Boundaries

No render, ComfyUI process, GPU workload, model/predictor/weight edit, registry
change, or router setting change was started by this work.
