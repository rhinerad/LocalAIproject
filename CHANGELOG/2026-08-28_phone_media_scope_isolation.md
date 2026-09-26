# 2026-08-28 — Phone media request scope isolation

## Fixed

- A short, unrelated phone request could inherit an active durable task checkpoint from earlier render-permission work in the same conversation. The model could then mention that stale topic even after a valid attachment tool call.
- `agentic_state.begin_turn()` now marks an unrelated active checkpoint as `superseded` and preserves it as evidence rather than injecting it into the new direct request. A new substantive task retains a bounded prior-task record.
- `agent.py` adds a turn-local scope boundary when the current request is not about rendering or permissions. It prevents unrelated historic context from producing invented permission status; actual current tool denials remain reportable.

## Verification

- Added regression coverage for direct attachment/media requests after a phone render-permission task, plus the durable-state supersession behavior.
- This change does not start renders, load models, alter paired-identity grants, or modify received attachment evidence.
