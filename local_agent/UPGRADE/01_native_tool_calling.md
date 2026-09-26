# Upgrade 1 — native function calling. No internet needed.

Paste everything below the line into Claude Code.

---

Replace the local agent's hand-rolled text tool protocol with **Ollama's native
function calling**. No downloads. Work straight through; do not stop to check in.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Read `local_agent/README.md` and `local_agent/agent.py` first.

## The problem

`agent.py` asks the model to emit `TOOL: name {json}` on a line of its own and
parses it with `TOOL_RE`. That is fragile by construction:

- a model that ignores the convention silently answers from memory instead —
  observed with `qwen3:8b`, and the reason the current prompt is full of shouty
  `NEVER answer from memory` rules
- only **one** tool per hop, so multi-step questions burn the whole hop budget
- malformed JSON degrades to `{}` and the tool runs with no arguments
- the protocol string eats context in every single request

Ollama's `/api/chat` accepts a `tools` array of JSON schemas and returns
structured `message.tool_calls`. Models trained for it comply far more reliably
than prompt instructions can achieve.

## Job 1 — schemas in `tools.py`

Every entry in `TOOLS` currently carries a human description string. Add a proper
**JSON Schema** for each of the 14: parameter names, types, which are required,
and enums where the value set is fixed (`run_build.action`, `propose_gpu.action`,
`read_doc.name`).

Keep the existing description text — it becomes the schema's `description`.

Add `tools.schemas()` returning the OpenAI-style array Ollama expects:

```python
[{"type": "function", "function": {"name": ..., "description": ...,
  "parameters": {"type": "object", "properties": {...}, "required": [...]}}}]
```

**Do not change what any tool does, and do not relax any guard.** The clip-id
regex, the doc whitelist, the build-action whitelist and the protected-file check
in `write_file` all stay exactly as they are. A JSON schema is a hint to the
model, never a substitute for validation.

## Job 2 — native calls in `ollama_client.py`

Add `tools=` to `chat()` and `chat_stream()`, passed through to the request body.

Streaming plus tool calls needs care: Ollama emits tool calls in the message
object, sometimes with no content tokens at all. Make sure a turn that is purely
a tool call does not render as an empty reply.

## Job 3 — rewrite the loop in `agent.py`

- Pass `tools.schemas()` on every request.
- Read `message.tool_calls` instead of regex-parsing the text.
- **Support multiple tool calls per turn.** Run them all, append one
  `{"role": "tool", "name": ..., "content": ...}` message per result, and
  continue. This is the main capability gain — "compare 00B and 27E" becomes one
  hop instead of two.
- Raise `MAX_TOOL_HOPS` to 6 now that hops are not wasted one-per-tool.
- **Keep a fallback.** If a model returns no `tool_calls` but its text matches
  the old `TOOL:` pattern, honour it. Some models will not support the native
  path and must still work. Log which path was used.
- Delete the now-redundant nagging from `CONVERSATION_RULES` — the whole
  "NEVER answer from memory / NEVER describe what a tool would return" block
  exists only because the text protocol was unreliable. Keep the short version:
  prefer tools for state, counts, clips and files. Reclaimed context is the point.

## Job 4 — the GUI keeps working

`server.py` streams `tool` and `tool_result` events and `static/index.html`
renders them as action cards. Preserve that. With several calls in one turn,
emit one card per call.

## Verify — all of it, no shortcuts

```powershell
python local_agent\tools.py
python -c "import sys;sys.path.insert(0,'local_agent');import tools,json;print(json.dumps(tools.schemas(),indent=2)[:1500])"
```

- [ ] all 14 tools have a valid schema; every enum matches the real whitelist
- [ ] a live question through the GUI produces a real `tool_calls` response
- [ ] a two-part question ("compare the ladders for 00B and 00A") triggers **two
      tool calls in one turn** and both results reach the answer
- [ ] the legacy `TOOL:` fallback still fires for a model that does not support
      native calling — test by stubbing a reply
- [ ] **the guard rails still refuse**: unknown tool, clip id `../etc`, doc name
      `/etc/passwd`, build action `rm -rf /`, and `write_file` onto a protected
      manifest
- [ ] Stop, Regenerate, attachments and persistence all still work
- [ ] `python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v`
      still reports **124/124 valid**

Then measure and report: how many tokens the system prompt lost, and whether the
model called tools on questions where it previously answered from memory. Give
the numbers.

## Do not stop

A failing test is a task, not a stopping point. Stop only when every box above is
ticked and you have written the `CHANGELOG/` entry.
