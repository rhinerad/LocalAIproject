# 2026-09-05dl — Do not prune `read_artifact` results (escape-hatch loop)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dl**. Builds the
fix proposed in `CHANGELOG/2026-09-05dj_qwythos_read_artifact_prune_loop.md`.
No `CAP_LOGIC` / farm-routing / Qwythos-prompt change.

## Cause (from 2026-09-05dj)

`read_artifact` is how a model recovers a tool result that
`prune_large_text` replaced with a pointer. Default slice `length=4000`
plus indented JSON is ~4196 chars. Context budget
`MAX_TOOL_RESULT_CONTEXT_CHARS` is **2400**, and prune is all-or-nothing.
The hop loop therefore stored the escape-hatch JSON as a **new** artifact
and fed back another pointer. Qwythos followed each new id until hop 6
with an empty answer (`farm_direct.json`). Any model using
`read_artifact` would hit the same loop.

## Change

`agent._tool_result_for_context(name, result)`: if `name == "read_artifact"`,
return the result unchanged; otherwise `prune_large_text` as before.
Used at both hop-loop tool-result append sites (normal hop and specialist
scope-retry). Other oversized tools still become pointers.

## Tests

`test_native_tool_calling` (from `local_agent/`):

- `test_read_artifact_default_slice_stays_in_next_hop_not_pruned` — default
  4000-char slice is the next `role=tool` content (not `output pruned`);
  no `tool:read_artifact` wrapper file is stored.
- `test_read_artifact_follow_up_page_uses_next_offset_not_wrapper_id` —
  second call keeps the **original** id and `offset=next_offset`; page-2
  text is the original bytes, not nested JSON.
- Existing `test_oversized_tool_result_is_an_artifact_pointer_in_next_hop`
  still prunes non-`read_artifact` results.

`test_native_tool_calling` + `test_artifacts` + `test_source_citation`:
**117 OK**.

## Live verify

No ComfyUI / host GPU / Mac Qwythos turn this pass (the 2026-09-05de
farm turn was 645 s and is not needed to prove the harness). Verification
is the hop loop itself: `agent.answer` with a stub `decide`/`chat_stream`
and **real** `tools.call("read_artifact")` against a stored 8–10k char
blob. That is the same prune site the farm path uses.

## Not done

GUI still cannot farm-route (`POST /api/send` pins a model). Pre-route
Qwythos silence (2026-09-05s) unchanged. Prefix-preserving prune for
`read_file` is still optional follow-up.
