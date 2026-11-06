# 2026-09-05a — PowerInfer hops get a text-only system prompt

Date: 2026-09-05. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py`: **2026-09-05a**.

Audit finding: chats pinned to `backend="powerinfer"` already had
`tool_schemas=[]` in `apply_hop_profile()` and a UI-only status note
("PowerInfer is text-only; native tool schemas are not sent"), but
`msgs[0]` was still the full agentic `system_prompt()` — the same
CONVERSATION_RULES built for models with native tool-calling. The model
was told to "use an available tool" and named `fetch_url`,
`start_current_chat_render`, `extract_video_actions`, and the rest, with
no way to actually call them. README already documents the pin as
text-only. Low-impact today (no accepted sparse model is selectable for
real use), but this would have been live the first time a PowerInfer
bundle entered the picker.

## What shipped

- `POWERINFER_CONVERSATION_RULES` in `local_agent/agent.py`: short,
  honest, no-tools framing in the same shape as
  `LIGHTWEIGHT_CONVERSATION_RULES`. States plainly that no tools are
  available this turn, not to claim an action occurred, and to answer
  directly in text.
- `system_prompt(..., rules=)` accepts an optional rules block. Default
  remains CONVERSATION_RULES / CODING_RULES. PowerInfer passes the
  text-only rules so operating memory, learned lessons, recalled memory,
  and the Equal Shares handbook (when scoped) stay attached.
- `apply_hop_profile()` for `backend=="powerinfer"` still returns
  `tool_schemas=[]` and now also replaces `msgs[0]` with that prompt.
  GPU hops still get `base_system`; CPU/farm hops still get
  `CPU_COMPACT_RULES`. The UI note is unchanged.

## Tests

```
python local_agent/test_native_tool_calling.py -q
  Ran 81 tests
  OK
```

80 existing native-tool assertions held. New
`test_powerinfer_system_prompt_is_text_only_not_tool_assuming` mocks a
`backend="powerinfer"` Decision (no live PowerInfer hardware). Same
operator turn on GPU still receives CONVERSATION_RULES + full native
schemas; CPU and farm still receive `CPU_COMPACT_RULES` + the three
meta-tools. The PowerInfer system message contains the text-only rules
and the project handbook, and does not contain tool-execution
instructions or native tool names.

## Not this PR

Live PowerInfer inference, picker enablement, or a production sparse
bundle. ReluLLaMA-7B remains diagnostic-only; TurboSparse-Mistral stays
parked. No change to routing, schemas, or the UI status note.
