# 2026-09-05av — Operator-approved phone-call assistant: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05av**.

Design note only — no provider account, no dial, no `APP_REVISION`, no
tool added.

Doc: `docs/design_notes/PHONE_CALL_ASSISTANT_2026-09-05.md`.

## Finding

Nothing in this tree places a PSTN or cellular call. The paired phone is
an LXMF chat identity (`lxmf_agent.py`, ADR 0001). `phone_scheduler.py` /
`schedule_phone_messages` send repeating **text back to the caller
only** — the model cannot name a recipient (`tools.call` injects
`__remote_schedule_identity`). Sideband’s “telephony” is **LXST over
Reticulum** (`vendor_sideband/README.md`), which cannot reach a shop’s
NANP number.

A live dial needs an explicit routing contract the TODO already requires:

- **Path P** — telephony API (Twilio-class). Needs a vendor account and
  almost certainly a public webhook, which fights loopback-only HTTP.
- **Path D** — Intent/`CALL_PHONE` on the paired handset. Needs an
  Android/Sideband-fork contract that the companion TODO has not
  approved. Stock Sideband has no cellular dial path here.

**There is no clean v1 that actually dials.** Forcing one would be an
implicit Sideband or scheduler extension, which the TODO forbids.

What can exist later, only after sign-off: Phase 1 = `call_gate` +
allowlist + hashed confirmation (copy `file_edit_gate`, **not**
`gpu_gate` `allow`) + simulated dial/cancel/timeout + min-metadata
JSONL. Mid-call purchases/ID/commitments need a **second** card. OTPs
and payment credentials are un-approvable. Recordings stay off pending
real legal review (C2), not a code comment.

No production code changed.
