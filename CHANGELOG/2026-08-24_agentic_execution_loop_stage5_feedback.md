# 2026-08-24 — Agentic execution loop, stage 5: explicit feedback

## Added

- Assistant-reply controls in the local GUI: **Helpful**, **Needs correction**,
  and **Correct & remember**.
- `local_agent/feedback.py`: opt-in feedback ledger and persistent-rule
  promotion.
- `/api/feedback`: localhost-only endpoint for those controls.

## Behavior

- Helpful/Needs correction feedback is audit-only; it does not alter persistent memory.
- A reusable rule is saved only when the operator types it into the explicit
  remember flow.
- The ledger stores a reply fingerprint, not raw reply text. Only the explicitly
  supplied reusable rule is retained.
- Safety-weakening rules are refused. Feedback cannot execute commands, change
  permissions, modify files, or grant a phone any capability.

## Verification

- Added tests for audit-only approval, explicit rule promotion, and unsafe-rule
  refusal.
- Full local-agent suite: 99 tests passed.
- Agentic harness baseline: 5/5 passed with mocked/no-model calls.
- H3 prompt validation remains 124/124 valid.
