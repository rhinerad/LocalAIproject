# 2026-08-24 — Bounded self-improvement ledger

## What changed

- Added `local_agent/learning.py`, an append-only, privacy-minimized ledger for
  typed repeated backend failures.
- After two occurrences, only a fixed reviewed lesson is injected into future
  chats. It cannot write code, alter tools, change model policy, or modify
  evidence.

## Why

The operator reported repeated cross-chat mistakes. A small local model needs
durable feedback, but allowing it to self-edit its safeguards would create a
less reliable system.

## Verification

- The ledger stores only category, event, timestamp, chat id, and a hash of the
  outcome; it stores no operator message, URL, attachment, tool arguments, or
  raw error text.
- The change is loaded through the normal server event path.

## Still unverified

- Repeated real failures must occur after restart before a lesson appears. No
  model, render, or media job was started for this change.
