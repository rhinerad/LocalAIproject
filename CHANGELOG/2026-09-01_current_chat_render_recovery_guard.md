# 2026-09-01 — Current-chat render recovery guard

## What changed

- `local_agent/agent.py` now treats the exact `start_current_chat_render`
  failure “this chat has no complete fenced H3 prompt set to render” as a
  deterministic terminal recovery.
- Added a native-tool-loop regression test in
  `local_agent/test_native_tool_calling.py`.

## Why

After a current-chat render failed because no H3 prompt set existed in that
chat, the model was allowed another tool-selection turn and suggested a batch
render against the repository root. That path is not an operator-supplied job
folder and does not establish that a different chat's prompts should be used.

## Behavior now

The agent reports that no render started, refuses to substitute another folder
or another chat's prompts, and tells the operator to put a complete fenced H3
prompt set in the current chat before retrying.

## Verification

- `python local_agent/test_native_tool_calling.py`

## Still unverified

This regression test does not start a renderer. A future real render remains
subject to the existing prompt, queue, port, thermal, and GPU-gateway preflight.
