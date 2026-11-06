# 2026-09-05dt — Hop index on JSON SSE events (cw piece 1)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dt**. Builds the
hop-index backend from
`CHANGELOG/2026-09-05cw_hop_index_and_pre_qwythos_route_scope.md` §1.
Does **not** change CAP_LOGIC, farm routing, or Qwythos prompts.
Pre-wait proposal farm route is already **2026-09-05ds** (cw piece 2);
this ticket is the emit wrapper only.

## What changed

`agent.answer` tracks `current_hop` (`None` outside the hop loop).
`emit()` runs payloads through `_with_hop`:

| Kind | Payload | Hop |
|---|---|---|
| `route`, `progress`, `tool` | JSON object | `"hop": N` merged (loop integer; **`null`** before/after the loop) |
| `tool_result`, `token`, `note` | raw text | **unchanged** |

Action-resolver / folderless-render / Sonic Pi early returns fire
`emit("tool")` before the loop, so they get `"hop": null` as cw specified.

`server._copy_hop` / `activity_from_sse`: if the JSON has `"hop"`, copy
it (including JSON `null`). If the key is missing, do not add it — old
persisted chats stay valid. `hop_index` is still accepted as a fallback
alias.

`APP_REVISION` **`2026-09-05-hop-index-r82`** (launcher
`$ExpectedAgentRevision` matched). r81 was the ds farm-attempt route;
this is a second transport-visible field.

No `index.html` change required for the wire (GUI already has optional
`data-hop` grouping from ds). No `trace_id`.

## Tests

From `local_agent/`:

- `test_activity_trace` — copy hop / hop null / missing hop / tool_result
  has no hop field; existing proposal-farm hop=0 still passes
- `test_sse_hop_index_on_json_kinds_across_hops` — real `agent.answer`
  `on_event` log: hop 0 then hop 1 on `route`/`progress`/`tool`;
  `tool_result` JSON does not gain `hop`
- `test_early_return_tool_sse_has_hop_null` — action-resolver `list_dir`
  short-circuit: tool announce `hop: null`, result raw
- `test_launcher_revision` — r82 lockstep

**36** targeted tests OK this pass (`test_activity_trace` + launcher +
the two new hop tests + existing multi-call hop).

## Not done

GUI still cannot farm-route a pinned new chat (`POST /api/send` still
pins). That remains the open 2026-09-05dg/de decision, not this wire.
