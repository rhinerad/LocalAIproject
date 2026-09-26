# 2026-09-05bd — Intent-mismatch capture (local JSONL, not a fix)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bd**.

TODO.md item (~440): the local agent does not infer vague requests as well as
Claude/GPT. That item cannot be diagnosed without real before/after examples.
This change only starts collecting those examples from live use.

## What shipped

A GUI button on assistant messages, **this wasn't what I meant**, POSTs to
`/api/intent_mismatch`. That handler reads the already-saved turn and appends
one JSONL record. It does not re-run the model, change routing or prompts,
write memory, or enqueue encrypted `feedback_manager` records.

Each record has:

- `ts` / `flagged_at`
- triggering `user_message`
- full `assistant_message`
- `tool_calls` (the `tool_evidence` already stored on the assistant message)
- `route` (`model`, `tier`, `capability`, `reason`, `host`, `backend`)
- `conversation_id` and `assistant_index`

Log path: `local_agent/runtime/intent_mismatch.jsonl` (append-only, same
shape as `runtime/comfy_mcp_audit.jsonl`).

Desktop `store.append` for the assistant reply now also keeps the SSE
`route` dict on that message so a later flag has the turn's model/tier/
capability instead of the conversation's latest `last_tier`. Empty `{}`
when no route event fired. Older chats without `route` still capture;
`route_incomplete` is true and tier may fall back to `last_tier`.

`APP_REVISION` was not bumped. HTML is served from disk each GET. The new
Python endpoint needs one desktop-agent restart.

No analysis pipeline. No training. No automatic rewrite of the reply.

## Tests

```
python -m unittest test_intent_mismatch test_feedback test_gui_render_hint -v
```

17/17 OK (`test_intent_mismatch` 8/8). Capture writes user/assistant/tools/route/timestamp
without mutating the chat JSON; a specific index is not the later turn; two
flags are two JSONL lines; `memory.remember` and `feedback_manager.enqueue`
are not called; old turns without per-message `route` set `route_incomplete`.

## Files

- `local_agent/intent_mismatch.py`
- `local_agent/server.py`
- `local_agent/static/index.html`
- `local_agent/test_intent_mismatch.py`
- `TODO.md`
