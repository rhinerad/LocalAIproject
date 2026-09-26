# 2026-08-24 — Agentic execution loop, stage 2

## Added

- Conservative retrieve-decision for explicit local project documentation,
  policy, history, and configuration questions.
- `retrieval.search_relevant()`: deterministic document relevance filter. A
  lexical BM25 hit must share meaningful query terms before it becomes evidence.
- Source-labelled, bounded retrieved evidence is supplied to the agent before a
  qualifying answer. No relevant source means the response must identify the
  gap rather than fill it from memory.
- Same-task continuation/replanning: “continue” and meaningful goal overlap
  preserve prior observations and a blocked step can be reopened.

## Tests

- Added retrieval decision, relevance-filter, malformed-result, and substantive
  continuation regression tests.
- Full local-agent suite: 90 tests passed.
- H3 prompt validation remains 124/124 valid.

## Safeguards retained

All retrieval is local and read-only. No framework, model, dependency, or
download was added. The tool whitelist, server-side validation, remote default
deny, render preflight, protected-file protection, and localhost-only HTTP are
unchanged.

## Not claimed

This is not an LLM self-grader. It is a transparent evidence-routing and
deterministic relevance check. A learned hallucination grader and model-driven
planner/replanner remain evaluation-gated future work.
