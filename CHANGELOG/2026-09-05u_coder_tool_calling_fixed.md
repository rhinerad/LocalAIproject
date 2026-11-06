# 2026-09-05u — Coder-14B tool-calling gap: fixed via content-JSON promoter

## Scope

🔴 lane, Part 1 of the "one more attempt" round. Reviews Grok's own
`CHANGELOG/2026-09-05t_content_json_tool_promoter.md`. No new code from
this entry — documents the operator-facing outcome and updates TODO.md.

## Finding: real fix, at the parser level, model-agnostic

`agent.parse_content_json_tool` runs when native `tool_calls` is empty
and before the legacy `TOOL:` fallback: it promotes a whole-message JSON
object (`{"name": <advertised tool>, "arguments"|"parameters": <object>}`)
to a real tool call, strictly gated (valid JSON, optional fenced block
with no other text, schema name match, required arg keys present, no
extra top-level keys — prose, Python blobs, truncated JSON, arrays, and
unknown names are all correctly ignored).

Live case 3 (`run_code` clamp debug): both
`josiefied-qwen2.5-coder-14b:official-tools` and stock
`qwen2.5-coder:14b` now actually execute `run_code` on the first attempt
(previously `run_code_count=0` in 2026-09-05b/n). 108 tests pass,
including 6 new covering the promoter's gate conditions and a real
agent-loop call-through test.

Because this lives in `agent.py`'s hop loop, not in a model tag, it fixes
tool-calling for **any** model that emits a well-formed JSON object in
`content` instead of native `tool_calls` or `<tool_call>` XML — the
default `:q4_k_m` Coder tag benefits from this without being retagged.
No prompt/`CODING_RULES` edits, no default-tag change.

## Known remaining limitation

The clamp debug loop still didn't finish green — later hops drifted into
other standalone JSON (`capabilities`, `run_safe_check`) after the first
result. That's a tool-choice/reasoning quality issue, not a parser gap —
the promoter did its job on the call it was asked to make.

## TODO.md update

Marks the Coder half of the 2026-09-05g/n tool-calling gap as fixed.
DeepSeek's half (native calls possible but unreliable, per 2026-09-05n)
remains open pending Part 2's final gut-check, dispatched separately.
