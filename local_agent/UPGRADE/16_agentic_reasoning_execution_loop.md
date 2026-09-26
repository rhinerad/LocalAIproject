# Upgrade 16 — Agentic reasoning and execution loop

## Priority, sources, and implementation status

**High priority, requested 2026-08-24.** This is the durable implementation
brief derived from the operator-provided “Agentic Reasoning and Execution Loop”
proposal. It is not permission to weaken any existing safety boundary or expose
hidden chain-of-thought.

The following were inspected as **design references**, not added as runtime
dependencies:

- [smolagents ToolCallingAgent](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py)
  — bounded tool-call/observation steps.
- [LangGraph local Self-RAG example](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_self_rag_local.ipynb)
  — retrieve only when needed and keep evidence checks explicit.
- [LangGraph plan-and-execute example](https://github.com/langchain-ai/langgraph/blob/main/examples/plan-and-execute/plan-and-execute.ipynb)
  — durable plan state separate from individual actions.
- [Aider](https://github.com/aider-ai/aider) — tight, repository-aware execution
  context and verification discipline.
- [Self-RAG](https://github.com/AkariAsai/self-rag),
  [LangGraph](https://github.com/langchain-ai/langgraph),
  [FastMCP](https://github.com/PrefectHQ/fastmcp), and
  [Mem0](https://github.com/mem0ai/mem0) — reference map for later evaluation.

### Stage 1 — implemented 2026-08-24

`agentic_state.py` is a stdlib-only durable checkpoint layer. For a substantive
multi-step request it persists a compact operator-visible goal, up to six
explicit checklist items, and the last eight bounded tool observations under
`local_agent/runtime/agentic_tasks/`. `agent.py` injects the trusted checkpoint
as a second system message, preserves it during trimming, and records every
tool result only after `tools.py` has completed its normal validation.

The follow-up instruction now tells the model to base factual state claims on
the named observations and label unsupported conclusions unverified. This is a
small, deterministic Self-RAG-style grounding guard; it is not a second model
silently judging its own output. Casual chat does not create a task plan, and a
new substantial task replaces the prior checkpoint for that conversation.

No packages were downloaded. Native Ollama schemas remain the function protocol;
`tools.py`, remote default-deny, render preflight, protected-file checks, and
localhost-only HTTP are unchanged.

### Stage 2 — implemented 2026-08-24

The harness now has an explicit, conservative retrieve-decision: questions that
ask about local project rules, history, setup, or documentation prefetch up to
three relevant `search_docs` chunks before the model answers. `search_relevant()`
acts as a deterministic document grader: a BM25 hit must share meaningful query
terms and carries those terms forward as audit metadata. If no source-labelled
chunk survives, the model is told plainly that local documents do not establish
the answer.

The task checkpoint now also distinguishes a continuation from a new goal. A
short “continue” or a substantial request sharing two meaningful goal terms
replans the current task, retains prior observations, and reopens a blocked
step. A dissimilar substantive request starts a new bounded task instead.

### Stage 3 — implemented 2026-08-24

New substantive multi-step tasks now receive one sequential structured plan
proposal from the selected local Ollama chat model. The proposal uses Ollama's
native `format` JSON Schema field, has two to six checklist items, and is
strictly validated before it replaces the deterministic fallback checklist.
The plan is operator-visible in the normal event stream and stored as task
state; it cannot call a tool, choose a path, or execute anything.

Validation rejects planner titles *and success conditions* containing execution
verbs such as render, start, write, delete, install, command, or shell. On a
model failure or malformed JSON, the safe deterministic plan remains active.
The proposal call is sequential under the existing chat-busy guard and follows
the router, so it never runs a second model alongside a render.

### Stage 4 — implemented 2026-08-24

`agentic_eval.py` is a repeatable offline harness baseline. It mocks model calls
and measures five observable properties: two native tool calls in one hop,
source-labelled document retrieval, same-task checkpoint continuation, blocked
failure state, and phone render default-deny. The baseline is deliberately an
infrastructure evaluation, not a claim that the local model has the factual
accuracy or breadth of ChatGPT/Claude.

Run it with `python local_agent/agentic_eval.py`. Its report is machine-readable
and a nonzero exit means a behavior regressed. This runs alongside the full
unit suite and the required 124/124 H3 prompt validation.

### Stage 5 — implemented 2026-08-24

The GUI now offers explicit feedback on an assistant reply. **Helpful** records
an audit signal only. **Correct & remember** asks the operator to write the
short reusable rule that should guide similar future work; only that typed rule
is promoted to persistent memory under `user-confirmed rule`. The reply itself
is never copied to memory and silence is never treated as approval.

Feedback records contain a reply fingerprint, not raw assistant text. Rules that
would weaken safeguards (for example, bypass validation or delete evidence) are
refused. This is an opt-in learning mechanism, not self-modifying code and not
an autonomous permission grant.

## Goal

Make the local agent more reliable across multi-step work and context resets by
using an explicit, observable harness loop:

```
operator goal
  -> assemble scoped context + durable task state
  -> model chooses a native structured tool call or final answer
  -> harness validates and runs only whitelisted tools
  -> tool observation is bounded and attached to working state
  -> evidence/grounding check
  -> compact stale detail into a checkpoint
  -> continue until complete, blocked, or awaiting a human decision
```

The model never executes code by itself. It selects from schemas; the local
harness validates every argument, enforces `tools.py` and remote permissions,
runs the operation, and records the observation.

## Required capabilities

1. **Plan / act / observe loop**
   - Keep native Ollama `message.tool_calls`, including multiple calls in one
     model turn; do not regress to prompt-only `TOOL:` conventions.
   - Maintain a compact task checklist/state for work that takes multiple hops.
   - Distinguish completed, blocked, awaiting-user, and next verification work.
   - Do not expose private reasoning. Show concise action cards, tool results,
     and evidence-based explanations instead.

2. **Grounded answers and verification**
   - State/project/file/URL/media claims must trace to the appropriate local
     tool observation; label an unsupported conclusion as unverified.
   - When evidence conflicts or is incomplete, issue focused follow-up reads or
     searches instead of smoothing over the conflict.
   - Before a consequential final answer, perform an inexpensive evidence check
     when the task has tools available. Never invent a test result.

3. **Safe tool execution**
   - JSON schemas are model hints only. Keep server-side validation, clip-ID and
     document whitelists, protected-file refusal, render preflight, thermal
     guard, localhost-only HTTP, and per-identity remote default-deny.
   - Keep every remote tool attempt audited. A phone never gains render,
     write-file, run-build, or ComfyUI-stop authority unless existing explicit
     desktop policy says so.
   - Preserve the exact-stop and current-chat-render deterministic routes where
     they prevent a model from choosing a documentation placeholder path.

4. **Context and memory management**
   - Bound tool observations before model-context insertion: remove redundant
     whitespace/HTML/boilerplate and retain relevant heads/tails of logs and
     tracebacks. Preserve the complete underlying evidence on disk.
   - Compact older interaction details into a factual task checkpoint, retaining
     the system prompt, schemas, durable operator preferences, current plan,
     recent user turns, and complete native tool-call/result exchanges.
   - Do not equate token trimming with VRAM freeing during a forward pass.
     Routing/unloading remains a between-turn resource decision.
   - Investigate prefix/KV-cache reuse only when supported by the installed local
     runtime and only if it respects GPU arbitration; do not assume it exists.

5. **Tests and acceptance**
   - Unit tests for multi-step task continuation, multiple tools per turn,
     evidence-required claims, conflicting tool observations, bounded output,
     checkpoint restoration after a new chat/restart, and refusal paths.
   - Regression tests must keep legacy fallback, Stop, Regenerate, attachments,
     persistence, remote default-deny, media queue behavior, and render guards.
   - Run `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
     and retain 124/124 valid. Do not start a render merely to test this upgrade.
   - Document measured prompt/context cost and any verified latency effect.

## Non-goals

- No hidden inner-monologue display or storage.
- No shell escape, arbitrary process control, unguarded autonomous rendering,
  model download, evidence deletion, or privilege widening.
- No claim of frontier-model parity without an evidence-backed evaluation.

## Remaining stages

- The safe intake/scoring foundation for real operator tasks is implemented in
  `operator_eval.py`: explicit anonymized cases begin pending, move to approved
  only by an operator action, and score captured tool traces/recovery responses
  only against operator-written assertions. It never reads chats or runs a
  model. Seed it only with operator-approved anonymized cases; never silently
  mine chats. Actual benchmark cases and a live-model run remain operator-gated.

The structured planner is deliberately **not** a completion grader. A model must
not manufacture task success: completion still follows recorded tool
observations and the deterministic task state.
