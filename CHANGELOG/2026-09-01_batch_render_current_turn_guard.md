# 2026-09-01 — Batch-render current-turn guard

## What changed

- `local_agent/agent.py` now refuses `batch_plan`, `batch_render`, and
  `start_batch_render` unless the current operator message explicitly requests
  a batch-render operation.
- Added a regression test proving that a PowerInfer/calibration-JSON request
  cannot execute a stale-context `batch_plan` call.

## Why

An earlier current-chat render failure remained in the conversation. On a later
request to continue PowerInfer work using an approved JSON file, the model
mistook the calibration artifact for H3 prompts and scanned the repository root
as a batch job folder. That scan was irrelevant and produced a misleading
“zero prompts” answer.

## Behavior now

The tool call is blocked before `tools.call()` runs. The deterministic recovery
states that a calibration/configuration JSON is not an H3 render job and directs
the agent toward the relevant validation or PowerInfer workflow instead.

## Verification

- `python local_agent/test_native_tool_calling.py`

## Still unverified

The guard deliberately does not perform PowerInfer calibration intake; that
requires a specific, safe source-file path and its own validation workflow.
