# 2026-08-26 — paired phone tool grants

## Fixed

The active, cryptographically paired Sideband phone identity
`62ce41abf11e32c42a6d85736f36cdde` was still limited to
`start_current_chat_render`. The phone agent was therefore correctly refusing
its sandboxed `run_code` calls and its direct `start_batch_render` fallback.

The operator explicitly authorized these additional capabilities for this exact
identity:

- `run_code` — still confined to the CPU-only, network-off sandbox.
- `start_batch_render` — still runs the same preflight, prompt validation,
  ownership, thermal, and global GPU-gateway checks.
- `start_current_chat_render` — retained for rendering the trusted chat's
  latest complete prompt set.

## Boundaries retained

This is not a blanket phone elevation. The phone remains denied write/build,
process-stop, persistent-memory, and other gated capabilities unless separately
granted. The desktop GPU gateway's global **Block** mode still prevents either
render path, and each remote invocation remains append-only audited.

## Follow-up fix

The runtime grants were correct, but `agent.py` and the render tool descriptions
still said that a remote phone could never render and that both render routes
were desktop-only. That stale model-facing policy caused the assistant to ask
for an impossible desktop permission despite a valid paired grant. The wording
now describes the exact per-identity capability check, and the Sideband bridge
was restarted to load it. Native tool regression: **25/25 passing**.

## 2026-08-27 follow-up

The active phone requested a LoRA test and correctly selected `run_build`, which
had not been granted yet. The same active paired identity now has the explicit,
revocable `run_build` capability in addition to its sandbox-code and render
capabilities. The persistent operating memory and `run_code` tool description
were also corrected: they previously repeated the superseded blanket
phone/desktop rule into every chat. The bridge was restarted again after the
correction. `test_native_tool_calling.py`: **25/25 passing**.
