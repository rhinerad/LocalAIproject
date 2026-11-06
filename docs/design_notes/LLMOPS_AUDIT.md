# LLMOps / AgentOps gap analysis and local pipeline spec — 2026-09-02

## Status

Originally requested earlier this session as a full Explore → Audit →
Propose task. The operator asked to hold Step 3 (this document) until the
Phase 1 engine-architecture milestone closed, and to do Steps 1-2 as a
read-only report in chat only. Phase 1 closed the same day. This document
is Step 3, using the research and audit already done (repeated here in
summary so this file stands alone) plus one additional verification.

## 1. Research summary (from the earlier read-only pass)

- **Tracing/observability**: Arize Phoenix and Langfuse are the dominant
  local-first, self-hostable options, both built on OpenTelemetry/
  OpenInference semantic conventions. Phoenix leans OTel-native and
  framework-agnostic; Langfuse leans stronger on prompt management. Both
  MIT/open-source, both Docker-deployable.
- **LLM-as-judge evals**: DeepEval (50+ metrics, tool-call and RAG-specific
  judges) and Ragas (RAG-specific: context precision/recall, faithfulness,
  answer relevancy) are the standard open frameworks. Consistent caveat
  across sources: a judge score is only useful if it's periodically checked
  against real human judgment, not trusted as ground truth on its own.

## 2. Audit summary (from the earlier read-only pass, plus one new check)

- **No OpenTelemetry, no span/trace concept anywhere in `local_agent/`.**
  The only structured execution log is `loop_controller`'s JSONL
  (`runs/loop_*.jsonl`), scoped to the autonomous goal-loop subsystem, not
  the general chat/tool-call path. The interactive CLI block in `agent.py`
  uses plain `print()`.
- **Evals exist but are fragmented, and none are LLM-as-judge in the
  standard sense.** `agentic_eval.py` mocks every model call (tests harness
  machinery, not output quality). `operator_eval.py` is explicitly manual
  (operator submits a case, hand-scores the answer/tool trace). The
  `judge_transcript` worker-farm workflow (built this session) is
  deterministic regex/pattern-matching over *past* saved transcripts, not a
  live model-graded run against a labeled eval set.
- **No token/cost tracking anywhere**, and it's worse than "not
  aggregated" — the raw numbers aren't even captured. **New verification
  for this document:** `ollama_client.py::chat()` calls Ollama's
  `/api/chat` endpoint, which returns `eval_count`, `prompt_eval_count`,
  `total_duration`, and `eval_duration` in every response — confirmed by
  reading the function end to end. `chat()` discards all of them, returning
  only `(text, tool_calls)`. `artifacts.py` prunes by **character** count
  (a 2,400-char pointer threshold), not token count. There is no per-tool
  or per-turn token ledger anywhere in this codebase.

## 3. Gap analysis

The three requested pillars, honestly scored:

| Pillar | State |
|---|---|
| Structured tracing (spans: retrieval, tool calls, generation) | **Phase A shipped 2026-09-05** (`tracing.py` + `agent.answer()` wiring + MCP audit byte-offset pointers). See CHANGELOG `2026-09-05m` / `2026-09-05y` / `2026-09-05ag` / `2026-09-05ak`. Phase B Phoenix/OTLP is still a future translation layer, not built. |
| Automated LLM-as-judge evals | **Partially missing.** Manual scoring and mocked-harness testing exist; a live model-graded run against a labeled set does not. |
| Token/cost tracking per tool call | **Missing, and the raw data is thrown away at the source**, not just unaggregated. |

## 4. Proposal

### 4a. Local tracing — SQLite span logger first, OTel-compatible shape, Phoenix export as an optional later step

**Status (2026-09-05):** Phase A is implemented. Schema evolved from the
four-kind sketch below (`hop`/`route`/`compact`/`action`, `attributes`,
`span_refs`). MCP generate prompts stay in `comfy_mcp_audit.jsonl` and
are joined by binary byte offset. Phase B (OTLP / Phoenix / Langfuse)
is still not decided and is not in tree.

Do not start by standing up Arize Phoenix in Docker. This project's own
pattern (see `retrieval.py`'s BM25 default, `atomic_io.py`, the general
"no new dependency without an explicit decision" discipline used for
PowerInfer/TinyChatEngine/the RAG reranker) argues for a dependency-free
first cut that can be upgraded later, not a new Docker service as the
first move — Docker Desktop is already running for the worker farm, so
capacity isn't the blocker, but scope creep is: a full observability
platform is a bigger commitment than this codebase has made for anything
else so far.

**Phase A — `local_agent/tracing.py` (new, proposed), stdlib + `sqlite3`
only:**
- One SQLite file (`knowledge/traces.db`, same directory convention as
  `retrieval_index.json`), one `spans` table:
  `(trace_id, span_id, parent_span_id, kind, name, start_ts, end_ts,
  input_summary, output_summary, tokens_in, tokens_out, model, tier,
  error)`. `kind` is one of `turn`, `reason` (a model call), `tool`,
  `retrieval`.
- A context-manager helper (`with tracing.span("reason", model=...) as s:
  ...; s.tokens_in = ...`) so call sites stay small.
