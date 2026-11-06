# 2026-09-01 — Visible agent activity trace goal

## What changed

- Added a local-agent roadmap item for a structured, live activity trace in
  `TODO.md`.
- Recorded the durable UX requirement in `local_agent/OPERATING_MEMORY.md`.

## Why

The operator wants to see useful progress while the model is working: what is
planned, which tool is running, what actually completed, and which approvals or
blockers remain.

## Boundary

The intended feature is a concise, structured execution trace—not exposure of
private raw chain-of-thought. It must distinguish intent from observed results,
redact secrets, work with pruned artifacts, and survive a chat refresh.

## Evidence

The roadmap and operating-memory entries capture the requested lifecycle event
types and acceptance cases. No chat server, agent loop, UI, model, tool, or
render process changed in this documentation-only update.

## Verification

- Reviewed both new entries for event lifecycle, persistence, intent-versus-
  evidence, and sensitive-output requirements.

## Still unverified

No streaming event format, chat UI component, or regression test exists yet.
