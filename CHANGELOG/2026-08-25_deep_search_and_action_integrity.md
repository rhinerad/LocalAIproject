# 2026-08-25 — Deep Search audit and action-integrity proof

## Why

The Deep Search addition was functional, but a review found two correctness
risks: a model could repeat a citation URL that was not among fetched sources,
and untrusted webpage text was not explicitly framed as data rather than
instructions. A separate review of the newest desktop chat found no tool cards
or tool-result evidence behind claims that software had been downloaded,
launched, and modified.

## What changed

- `deep_research.py`
  - Treats fetched text as untrusted evidence and instructs the synthesizer to
    ignore commands or prompts embedded in webpages.
  - Replaces unsupported model-cited URLs with `[unverified citation removed]`
    and records a research gap instead of presenting fabricated evidence.
  - Uses the injectable monotonic clock consistently for its bounded deadline.
- `agent.py`
  - Adds an execution-evidence rule: plans and prose are never confirmation;
    only a permitted tool result can confirm a local action.
  - Refuses attempts to bypass paywalls, logins, licenses, activations,
    subscriptions, or other access controls. It states clearly that no files
    were changed and points to legitimate alternatives.
  - Rejects a bare model claim of having performed a local action when no tool
    call occurred in that turn.
  - Preserves more bounded evidence for `deep_research` follow-up synthesis
    (6,000 characters; other tools remain at 2,400).
- `server.py`
  - Persists a concise per-turn `tool_evidence` record in assistant message
    metadata: tool name, result/error outcome, and a 240-character summary.
    This is durable confirmation for audits without saving tool arguments.
- Startup revision is now `2026-08-25-action-integrity-r58`.

## Evidence

- `python local_agent/test_native_tool_calling.py` — 21/21 passed.
- `python local_agent/test_deep_research.py` — 6/6 passed.
- `python local_agent/test_search_backend.py` — 7/7 passed.

No render, ComfyUI workflow, model download, or new model load was started for
this change.
