# 2026-08-27 — scheduled phone messages: the orphaned half connected

## The reported failure

From the phone: *"start sending a message every 30 seconds for the next 20 or 30
minutes starting with 0 and counting up."* The agent replied as though it had
started. **Nothing was ever sent**, and its reply also mentioned permissions,
which had nothing to do with the request.

## Root cause — two missing connections, not one

`local_agent/phone_scheduler.py` already existed (created 2026-08-27 17:14) and
is complete and correct: durable JSON state, bounded intervals and counts,
per-identity isolation, an audit trail, and a `dispatch_due(send)` entry point.

It was **orphaned at both ends**:

1. **No tool registered it.** `tools.py` contained no scheduler entry — the only
   match for "schedul" was `scheduler="karras"`, a ComfyUI sampler argument. The
   model therefore had no way to create a schedule.
2. **Nothing called `dispatch_due`.** `lxmf_agent.py` never imported the module.
   Even a schedule created by hand would have sat in the file forever.

So the model had no capability, and did what a model does with no capability and
a confident-sounding request: it narrated success. It then reached for a gated
execution tool as a substitute, which is exactly where the unrelated permission
language came from. **The permission system behaved correctly** — it refused
something that should be refused. The bug was the absent feature behind it.

## What changed

### `tools.py` — three phone-only tools

| tool | |
|---|---|
| `schedule_phone_messages` | `{"message":"count {n}","interval_seconds":30,"count":40}`, optional `start` |
| `list_phone_schedules` | this phone's jobs and their status |
| `cancel_phone_schedule` | `{"job_id":"phone_schedule_..."}` |

**Source-bound by construction.** The recipient is always the calling identity,
injected by the trusted dispatch seam in `call()` — the same mechanism already
used for `__remote_render_identity`. There is **no recipient parameter in the
schema**, so the model cannot name, choose or forge a target. A desktop call has
no identity to inject and is refused with a clear message.

This is a new capability, not a relaxed permission. No existing gate was widened.

### `lxmf_agent.py` — the delivery half

- `_scheduled_send()` resolves the pairing and replies through the existing
  `_reply()` path with `kind="scheduled"`. If the pairing is no longer active it
  raises `ScheduleBlocked`, so revoking a phone stops its schedules rather than
  retrying forever.
- `drain_scheduled()` wraps `dispatch_due` and swallows its own errors — a
  scheduler fault must never kill the bridge loop.
- The existing 1-second `run()` loop now drains on every tick.

## Verified

`local_agent/test_phone_scheduler.py`, **10 tests, all passing**:

- all three tools registered **with schemas**
- the schema exposes **no** `identity` / `recipient` / `to` / `target` / `address`
- a desktop call is refused
- a model-supplied `__remote_schedule_identity` is **stripped** and refused —
  the forgery path is closed
- a phone call binds to its caller
- **counts up correctly**: `count 0` at t, nothing at t+1s, then `count 1/2/3` at
  30-second intervals, and **no fifth message** after the count completes
- unpairing mid-run marks the job `blocked`, not retried
- a transient send failure does **not** increment `queued_count` — a failed queue
  is never recorded as a sent message
- the run loop really calls `drain_scheduled()`, and `_scheduled_send` reaches
  `_reply` with the right bytes, text and `scheduled` kind

Unaffected: 48 tools, 48 schemas, none missing; `project_state` still dispatches;
`validate_h3_prompt.py` still **124/124**.

## Still unverified

- **No message has been sent to the real phone yet.** Every test above uses an
  injected send callback. The first live run is the real test.
- Wording only: whether the model reliably chooses `schedule_phone_messages` for
  a plain request like "message me every 30 seconds" is unmeasured.
- The bridge must stay running for a schedule to continue; there is no catch-up
  for messages whose due time passed while it was stopped. `dispatch_due` sends
  one message per due job per tick, so a long outage does not produce a burst —
  but it does mean missed intervals are skipped, not replayed.

## Note for the operator

Limits are deliberate: interval **10–3600 s**, count **1–120**, total span within
**24 hours**. "Every 30 seconds for 30 minutes" is 60 messages — within range.

A queued LXMF message is **queued, not delivered**. The workstation cannot
promise radio delivery, and the tool's own response says so rather than claiming
success — which is the failure mode this entry exists to fix.
