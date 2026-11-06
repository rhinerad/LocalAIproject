# 2026-08-24 — Controlled developer workspace

## What changed

- Added `write_candidate_tool`: saves a versioned Python helper only under
  `local_agent/developer_workspace/`; it refuses overwrite and never executes it.
- Added `run_safe_check`: runs only fixed non-rendering tests and validation.

## Why

The operator wants Codex-like agency without turning a chat model into an
unrestricted Windows command shell.

## Verification

- `python local_agent/test_native_tool_calling.py` — 10/10 passed.
- `run_safe_check(context_tests)` — passed.
- Unknown checks are refused by the whitelist.

## Still unverified

- Natural tool selection in a real conversation. No render or protected file was changed.