- Field names deliberately match OpenTelemetry/OpenInference conventions
  (`span_id`, `parent_span_id`, `start_ts`/`end_ts` as epoch, `kind`
  as a stand-in for OTel's `span.kind`) so a **Phase B** exporter to
  Phoenix/Langfuse over OTLP is a translation layer over this table, not a
  rewrite, if that's ever wanted.
- Redaction: reuse `artifacts.py`'s existing pruning boundary for
  `input_summary`/`output_summary` — never store a full raw prompt/response
  in the trace DB, only the same bounded pointer/summary shape already used
  elsewhere, so this doesn't become a second, less-guarded copy of
  sensitive conversation content.

**Phase B — optional, not decided here**: an OTLP exporter reading Phase
A's SQLite table and forwarding to a self-hosted Arize Phoenix (Docker) or
Langfuse instance, if the SQLite-only view proves insufficient in practice.
New dependency (`opentelemetry-sdk` at minimum, Docker for Phoenix/
Langfuse itself) — needs its own explicit approval when/if proposed, same
as every other new dependency in this project.

### 4b. Local eval script — extend `operator_eval.py`, add an LLM-as-judge pre-score, keep human authoritative

Do not build a separate eval runner from scratch — `operator_eval.py`
already has the case intake/review/scoring structure (`pending` →
`approved` → scored against a captured answer/tool trace) and
`quality_comparison.py` already has the prepare/verify pattern used for
PowerInfer's model comparisons. Extend rather than duplicate:

- New `operator_eval.py` mode: after a case is `approved`, run it live
  against the active model (through `router.decide()`, respecting the
  GPU-busy/render-priority rules every other model call in this codebase
  already follows) and capture a **judge pre-score** using a second,
  CPU-only model call (same pattern as `context_compactor`'s dedicated
  summarizer call) — a structured verdict (`{"score": 0-5, "reasoning":
  "...", "flags": [...]}`) against the case's rubric.
- The pre-score is advisory, stored alongside the case, **never
  auto-accepted** — matches every other "review_required, not a
  conclusion" pattern already established in this codebase (the judge_rubric
  worker-farm findings, PowerInfer's quality-gate results). The operator's
  own manual score remains the one that counts for any promotion decision.
- Periodically compare judge pre-scores against the operator's actual
  scores on the same cases and report the correlation — directly
  addresses the research caveat that an ungrounded LLM judge is worse than
  no judge. If they diverge badly, that's a finding to report, not a
  reason to keep trusting the pre-score.
- This can run against the existing 32-pair TurboSparse calibration data
  format too (same JSONL shape), if/when that becomes relevant to Phase 1
  PowerInfer work — not the primary target, but the format overlap is
  worth knowing about rather than building two incompatible eval-case
  schemas.

### 4c. Pseudo-code — Reason → Act → Observe loop wrapped in spans

Same real current loop shown in `HARNESS_OPTIMIZATION.md` §4c, now
additionally annotated with tracing (Phase A above) and the token capture
`ollama_client.chat()` currently discards:

```
def agent_turn(messages, tools_available):
    trace_id = tracing.new_trace_id()
    with tracing.span("turn", trace_id=trace_id) as turn_span:

        plan = action_resolver.resolve(messages[-1])
        if plan.is_deterministic:
            with tracing.span("tool", trace_id=trace_id, name=plan.tool_name) as s:
                result = tools.call(plan.tool_name, plan.args)
                s.output_summary = summarize(result)
            return finalize(messages, result)

        for hop in range(MAX_HOPS):
            if router.estimate_context_tokens(messages, tool_schemas) > num_ctx:
                with tracing.span("compact", trace_id=trace_id):
                    messages = _trim_context(messages, num_ctx, tool_schemas, emit)

            with tracing.span("reason", trace_id=trace_id, model=route.model) as s:
                response, raw = model.generate_with_raw(messages, tools=scoped_tools(messages))
                # PROPOSED: ollama_client.chat() must return the raw response
                # dict (or a small NamedTuple) alongside (text, tool_calls) so
                # this line can actually populate real numbers instead of
                # discarding them the way it does today:
                s.tokens_in = raw.get("prompt_eval_count")
                s.tokens_out = raw.get("eval_count")
                s.model = route.model
                s.tier = route.tier

            if not response.tool_calls:
                turn_span.output_summary = summarize(response)
                return response

            safe_calls, sequential_calls = partition(response.tool_calls)
            for call in safe_calls:
                if is_farm_eligible(call) and farm.worker_available():
                    with tracing.span("tool", trace_id=trace_id, name=call.name, tier="farm"):
                        schedule_on_farm(call)
                else:
                    with tracing.span("tool", trace_id=trace_id, name=call.name, tier="local"):
                        run_locally(call)

            results = gather_concurrent(safe_calls) + run_sequential(sequential_calls)
            messages = append_results(messages, results, prune=artifacts.prune_large_text)

        return messages
```

The only genuinely new *behavioral* requirement here (not just a wrapper)
is that `ollama_client.chat()` needs to stop discarding `eval_count`/
`prompt_eval_count` — everything else is instrumentation around the
existing real control flow.

## What this document does not do

Does not implement `tracing.py`, the SQLite schema, the `operator_eval.py`
judge-pre-score extension, or the `ollama_client.chat()` return-shape
change. All four are proposals. Does not install any new dependency —
Phase A is deliberately dependency-free; Phase B explicitly requires a
separate future approval.
