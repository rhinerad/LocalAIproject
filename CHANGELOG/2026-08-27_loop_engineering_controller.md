# 2026-08-27 — Opt-in read-only loop-engineering controller

## What changed

- Added `local_agent/loop_controller.py`, a stdlib-only durable controller for
  explicit verification goals.
- Its fixed check registry contains only local non-rendering test and validation
  commands. Its only optional tool handoff is the existing non-writing diff
  preview after a failure and explicit request; it never starts a model,
  downloads, accesses the network, edits a project file, or controls ComfyUI.
- Added durable, redacted state under `local_agent/runtime/loop_engineering/`:
  goal records, one-result-per-run audit logs, triage records, review queue,
  configuration, and a compact status file.
- Added explicit default-off `loop_enabled` state. One `run-once` call executes
  exactly one pending fixed check; success advances to the next check only on a
  future invocation, while failure stops at `needs_operator` and opens a
  review record.
- Added a read-only status summary to the existing localhost app. It has no
  endpoint that can enable or run a loop.
- Added controller documentation and `test_loop_controller.py` coverage.
- Added a 20-scenario golden safety/maintenance contract and an evidence-only
  metrics report. They make no model calls and report unknown metrics as
  unmeasured instead of estimating them from nothing.
- Added a Phase-2 review-only repair-proposal handoff: only after a failed,
  operator-reviewed fixed check and an explicit request, it can call the
  existing non-writing unified-diff tool. It stores only a redacted audit item
  and diff hash; it cannot apply a file edit or approve its own proposal.
- Added `loop_verifiers.py`, a separate deterministic evidence registry for
  SHA-256 checks, JSON required-key checks, and captured-result predicates. It
  has no command runner, network access, model call, or authority to mark a
  goal complete.

## Why

This implements the safe first phase of the Loop Engineering design: durable
state, bounded discovery, constrained action, deterministic verification, and
an operator gate. It does not grant the agent recursive or self-modifying
authority.

## Verified

- `python local_agent/test_loop_controller.py`
- `python -m py_compile local_agent/loop_controller.py`
- `python local_agent/loop_evaluation.py`
- `python local_agent/test_loop_evaluation.py`
- `python local_agent/test_native_tool_calling.py`
- `python local_agent/test_loop_verifiers.py`

## Intentionally not done

- No scheduler, repair automation, proposal writes, external model verifier,
  worktrees, render control, downloads, or model loading was added.
