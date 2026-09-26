# 2026-08-27 — Local agent general-project scope isolation

## Problem

An unrelated Harmontown dataset/LoRA request received Equal Shares project
state. The agent had general-scope wording in `agent.py`, but its always-on
generated knowledge file still declared it to be the Equal Shares assistant.
Every chat also received Equal Shares-only tool schemas, and general prior-chat
retrieval could inject an Equal Shares conversation based on broad shared words.

## Changed

- `build_knowledge_pack.py` now writes the detailed handbook to
  `knowledge/EQUAL_SHARES_REFERENCE.md`, with an explicit project-only header.
- `agent.py` injects that file only for explicit Equal Shares scope; ordinary
  chats receive neither the handbook nor project-specific operating-memory
  lines.
- `tools.schemas(include_project=False)` omits Equal Shares-only actions from
  an ordinary model turn. `tools.call()` and all server-side safeguards are
  unchanged.
- `chat_retrieval.search(..., include_project=False)` excludes prior chats
  containing explicit Equal Shares markers.
- Added Upgrade 21 as the tracked roadmap for explicit multi-workspace support.

## Verification planned in this session

- General-chat regression must prove an unrelated story and a general ComfyUI
  request do not receive the handbook or specialist schemas.
- Explicit Equal Shares clip questions must still receive both.
- Prior-chat retrieval must exclude an Equal Shares chat for an ordinary VLM
  request but retain it for scoped project work.
- The existing native-tool, context, agentic, and H3 validation suites must
  remain green.

## Not changed

No render path, Equal Shares evidence, model routing, remote permissions,
tool-dispatch validation, or GPU behavior changed. This is a context and schema
presentation correction only.
