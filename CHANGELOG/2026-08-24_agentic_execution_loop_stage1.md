# 2026-08-24 — Agentic execution loop, stage 1

## Added

- `local_agent/agentic_state.py`: bounded, persistent, operator-visible task
  checkpoints. They contain an explicit goal, checklist, status, and the last
  eight tool observations; they never contain hidden model reasoning.
- `agent.py` now starts/restores a checkpoint for substantive multi-step work,
  preserves the checkpoint during context trimming, records each completed tool
  result, and directs follow-up turns to ground factual claims in observations.
- `local_agent/test_agentic_state.py`: checkpoint persistence, bounded evidence,
  failure/block state, protected system checkpoint retention, and native-tool
  integration checks.

## Safeguards retained

No tool was added and no validation was relaxed. `tools.py` remains the authority
for schemas, argument validation, protected paths, render preflight, and remote
permissions. The harness never executes a checkpoint, a plan, or model text.
It only records a tool result after the existing guarded call has returned.

## Reference approach

The implementation adapts the plan/act/observe and evidence-grounding ideas in
smolagents, Aider, LangGraph Self-RAG, and LangGraph plan-and-execute without
installing those frameworks or adding a dependency/download burden.

## Remaining limitation

This stage does not pretend that a small local model can self-grade truth. The
grounding guard retains named evidence and requires an explicit “unverified”
label where evidence is absent. Stronger relevance/hallucination grading awaits
a measured evaluation suite.
