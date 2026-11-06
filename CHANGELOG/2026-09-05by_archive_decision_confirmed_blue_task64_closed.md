# 2026-09-05by — Archive decision confirmed (A:+D:); Task #64 chars/token audit closed

## Scope

Operator tracking entry. Records an operator decision and closes out
Task #64's report, found already landed in CHANGELOG (`bx`) rather than
relayed through chat.

## Operator decision: archive destination pair

Operator confirmed the destination pair is **A: (source drive, existing
project tree) + D: (Seagate Portable, confirmed separate physical disk,
unique ID `3E543346485A464B`)**, accepting the caveat from `2026-09-05bu`/
Purple's verification that D: must be unplugged and stored elsewhere
between backup runs for this to remain a real second failure domain
against a site incident. This clears the runbook's own gate for Purple
to write `ARCHIVE_DECISION.md` (five required fields: destination pair,
custody approach for the recovery secret, source-root scope, first
restore-drill scope, execution-window preflight) and proceed to
installing Restic / creating a repo key. No Restic installed yet, no key
created yet — this entry only unblocks that next step.

## Task #64 (🔵 Blue) — closed, found landed as `2026-09-05bx`

Confirmed the same chars-per-token bug class found in the Qwen3.8-27B
eval (`bm`) also lived in the shared benchmark fill generator
(`measure_ollama_kv_cache.probe_prompt`), not in production routing.
Root cause: the router's message-JSON chars→tokens estimator (3.4,
intentionally conservative for wire-size estimation) was reused
backwards to *generate* filler text sized in tokens, silently
under-filling — the bm 20K-token target actually delivered 9375 tokens
(~6.5 chars/token on that repetitive filler). Fix is centralized in the
one shared helper (`probe_prompt(chars_per_token=...)`, calibrated live
via one short chat measuring `len(prompt)/prompt_eval_count`, offline
fallback 6.5 not 3.4) rather than patched per-script. `router.py`'s
production `_MESSAGE_CHARS_PER_TOKEN` constant is explicitly untouched —
correctly scoped as a benchmark-tooling fix, not a routing fix. 8/8
tests (`test_measure_ollama_kv_cache.py`). Does not re-run the GPU eval;
the bm 9375-token figure stands as recorded.

## Status

Task #64 done. Purple is now clear to write `ARCHIVE_DECISION.md` and
proceed. Task #63 (🔴 Red, re-verify catalog-drowning fix with ComfyUI
actually running) still has no report.
