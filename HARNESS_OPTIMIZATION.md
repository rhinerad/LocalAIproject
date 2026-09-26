# Harness optimization — gap analysis and spec, 2026-09-02

## Status

Originally requested earlier in this session, held per operator instruction
until Phase 1 (engine architecture) closed. Phase 1 closed 2026-09-02
(decision: stay on Ollama with current models). This is that deferred
Explore → Audit → Propose deliverable, done now.

**§4a implemented 2026-09-03** (`CHANGELOG/2026-09-03aw_farm_routing_caller.md`,
current-state `docs/ARCHITECTURE.md`). Do not re-derive a farm-routing
caller: `agent._maybe_start_farm_summary_prefetch` +
`farm_offload.should_route` already decide farm vs local.
Summarize is prefetch-only (Mac cold ~55s must not block the turn);
embed may block `search_docs` when `farm_status.json` is healthy.
This file remains the 2026-09-02 proposal snapshot; the live picture is
ARCHITECTURE.md.

## 1. Explore & research

**LangChain Deep Agents.** Addresses context bloat primarily through
subagent isolation — a subagent does the token-heavy work (web search, file
reads) and the main agent receives only the final result, not the raw
output. Also ships an on-demand `compact_conversation` tool an agent can
trigger itself (e.g. between tasks) rather than only compacting reactively
at a fixed threshold.

**Letta (formerly MemGPT).** A full agent runtime, not just a memory
library — agents run inside Letta rather than calling it. Its hierarchical
memory model borrows from OS design: main context ("RAM": system prompt +
recent messages + a writable working-context block), recall storage
("disk": a searchable database of past messages), and archival storage
("cold storage": a vector-indexed store for documents/long-term knowledge).
The key idea worth taking, independent of adopting Letta itself, is a
**writable working-context block the agent can edit**, distinct from the
raw message buffer — not just a passive summary.

**Progressive tool disclosure.** Real, current pattern (2026):
"progressive disclosure — letting the agent recursively discover context
across layers — outperforms loading everything upfront," and "fewer, more
expressive tools beat a long menu of narrow ones." `OpenHarness`
(`HKUDS/OpenHarness`) is a real, verifiable open-source implementation of
this — MCP client with progressive tool discovery and a skill loader.
**Correction on sourcing:** the originally-requested "RoboCFO" could not be
verified as a real project after a direct search — it does not appear to
exist under that name, or isn't findable. Rather than invent details about
it, this section relies on OpenHarness and the general literature instead;
if "RoboCFO" refers to something specific, point me at it and I'll fold in
the real details.

**Supervisor / fan-out for background work.** `revfactory/harness` (real,
verified) generates team architectures including an explicit supervisor
pattern and fan-out/fan-in for distributing work across specialized agents.
The general pattern — a coordinator that routes bounded, independent
sub-tasks to concurrent workers rather than running everything serially in
the main loop — is well established (Azure's "Scheduler Agent Supervisor"
pattern is the classical description of the same shape).

## 2. Audit — what this codebase already has

This is the important finding: **most of what the original request asked
for already exists, in a working and (mostly) tested form.** The honest
framing is "extend and connect what's built," not "build from zero."

