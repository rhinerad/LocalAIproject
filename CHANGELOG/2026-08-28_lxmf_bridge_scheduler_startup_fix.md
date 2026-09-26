# 2026-08-28 — LXMF bridge scheduler startup repair

## Fixed

`LXMFBridge.run()` called `self.drain_scheduled()`, although the scheduler
delivery adapter belongs to its transport-agnostic `BridgeCore` instance. The
bridge therefore opened the RNode and then crashed on its first timer tick with
`AttributeError: 'LXMFBridge' object has no attribute 'drain_scheduled'`.

The loop now calls `self.core.drain_scheduled()`. No scheduler policy, pairing
rule, permission boundary, or delivery semantics changed.

## Verification

- `python -m unittest test_phone_scheduler -v` from `local_agent/`: **12/12**
  passed, including source binding, durable pre-send leases, cancellation,
  no duplicate concurrent dispatch, and the bridge wiring assertion.
- A controlled four-second live bridge run opened `COM11`, configured the
  `Equal Shares RNode LoRa` transport at **914.875 MHz / 500 kHz / SF12 / CR5**,
  remained alive through the scheduler tick, and exited normally on its timer.
- The configured Wi-Fi AutoInterface still reports multicast echo failures.
  That does not prevent the independently configured USB LoRa transport and is
  not treated as successful Wi-Fi delivery.

## Still pending

The real paired-phone acceptance remains: receive five timed messages, cancel
one active schedule, and verify safe recovery across a bridge restart. LXMF
queueing alone is not claimed as phone delivery.
