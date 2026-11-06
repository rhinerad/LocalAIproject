# 2026-09-02 — LLMOPS_AUDIT.md written (deferred deliverable, now unblocked)

## Scope

The other deliverable held pending Phase 1 closure this session (alongside
`HARNESS_OPTIMIZATION.md`, already written). Steps 1-2 (research, codebase
audit) were done earlier as a read-only chat report at the operator's
explicit request ("audit only, no spec yet"); this is Step 3, using that
same research/audit plus one new verification, now that Phase 1 has
closed. Documentation only — no code written, no dependency installed.

## New verification beyond the earlier read-only pass

Read `ollama_client.py::chat()` end to end: it calls Ollama's `/api/chat`,
which returns `eval_count`, `prompt_eval_count`, `total_duration`, and
`eval_duration` in every response. The function discards all of them,
returning only `(text, tool_calls)`. This sharpens the earlier "no token
tracking" finding — the gap isn't that data needs aggregating, it's that
the raw numbers are thrown away at the one call site that has them.

## What was written

`LLMOPS_AUDIT.md`: research summary, audit summary (tracing is a real
zero — unlike the RAG/harness audits where most of the ask turned out to
already exist, this one had no fallback existing implementation), and a
three-part proposal:
- **4a**: a dependency-free SQLite span logger (`local_agent/tracing.py`,
  proposed) with OTel/OpenInference-shaped fields, explicitly *not*
  starting with a Docker Phoenix/Langfuse instance — consistent with this
  project's pattern of a lightweight first cut before any new dependency,
  with an optional OTLP-export upgrade path flagged but not decided.
- **4b**: extend `operator_eval.py` (not build a new eval runner) with an
  LLM-as-judge pre-score that's advisory only and gets its correlation
  against real human scores tracked over time — directly addresses the
  research finding that an unchecked judge score is worse than none.
- **4c**: pseudo-code for the Reason→Act→Observe loop with tracing spans
  added, built on the same real-current-loop description
  `HARNESS_OPTIMIZATION.md` used, with one concrete required code change
  identified (`ollama_client.chat()`'s discarded token fields) rather than
  everything being a pure wrapper.

`TODO.md`: new "LLMOps / observability" section with three tracked items
(the tracing module, the `ollama_client.chat()` fix, the eval pre-score
extension), all unimplemented.

## What was not done

No code written. No new dependency installed or added to any requirements
file. No SQLite file created. `operator_eval.py` and `ollama_client.py`
untouched.
