# 2026-08-29 — Scheduled Sideband delivery fallback and final-outcome audit

## Finding

A live six-message, 30-second phone schedule was created for the paired phone
identity and the scheduler submitted counters `0` through `5` to the LXMF
router. The phone received none. `queued to LXMF` was router submission, not
delivery evidence.

The bridge hard-coded every outbound message to LXMF `DIRECT`. That works for
the immediate answer while a phone link is open, but a later scheduled message
can have no active direct link even though the paired session has an established
ratchet.

## Fixed

- The bridge now follows Sideband's delivery selection: retain `DIRECT` while
  a delivery link exists; otherwise use compact opportunistic delivery when a
  ratchet exists for the paired destination.
- Every outbound message now records its eventual LXMF `delivered` or `failed`
  callback in `runtime/lxmf/outbound_delivery_audit.jsonl`, including method,
  state, request ID and message hash. Router submission remains explicitly
  distinct from receipt.
- Added mocked coverage for both link-present and ratchet-only routing cases.

## Verification boundary

The corrected bridge must be restarted before a live re-test. A phone receipt
is still required to claim live delivery; this change does not turn queued
records into proof of receipt.
