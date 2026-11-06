# 2026-09-01 — Regression-runbook refresh

## What changed

- Corrected stale README text that described `test_native_tool_calling.py` as
  a nine-test suite. It now contains 45 tests.
- Added `docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md` with the fast changed-core
  check, bounded local-agent groups, and the only valid isolated worker-farm
  invocation.

## Why

One monolithic test-discovery run can outlast a short terminal or automation
window. The documented groups preserve fail-fast behavior and make it clear
that worker-farm tests require their dedicated virtual environment.

## Verification

The documented groups were run on 2026-09-01: 458 local-agent tests, 16
worker-farm tests, and the 124/124 H3 validator all passed.

## Retrieval refresh

Ran `python local_agent\build_knowledge_pack.py` after adding the new operator
decision and regression-runbook documents. It rebuilt the generated local
search index to **339 files / 795 chunks** (3,736.2 KB), so those documents are
available through the agent's local document retrieval. No model, render,
ComfyUI backend, queue, or bridge was started.

Confirmed both `docs/LOCAL_AGENT_OPERATOR_DECISIONS.md` and
`docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md` are present in the rebuilt index.
