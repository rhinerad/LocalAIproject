# 2026-08-28 — Phone counter default and scheduler-test isolation

## Fixed

- `schedule_phone_messages` now treats an omitted `message` template as
  `"{n}"`. A natural phone request such as “send five messages, counting from
  0” can therefore schedule `0`, `1`, `2`, `3`, `4` even if the model omits a
  redundant presentation field. An explicitly supplied blank message remains
  invalid. The phone-only, source-bound recipient rule is unchanged.
- Its native function schema now makes `message` optional and documents the
  counter-only default.
- `phone_scheduler.py` resolves state and audit paths at call time rather than
  capturing the live runtime paths as Python default parameters. Scheduler
  tests now use their temporary queue as intended; they cannot create future
  fake jobs in the live phone queue.
- Successful queue audit records now preserve the counter that was actually
  queued. Previously `queued_count` was incremented before the record was
  written, making the evidence label one ahead of the message. Existing audit
  evidence remains unchanged; the bridge was restarted for the corrected logic.

## Evidence

- A real phone message reached the bridge over the paired LoRa route and the
  CPU agent selected `schedule_phone_messages`. The refusal was specifically
  `message must contain 1 to 500 characters`, caused by the omitted template;
  it was not a radio, pairing, or permission failure.
- `python -m unittest test_phone_scheduler -v`: **14/14 passed**, including
  the counter-only default, source binding, pre-send lease, cancellation, and
  bridge wiring tests, plus exact queued-counter audit evidence.
- The bridge was restarted after the patch so the live phone path uses the
  updated tool implementation.

## Live acceptance evidence

The paired phone identity `62ce…cdde` completed two five-message, 15-second
counter schedules over the RNode transport. For the final controlled run,
`phone_schedule_12c978519bce4130` reached `complete` with five queue attempts;
the operator confirmed receipt on the phone. This verifies the phone → bridge
→ CPU agent → scheduler → LoRa reply path. It does not yet replace the separate
cancel-midway and restart-during-active-schedule checks.

## Preservation

Existing runtime schedule/audit records were preserved. No evidence was
deleted or rewritten.
