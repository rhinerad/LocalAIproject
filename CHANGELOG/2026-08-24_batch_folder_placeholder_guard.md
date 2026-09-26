# 2026-08-24 — Batch-folder placeholder guard

## What changed

- `local_agent/tools.py`: added `_batch_job_folder()` and use it for both
  `batch_plan` and `batch_render`.
- `local_agent/tools.py`: removed `D:/jobs/scene12` from the model-visible tool
  description.
- `local_agent/agent.py`: states that a batch job folder must be an actual path
  supplied by the operator; examples and previous-chat paths must not be copied.
- `local_agent/test_native_tool_calling.py`: adds a regression test for the
  former placeholder.

## Why

The model copied `D:/jobs/scene12` from the old tool-description example after an
operator asked for a render. That folder was never a real project job and the tool
correctly rejected it, but the failure was confusing and could recur.

## Evidence and verification

`python local_agent\\test_native_tool_calling.py` passed: 12/12 tests. The new
regression showed both `batch_plan` and `batch_render` rejecting
`D:/jobs/scene12` as a documentation example.

The follow-up recovery is also deterministic: it does not permit a model turn
after this exact refusal, so it cannot promise to persist or reuse the failed
example path.

## Still unverified

No render was started or tested. The current batch tool remains proposal-only;
direct render execution is a separate guarded capability and is not changed here.
