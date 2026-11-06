# ADR 0004 — Explicit-feedback-only learning

**Status:** Accepted

## Decision

Do not silently mine conversations for training or memory. Persist only
explicit operator feedback, using rule-only distillation by default. External
examples remain staged until the operator reviews provenance, licensing,
content, and the normalized result.

## Why

Chat history can contain private files, creative material, identities, and
incorrect model output. Silent ingestion would make those risks permanent and
would blur the line between an observation and an approved rule.

## Consequences

- Feedback storage sanitizes paths and sensitive data before persistence.
- Pending examples and negative feedback do not automatically alter retrieval
  or agent behavior.
- Learning quality is attributable and reversible through lifecycle metadata.

## Evidence

`local_agent/feedback_manager.py`, exemplar curation/lifecycle modules, and
their local regression suites.
