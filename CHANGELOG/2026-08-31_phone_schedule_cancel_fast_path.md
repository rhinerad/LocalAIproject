# 2026-08-31 — Phone schedule cancellation fast path

## Problem

The exact Sideband command `cancel the active phone schedule` previously made a
full CPU model request before it could select the cancellation tool. A short,
time-sensitive cancellation could therefore wait behind ordinary inference and
arrive after a schedule had completed.

## Change

`local_agent/lxmf_agent.py` now recognizes only that narrow cancellation form.
For a paired phone it lists that identity's active jobs, invokes the existing
`tools.call("cancel_phone_schedule", ...)` boundary for each, appends the final
reply to the ordinary phone chat, and sends it immediately. No other scheduling
language bypasses the model. The tool boundary still injects the verified
identity, validates the job owner, and writes the remote-tool audit record.

If no job remains active, the phone receives the explicit result rather than a
made-up cancellation claim.

## Verification

`python local_agent/test_lxmf_bridge.py` passed: 16 tests. The new test proves
the direct command avoids model execution and cancels only the calling
identity's active schedule. `python -m py_compile local_agent/lxmf_agent.py`
passed.
