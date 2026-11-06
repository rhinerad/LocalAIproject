# 2026-08-29 — Radio delivery metrics harness

## Added

- `local_agent/radio_metrics.py`, a stdlib-only evidence reporter for the
  append-only scheduler audit plus optional operator-recorded phone receipts.
- `docs/RADIO_DELIVERY_EXPERIMENT_PROTOCOL.md`, a controlled 20-message test
  procedure and receipt format.
- Regression coverage proving that a queued LXMF event is never labelled as
  delivery without receipt evidence, and that loss is only calculated after
  the operator closes the test window.

## Boundary

- No bridge was restarted, no phone message was sent, no radio port was opened,
  and no existing schedule/audit evidence was changed.
- This adds measurement scaffolding only. It does not establish packet-loss,
  delivery, or latency figures.
