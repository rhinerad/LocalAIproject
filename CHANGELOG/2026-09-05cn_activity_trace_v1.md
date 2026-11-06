# 2026-09-05cn — Visible agent activity trace v1

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cn**.

Design: `docs/design_notes/VISIBLE_AGENT_ACTIVITY_TRACE_2026-09-05.md`
(`CHANGELOG/2026-09-05q`, `2026-09-05s`). Does not depend on Orange
tracing PR 2. No `trace_id` on SSE. Did not touch `outputs/equal_shares/**`.
Did not reorder farm Qwythos vs `emit("route")` in `agent.py`.

## What shipped

The desktop GUI maps the live SSE kinds it already receives
(`route` / `progress` / `tool` / `tool_result` / `note` / `queued` /
`error` / `done`) onto expandable lifecycle cards:

| SSE | Card kind | Stamp |
|---|---|---|
| `progress` decide/review/write | `planning` | Proposal — not proof of execution |
| `note` “task plan prepared” | `planning` | Proposal |
| `tool` | `tool_call` | Announced — not yet observed |
| `tool_result` | `tool_result` | Observed result / Observed error |
| `progress` evidence | `verification` | observation |
| GPU/file-edit pending `note` | `waiting_for_permission` | sidebar remains source of truth; turn may already be on CPU |
| `queued` | `queued` | announced |
| `done` | `complete` | Observed result |
| `error` / hop-limit note | `blocked` | Observed error |
| `route` | `route` | Observed result (tier / model / backend / reason / capability / gpu_busy) |

A plan is never shown as proof the step ran. Live tool args are redacted
to keys + path/clip/action/name (no bodies). The same redaction
(`remote_security._redact_args`) is persisted on a new `activity` array
on the assistant message. `openChat` restores `activity` when present;
older chats fall back to stored `tool_evidence` as **observation-only**
cards (no invented announce). Chat-list `last_tier=farm` is FARM, not
CPU. Elapsed time ticks on the live Working… summary from `Date.now()`;
it is not faked and is not restored after refresh.

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-activity-trace-v1-r79`.

## Tests

```
python -m unittest test_activity_trace test_launcher_revision -v
```

21/21 OK. Covers secret-arg redaction, ERROR/REFUSED as observation,
planning vs complete, GPU-permission note vs GPU-gate-block (CPU
fallback is not `blocked`), farm route fields, `tool_evidence` restore
without inventing a proposal, store round-trip, farm listing badge,
and GUI contract strings.

## Live evidence (not “should work”)

Restarted desktop `server.py` to r79 (PID replaced; GPU Ollama was
already up). Chat `aff6ebfe72f64d37`, workspace `general`.

**Before (pre-v1 store):** `chats/bdd1b186505e46ab.json` assistant
message had `tool_evidence` (`search_docs`, `list_dir`) and
`has_activity False`. Old `openChat` rendered content only. v1 restore
now emits observation-only DOM:

```html
<details class="act life" data-kind="tool_result" data-state="result" data-source="observation">
  <summary>Observed result tool_result search_docs</summary>
</details>
<details class="act life" data-kind="tool_result" data-state="result" data-source="observation">
  <summary>Observed result tool_result list_dir</summary>
</details>
```

**GPU routing turn** (`POST /api/send`, model
`huihui_ai/qwen3-abliterated:14b`, prefer auto): SSE included
`route` `tier=gpu` `backend=ollama` `capability=tool` with reason
“GPU free — GPU idle…”. Persisted `activity` began with that route
card. The 14B hop returned empty completion twice (no tool calls);
that is a model miss, not a GUI miss. `last_tier` stayed `gpu`.

**Tool turn** on the same chat (action-resolver `list_dir` of
`local_agent/static`, no extra model load): SSE
`conversation`, `tool`, `tool_result`, `done`. Persisted:

- `tool_call` / `announced` / `proposal` with redacted args
  `{keys:["path"], sha256, json_bytes, path}` — no raw bodies
- `tool_result` / `result` / `observation` summary of the directory
- `complete` / `result` / `observation` (stamped at `store.append`,
  because `done` is pushed after the save)

`GET /api/chat?id=aff6ebfe72f64d37` after the turn restored those
cards (`REFRESH restore kinds` included
`tool_call:announced:proposal`, `tool_result:result:observation`,
`complete:result:observation`).

Farm routing was not observed on these turns: the chat is pinned to
the 14B GPU model, CPU Ollama `:11435` was down, and the list_dir
short-circuit does not emit `route`. Farm is covered by the listing
badge + `activity_from_sse` route test (`backend=farm`). Hop index
and pre-Qwythos `route` emit remain the deferred cut from `2026-09-05s`.

Failed-tool, approval-wait, and queued-media cards are implemented and
unit-tested; they were not re-hit by a live media/GPU-gate turn in this
pass.

## Files

- `local_agent/server.py`
- `local_agent/static/index.html`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_activity_trace.py`
- `TODO.md`
