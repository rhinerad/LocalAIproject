# 2026-08-28 — Context-prefetch extraction (architecture audit job 5)

## What changed

- Added `local_agent/context_prefetch.py`.
  - `ContextBudgetPolicy` is the one named source for the five pre-model
    context limits: tool results, URL evidence, continuity, approved exemplars,
    and deep-research results.
  - `ContextPrefetcher` exposes the ordered injection seam.
- `agent.answer()` now builds one `ContextPrefetcher` instead of hand-running
  the five pre-model injections inline.
- Extracted the prior-chat and bounded difficulty-plan blocks into named agent
  helpers. URL evidence, local-document retrieval, and approved-exemplar
  retrieval retain their existing safeguards and source-labelling behavior.

## Behavior preserved

- URL evidence still runs before the Sonic Pi deterministic guard; the other
  four stages still run afterward in historical order: project docs, prior
  chats, difficulty plan, then approved exemplars.
- The existing `agent` constants remain compatibility aliases, so public test
  callers and context sizes did not change.
- No tool permission, GPU routing, render preflight, CPU thread cap, or model
  selection behavior changed.

## Verification

- New `test_context_prefetch.py`: 2/2 pass (historical stage ordering and
  existing policy values).
- `test_context_resilience.py`: all five checks pass.
- `test_exemplar_retrieval.py`: 2/2 pass.
- `test_general_assistant.py`: all seven checks pass.
- `test_native_tool_calling.py`: 28/28 pass, unchanged.
- `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.
- Current tool schema catalog remains **52**; this extraction adds/removes no
  tools. The audit prompt's `48` expectation is stale and remains documented.
