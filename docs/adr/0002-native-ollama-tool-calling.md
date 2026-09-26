# ADR 0002 — Native Ollama function calling

**Status:** Accepted

## Decision

Send JSON schemas to Ollama and consume structured `message.tool_calls`.
Support multiple tool calls in a turn. Retain the older text `TOOL:` parser only
as a compatibility fallback for models that do not return native calls. When
native `tool_calls` is empty, also promote a **standalone** content JSON object
`{"name", "arguments"|"parameters"}` that matches an advertised schema (Qwen2.5-Coder
emits this instead of `<tool_call>` XML). That promoter is not the `TOOL:`
fallback and does not change prompts.

## Why

Prompt-only tool conventions consumed context, allowed malformed JSON to become
empty arguments, and limited a turn to one action. Native calls let the model
request several independent read-only observations before responding.

## Consequences

- Schemas are assistance, not authorization: `tools.py` remains the validation
  and whitelist boundary.
- The legacy route remains visible in logs so model compatibility can be
  measured rather than assumed.

## Evidence

`local_agent/tools.py`, `local_agent/ollama_client.py`, `local_agent/agent.py`,
and their native/legacy regression tests.
