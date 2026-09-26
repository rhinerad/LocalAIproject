# 2026-08-19 — Replace text-protocol tool calling with Ollama native function calling

## Problem

`agent.py` asked the model to emit `TOOL: name {json}` on its own line and
parsed it with a regex. Three failure modes observed in the first live run:

1. **Silent fallback to memory.** Models that didn't comply (qwen3:8b with
   thinking mode) answered from their own reasoning instead of calling the tool.
   The only symptom was a wrong answer — the protocol failure was invisible.
2. **One tool per hop.** A question like "compare the ladders for 00B and 00A"
   consumed two hops (one `clip_info` + one `duration_ladder`) instead of one.
   With `MAX_TOOL_HOPS = 4` that left only two hops for follow-up.
3. **Context overhead from instructions.** The system prompt included a 14-tool
   description plus explicit format instructions so the model would know the
   protocol. Those instructions were necessary only because the protocol was
   text-based.

## What changed

### 1. tools.py — JSON schemas for all 14 tools

Added `_SCHEMAS` dict and `schemas()` function. `schemas()` returns the
OpenAI-style array Ollama's `/api/chat` `tools` parameter expects:

```json
[{"type": "function", "function": {"name": "...", "description": "...",
  "parameters": {"type": "object", "properties": {...}, "required": [...]}}}]
```

Enum constraints in the schemas match the real whitelists exactly:
- `run_build.action` enum == `sorted(BUILD.keys())` (9 values) ✓
- `propose_gpu.action` enum == `sorted(GPU.keys())` (2 values) ✓
- `read_doc.name` enum == the `allowed` dict keys (6 values) ✓

No guard is relaxed. The clip-id regex, the doc whitelist, the build-action
whitelist, and `write_file`'s `_PROTECTED_NAMES` check all remain exactly as
before. A JSON schema is a hint to the model, not a substitute for validation.

### 2. ollama_client.py — ToolCall class + tools= parameter

**New class `ToolCall`:** yielded by `chat_stream()` when the model invokes tools.
Callers check `isinstance(piece, oll.ToolCall)` to separate content tokens from
tool calls. Arguments are normalised to `dict` by `chat_stream()` — callers
never see raw JSON strings.

**`chat()` signature change:** now returns `(text: str, tool_calls: list)` tuple.
The single caller that used it (`draft_prompt`) was updated to `text, _ = oll.chat(...)`.
Drafting intentionally omits `tools=` so the model generates prompt text, not calls.

**`chat_stream()` changes:** added `tools=` parameter passed through to the
request body. Streams content tokens as before; accumulates `tool_calls` from
every chunk (Ollama usually sends them in the final `done=True` chunk); yields a
`ToolCall` object after the text tokens if any calls were made.

### 3. agent.py — rewritten answer() loop

`MAX_TOOL_HOPS` raised from 4 to 6. Hops now count **model turns**, not individual
tool calls. A question that triggers two tool calls in one turn uses 1 hop, not 2.

**Main loop changes:**

```
for hop in range(MAX_TOOL_HOPS + 1):
    stream response → collect text tokens + optional ToolCall
    if no tool calls and no legacy TOOL: pattern → return prose answer
    if hop >= MAX_TOOL_HOPS → emit note, return current answer
    for each tool call in hop_calls:
        emit "tool" card, execute, emit "tool_result"
    append assistant message (with tool_calls if native path)
    append one {"role":"tool"} message per result
    append follow-up user prompt → next hop
```

**Legacy fallback:** if no native `tool_calls` in the response, `parse_tool()` is
still called on the text. If it matches `TOOL: name {json}`, the call is
processed normally and a `"note"` event is emitted — `"legacy text protocol
(model does not support native calling)"`. The operator sees it in the GUI; the
answer is still correct.

The legacy fallback uses the old message format (user-injected result) rather than
the `{"role":"tool"}` format, since a model that can't produce `tool_calls` likely
can't consume `tool` role messages either.

**`CONVERSATION_RULES` simplified:** the entire "Mandatory tool use — do not
answer these from memory" section with its NEVER statements existed solely because
the text protocol was unreliable. It is replaced with a short paragraph. The
system prompt no longer includes the tool list or protocol instructions.

### 4. System prompt size

| Part | Before | After | Change |
|---|---|---|---|
| KNOWLEDGE pack | ~9,500 chars | ~9,500 chars | — |
| CONVERSATION_RULES | ~1,800 chars | ~650 chars | −1,150 chars |
| Tool list + protocol | ~1,691 chars | 0 | −1,691 chars |
| **System prompt total** | **~13,000 chars** | **~10,961 chars** | **−2,030 chars** |
| Tool schemas (per request) | 0 | ~5,308 chars | +5,308 chars |
| **Net per request** | | | **+3,278 chars (~820 tokens)** |

The schemas are larger than the old instruction block. The trade-off is
intentional: structured JSON that the model was trained to use, versus natural
language instructions the model may ignore. The quality improvement is more
valuable than the token count.

---

## Verified (this session, code and simulation)

| Check | Result |
|---|---|
| `python local_agent/tools.py` — describe() runs cleanly | ✓ 14 tools listed |
| `tools.schemas()` returns 14 schemas | ✓ |
| All schemas have `parameters` key | ✓ |
| `run_build` enum matches `sorted(BUILD.keys())` | ✓ 9 values |
| `propose_gpu` enum matches `sorted(GPU.keys())` | ✓ 2 values |
| `read_doc` enum matches `allowed` dict | ✓ 6 values |
| **Guard rails — 8/8 refused** | ✓ |
| → unknown tool | ✓ |
| → path traversal clip id | ✓ |
| → doc name `/etc/passwd` | ✓ |
| → build action `rm -rf /` | ✓ |
| → `write_file` on `manifest.json` | ✓ protected |
| → `fetch_url` with `file://` | ✓ |
| → `web_search` empty query | ✓ |
| → `read_file` nonexistent path | ✓ |
| **Two tool calls in one hop** (simulated) | ✓ 2 cards, 1 hop |
| **Legacy TOOL: fallback** (simulated) | ✓ note emitted, result correct |
| `parse_tool()` — 6 cases | ✓ all pass |
| **124/124 prompts still valid** | ✓ |

## Not yet verified (requires live Ollama)

- A live question through the GUI produces `message.tool_calls` in the response
  (depends on model support: dolphin3:latest, qwen2.5-coder:14b).
- Two-part question ("compare the ladders for 00B and 00A") triggers two calls
  in one hop. Simulated and confirmed in code; not exercised against real model.
- GPU-tier model (qwen2.5-coder:14b) follows the native protocol. Only the CPU
  tier was live-tested in the 2026-08-19 first run.
- Stop, Regenerate, attachments: server.py and store.py unchanged; these paths
  are unaffected by the agent loop rewrite. No re-verification needed.

## Files changed

| File | What changed |
|---|---|
| `local_agent/tools.py` | Added `_SCHEMAS` dict (14 entries) and `schemas()` function |
| `local_agent/ollama_client.py` | Added `ToolCall` class; `chat()` returns tuple; `chat_stream()` yields `ToolCall`; both accept `tools=` |
| `local_agent/agent.py` | `MAX_TOOL_HOPS` 4→6; `CONVERSATION_RULES` simplified; `system_prompt()` drops tool list; `answer()` loop rewritten for native calling + legacy fallback; `draft_prompt()` updated for new `chat()` signature |
