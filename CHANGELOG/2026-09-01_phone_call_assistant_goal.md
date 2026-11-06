# 2026-09-01 — Operator-approved phone-call assistant goal

## What changed

- Added a low-priority future-capability ticket to `TODO.md` for an
  operator-approved phone-call assistant.
- Recorded the durable operating constraint in
  `local_agent/OPERATING_MEMORY.md`.

## Why

The operator wants the local agent eventually to complete ordinary tasks by
making calls, including from their phone-connected workflow. This needs a
defined approval and audit boundary before it can be considered for
implementation.

## Safety and implementation boundary

This is planning only. Each call must require a final review of the recipient,
number, purpose, and script. The agent must identify itself honestly and cannot
make autonomous emergency, premium-rate, or unknown-number calls; make purchases
or account changes; disclose sensitive information; enter payment credentials;
or handle one-time codes. Recording/transcription is opt-in, encrypted, and
consent-law gated.

## Evidence

The new tracker entry and operating-memory policy describe the requested scope
and explicit non-goals. No telephony provider, Android permission, Sideband
transport, scheduler, or call process was changed.

## Verification

- Reviewed the new TODO and operating-memory entries for a clear unimplemented
  status and final-confirmation requirement.

## Still unverified

No telephony provider/device routing contract, call interface, consent workflow,
or simulated-call test exists yet.
