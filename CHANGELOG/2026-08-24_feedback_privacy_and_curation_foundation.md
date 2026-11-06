# 2026-08-24 — Privacy-first feedback and exemplar-curation foundation

## Added

- `local_agent/feedback_manager.py`: default rule-only feedback records,
  path/email/credential sanitization for explicit full-sanitized mode, and
  AES-256-GCM envelopes written by an idle-only worker.
- The AES key is separate from feedback records and protected with the current
  Windows user's DPAPI. If a headless context has no loaded Windows profile, it
  fails closed and retains queued records only in memory; it never writes a
  plaintext key or record. An explicit `LOCAL_AGENT_FEEDBACK_KEY` is supported
  for an operator-managed service account.
- `local_agent/exemplar_curator.py`, `exemplar_filter.py`, and
  `prompt_normalizer.py`: an operator approval queue with source/license
  metadata, deterministic pre-screening, exact deduplication, and a native-H3
  review scaffold. Bracketed second ranges are converted to prose because they
  are invalid H3 grammar.
- `local_agent/exemplar_lifecycle.py`: ID-only attribution, positive/negative
  health scores, `needs_review` flagging below 0.40 after five uses, and
  reversible local archival.
- Local-only API endpoints for pending/staging/review actions.

## Deliberate limits

- No external corpus, Chroma DB, embedding model, or training package was
  downloaded, installed, embedded, or activated.
- No candidate is retrieved into an answer merely by being staged or approved.
- No render, media, ComfyUI, or vision-runtime setting was touched.

## Verification

- `python local_agent/test_feedback.py` — 4/4 passed.
- `python local_agent/test_exemplar_curator.py` — 3/3 passed.
- `python local_agent/test_exemplar_linter.py` — 3/3 passed.
- `python local_agent/test_exemplar_lifecycle.py` — 1/1 passed.
- Full local-agent suite passed: 107 tests.
