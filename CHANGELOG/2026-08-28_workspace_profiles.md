# 2026-08-28 — Workspace profiles for general-project isolation

## What changed

- Conversations now persist a separate `workspace` field: `auto`, `general`,
  or `equal_shares`. Existing chats safely default to `auto`.
- The desktop new-chat controls visibly select the workspace alongside the
  independently pinned model. Both lock after the first message, so switching
  chats cannot silently switch a workspace.
- `agent.answer()` uses an explicit workspace before its existing conservative
  scope inference: `general` prevents Equal Shares handbook/tool-schema
  injection, while `equal_shares` enables it for ordinary follow-ups.
- The server returns the selected workspace in its conversation event and
  passes the persisted value to the agent. No new tool, render path, model load,
  or permission capability was added.

## Verification

- New `test_workspace_profiles.py`: 3/3 pass (General override, Equal Shares
  override, durable separate model/workspace state).
- `test_general_assistant.py`: all seven scope-isolation checks pass.
- `test_context_resilience.py`: all five checks pass.
- `test_native_tool_calling.py`: 28/28 pass.
- `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.
- Current tool catalog remains **52** schemas; no tool was added or removed.

## Deferred deliberately

Read-only workspace inspection, root-path inference, unrelated-project fixtures,
operator evaluation metrics, and memory-section separation remain future work.
