# 2026-08-31 — agent.py/tools.py: repeated-failure loop guard + on-demand artifact retrieval

## What changed

Two gaps identified during a design review of the agentic loop (comparing
`agent.py`'s actual hop loop against a standard "reason → act → observe"
agent-harness spec) were closed. A third item from that same review
(a hard token-budget stop condition) was deliberately **not** added — see
"What was not changed" below.

**1. Repeated-failure loop guard, in `agent.py`.**

Previously nothing detected the model issuing the exact same tool call
(same name, same arguments) and getting an `ERROR` result several hops in a
row. The only stop conditions were "no tool call" and the 6-hop cap
(`MAX_TOOL_HOPS`), so a model stuck retrying an unwinnable call could burn
all 6 hops before giving up.

Added `REPEATED_FAILURE_LIMIT = 3` and a rolling `recent_tool_attempts` list
tracked across hops (not just within one hop, since the router already
re-decides fresh every hop). After each tool call, if the last 3 attempts
are identical in both name and JSON-serialized arguments *and* all three
results started with `ERROR`, the turn ends immediately with a clear
message naming the tool and the last error, instead of continuing to the
hop cap. Two things that must **not** trigger it, verified explicitly:
the same tool called with *different* arguments each time (a legitimate
multi-item task), and a transient failure that succeeds on a later attempt
(2 identical failures followed by a success).

**2. `read_artifact` tool, in `tools.py`.**

`artifacts.prune_large_text` already stores any oversized tool result in
full locally and replaces it in the model's context with a pointer
string (`[... output pruned; artifact_id=...]`). Until now that pointer
was a dead end — the module's own docstring called retrieval "future
purpose-built retrieval," i.e. an acknowledged, not-yet-built gap. There
was no tool of any kind that could resolve an artifact_id back into text.

Added `read_artifact(artifact_id, offset, length)`, registered in `TOOLS`
and `_SCHEMAS` like every other tool. It validates the id format
(`artifact_<16 hex chars>`), refuses a missing/foreign artifact, caps
`length` at 8000 chars, and returns `{text, more_remaining, next_offset,
total_chars, ...}` so the model can page through a large stored result on
request. This is deliberately a paging read, not an automatic re-inject or
summary: the model must explicitly ask for a bounded slice, so it always
knows exactly how much of the original it has seen, rather than being
handed an arbitrary unrequested chunk it could mistake for the whole
result — the operator's original constraint was specifically "we cannot
afford hallucinated tool outputs," and auto-injecting a partial chunk the
model didn't ask for would reintroduce exactly that risk.

## Why

Requested after a design-review conversation compared this codebase against
a standard local-agent-harness spec (agentic loop, tool callbacks, context
compaction/memory). The loop structure, tool-error passback, and
history-summarization/memory pieces already matched the spec closely on
inspection. These were the two places where the actual code fell short of
it for a defensible-but-real reason (no loop-detection at all; a
documented-but-unbuilt retrieval seam) rather than by deliberate design.

## What was not changed, and why

**No hard token-budget stop condition was added to the hop loop.** The
review found `router.estimate_context_tokens()` is already computed every
hop and used to trigger `_trim_context()` when the conversation would
exceed the model's `num_ctx` — trimming and continuing, never stopping the
turn. Adding a second, redundant "give up after N total tokens" condition
on top of that was judged unnecessary: the hop cap (6) already bounds the
number of model calls, and each individual call's context is already
bounded to `num_ctx` by the existing trim pass, so total resource use per
turn is already bounded without an additional stop condition. This is
flagged here explicitly rather than silently skipped, per the instruction
to leave alone anything with a good reason behind its current shape.

## What was verified

Sandbox limitation (documented repeatedly in this CHANGELOG): this review
environment's mount cannot delete any file, so `router.set_chat_busy()`'s
`finally`-block `unlink()` errors on every `agent.answer()` call here —
unrelated to this change, reproduced with a plain `touch && rm` on an
unrelated file in `runtime/`. Worked around for verification by patching
`router.set_chat_busy` to a no-op, exactly as done for the two prior
`agent.py` fixes this week.

With that workaround:
- `python3 -m py_compile agent.py tools.py` — clean.
- `tools.schemas()` still returns exactly one schema per tool
  (`len(tools.TOOLS) == len(tools.schemas())`), confirming `read_artifact`
  is fully wired into both the dispatch table and the native tool-calling
  schema sent to the model.
- A 12-check standalone script (bypassing `unittest`'s teardown issue)
  covered: the guard firing at exactly 3 identical failures and not before;
  `chat_stream` being invoked exactly `REPEATED_FAILURE_LIMIT` times, not 6;
  varying-argument failures reaching the normal hop cap instead of
  triggering the guard; a transient failure that recovers on attempt 3 not
  triggering the guard; `read_artifact` paging correctly (`next_offset`,
  `more_remaining`); and all four `read_artifact` error paths (malformed id,
  unknown id, offset past the end, length over the 8000-char cap). All 12
  passed.
- Added the same four cases as permanent tests in
  `test_native_tool_calling.py`
  (`test_repeated_identical_failing_tool_call_stops_the_loop_early`,
  `test_failing_tool_call_with_varying_arguments_is_not_treated_as_stuck`,
  `test_failing_tool_call_that_then_succeeds_is_not_treated_as_stuck`,
  `test_read_artifact_pages_through_a_pruned_tool_result`) and ran the full
  file with the same `set_chat_busy` workaround: **35/35 pass** (31
  pre-existing + 4 new), no regressions.
- Ran `test_run_code.py` (14/14) and `test_agentic_state.py` (11/11) as a
  sanity check that nothing adjacent broke; both fully pass. `test_media_
  analysis.py` has 6 pre-existing failures in this sandbox (unrelated
  `unlink()` permission errors on other files, a vision model genuinely not
  installed in this review environment, and a Windows-path-separator
  assertion) — confirmed unrelated to this change by inspecting each
  traceback; none touch `agent.py`'s hop loop, `tools.py`'s dispatch, or
  `artifacts.py`.

## Real-machine verification

Run by the operator directly on the Windows workstation (no sandbox
workaround needed there, since `runtime/` files can actually be deleted):

```powershell
cd "...\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent"
python -m unittest test_native_tool_calling test_run_code test_agentic_state -v
```

Result: all three suites passed clean (`OK`), including the 4 new tests in
`test_native_tool_calling.py`, with no `set_chat_busy` workaround in play.
This closes the one item left unverified above — the fix is confirmed on
the real target environment, not just in the review sandbox.