| Requested capability | Status here |
|---|---|
| Context compaction middleware, threshold-triggered | **Built.** `local_agent/context_compactor.py` + `agent.py::_trim_context`. Triggers reactively when `router.estimate_context_tokens(msgs, tool_schemas) > num_ctx` (the model's actual adaptive context window, not a guessed constant like the originally-proposed fixed 6,000 tokens) — arguably a better trigger, since it's tied to the real budget rather than an arbitrary number. Uses a dedicated CPU-only `llama3.1:8b` helper to produce a structured digest (goal, decisions, open_questions, tool_state, hard_constraints, notable_files), replacing older messages while preserving the system prompt and the current tool-call/result pair intact. Falls back to deterministic truncation if the summarizer model isn't installed — never blocks a turn on it. |
| Oversized tool-output handling | **Built**, adjacent capability. `artifacts.py` (Pillar 2) prunes large tool outputs to a ≤2,400-char pointer with a SHA-1 fingerprint and (as of this session's source-citation work) an embedded source label, retrievable in full via `read_artifact`. |
| Autonomous fact/memory extraction | **Built.** `memory_extractor.py` (Pillar 3) — async, capped, CPU-only, rejects sensitive/transient facts before promotion to persistent memory. |
| A Letta-style "writable working-context block" | **Partially built, not exactly this shape.** `operating_memory.py` exists (not audited in depth here) and the digest from Pillar 1 is regenerated, not agent-editable mid-turn. Closest gap to the Letta pattern specifically — see proposal below. |
| Progressive tool disclosure ("don't load 50 schemas at once") | **Built**, via a different mechanism than the research examples. `tools.PROJECT_ONLY_TOOLS` hides an entire category of specialist tools (`search_docs`, `agentic_search_docs`, `run_build`, etc.) from the schema sent to an ordinary general-purpose chat — they only appear in an explicitly project-scoped chat. This is coarser than per-step recursive discovery but achieves the same goal (fewer irrelevant schemas in context) and is already measured to reduce false tool selection by small local models (see `CHANGELOG/2026-08-31_...` project-scope work). |
| Parallel tool execution within one turn | **Built.** `agent.py`'s hop loop runs every tool call in `tools.CONCURRENCY_SAFE_TOOLS` (pure reads: files, docs, web, memory listings) concurrently in a thread pool; writes/renders/GPU-touching calls stay sequential. Fixed a real index-cache race during this work (`retrieval._INDEX_LOCK`). |
| Bounded coordinator/worker fan-out for sub-questions | **Built.** `dispatch_subtasks` (`subtask_dispatch.py`) — up to 5 independent sub-questions run concurrently on tool-free CPU workers. Deliberately narrow (no recursive dispatch, hardcoded off the GPU). |
| Bounded multi-round agentic loops (retrieve/reason/retry) | **Built, twice.** `deep_research.py` (web-scoped) and, as of this session, `agentic_retrieval.py` (local-docs-scoped) — both plan→gather→grade→retry with capped rounds, routed through `router.decide()` so a render still owns the GPU. |
| Supervisor/fan-out to background/secondary machines | **Built, and summarize/embed now route.** `local_agent/worker_farm/` is a live Celery/Redis system over WireGuard to `mac_worker`. Queues include `summarize` and `embed` (plus `distill`, `probe`, `judge`). Workstation classifier: `farm_offload.should_route` reading `farm_status.json`. See Status banner / `CHANGELOG/2026-09-03aw_farm_routing_caller.md`. |
| Structured tracing/observability of the loop | **Not built** — confirmed gap, unchanged from the earlier LLMOps audit this session: no OpenTelemetry, no span/trace concept, no per-tool latency/token capture outside the narrow `loop_controller` JSONL log. Out of scope for this document (tracked separately, `LLMOPS_AUDIT.md` still not written — see that thread). |

## 3. Gap analysis

Two real, narrow gaps, not a rebuild:

1. **No mechanism routes a lightweight background task (summarization,
   embedding generation) to the worker farm automatically.** **Closed
   2026-09-03aw.** Classifier is `farm_offload.should_route` (reads
   `farm_status.json`, not live Celery inspect). Summarize: hop-loop
   prefetch at 80% ctx via `agent._maybe_start_farm_summary_prefetch`;
   overflow consumes a ready result or goes local — never a sync farm
   wait. Embed: `EmbeddingScorer.vectors_for` tries the farm for stale
   chunks, then local `_embed`. Same None-fallback as HybridScorer
   lexical-only.
2. **No agent-editable working-context block distinct from the
   regenerated Pillar-1 digest.** Minor relative to (1); Letta's specific
   contribution here is that the agent itself can edit a persistent
   scratch block, not just receive a fresh model-generated summary each
   time context fills.

Everything else the original request asked for either already exists
(context compaction, progressive tool disclosure, parallel execution,
bounded agentic loops) or was already flagged as a separate, larger gap
(structured tracing — a different document's scope).

## 4. Proposal

### 4a. Supervisor routing — extend the existing worker farm, don't build a new daemon

Do **not** build a new ZeroMQ/FastAPI daemon (the original request's Phase
2 spec named that transport) — `TODO.md` already flagged this
inconsistency when the RAG upgrade's "swarm offload" item was scoped. The
farm's Celery/Redis-over-WireGuard transport is live, tested, and already
proven with `mac_worker`. Concretely:

- Add a `summarize` queue (mirrors the existing `judge` queue's shape —
  see `local_agent/worker_farm/tasks.py`) that runs Pillar 1's compaction
  prompt against a batch of old messages, off the workstation.
- Add an `embed` queue for `EmbeddingScorer`'s chunk-embedding backlog
  (Stage 1 of the RAG upgrade) — embedding new/changed doc chunks is
  exactly the kind of bounded, stateless, CPU-only background work the
  farm was built for, and `mac_worker`'s 16 GB RAM is enough for
  `nomic-embed-text`.
- A lightweight classifier in `agent.py` (not a new service) decides
  farm-eligible vs. synchronous: task is farm-eligible if it's CPU-only,
  has no dependency on the current turn's live state, and a completed farm
  worker is currently connected (checked via the existing Celery
  inspect/ping, not a new health system). Otherwise, fall back to doing it
  locally exactly as today — never block a turn waiting on a farm round
  trip for something the workstation can already do instantly.

### 4b. Working-context block (smaller, optional follow-up)

Extend `operating_memory.py` (not audited in depth for this document) to
accept an explicit agent-editable field alongside Pillar 1's regenerated
digest, if/when a concrete failure case shows the regenerated-each-time
digest is losing something an editable block would keep. Not urgent —
flagged, not specced in detail, since no observed failure motivates it yet
the way the RAG gaps had concrete evidence.

### 4c. Pseudo-code — Reason → Act → Observe loop with these hooks

This reflects the loop as it **actually exists** in `agent.py` today
(hop-based, with real compaction/concurrency/action-resolution), annotated
with where the proposal in 4a plugs in. It is not a rewrite.

```
def agent_turn(messages, tools_available):
    # ACT-before-REASON shortcut that already exists: direct requests skip
    # straight to a deterministic tool plan (action_resolver.py) when the
    # intent is unambiguous, instead of spending a model call to rediscover
    # what the operator already said plainly.
    plan = action_resolver.resolve(messages[-1])
    if plan.is_deterministic:
        result = tools.call(plan.tool_name, plan.args)
        return finalize(messages, result)

    for hop in range(MAX_HOPS):
        # REASON — compact first if the prompt won't fit (existing, reactive,
        # threshold = the model's real adaptive num_ctx, not a guessed constant)
        if router.estimate_context_tokens(messages, tool_schemas) > num_ctx:
            messages = _trim_context(messages, num_ctx, tool_schemas, emit)

        response = model.generate(messages, tools=scoped_tools(messages))
        # scoped_tools() is the existing PROJECT_ONLY_TOOLS filter — already
        # "progressive disclosure," just coarse-grained (chat-scope, not
        # per-hop) rather than per-step recursive discovery.

        if not response.tool_calls:
            return response  # OBSERVE: nothing to act on, done

        # ACT — split calls by safety class (existing CONCURRENCY_SAFE_TOOLS)
        safe_calls, sequential_calls = partition(response.tool_calls)

        # PROPOSED (4a): before dispatch, classify each safe call for
        # farm-eligibility instead of always running locally.
        for call in safe_calls:
            if is_farm_eligible(call) and farm.worker_available():
                schedule_on_farm(call)          # e.g. summarize/embed queue
            else:
                run_locally(call)               # existing thread-pool path

        results = gather_concurrent(safe_calls) + run_sequential(sequential_calls)

        # OBSERVE — results feed back in; existing artifact-pruning (Pillar 2)
        # already keeps oversized results from re-bloating context here.
        messages = append_results(messages, results, prune=artifacts.prune_large_text)

    return messages  # hop budget exhausted; existing behavior unchanged
```

The only new element versus the current real loop is the `is_farm_eligible`
/ `schedule_on_farm` branch in the ACT phase — everything else in the
pseudo-code is a direct description of code that already runs today.

## What this document does not do

Written as a proposal. §4a (queues + classifier) is now built — see the
Status banner. The `operating_memory.py` extension in §4b is still
proposed, not built. Does not touch `LLMOPS_AUDIT.md` (structured tracing
remains a separate deliverable). Does not change any default behavior of
`agent.py`'s existing loop.
