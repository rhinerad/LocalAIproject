# 2026-08-24 — Local Agent general-scope cleanup

## What changed

- The everyday interface is now labelled **Local Agent — desktop assistant**.
  Existing launch-script names and project files remain in place for compatibility.
- Equal Shares specialist context no longer activates merely because a chat says
  `ComfyUI`, `render`, `voice`, `clip`, or `shot`. It now requires an explicit
  Equal Shares marker: the project name, MiniMax H3, an Equal Shares clip ID,
  an Equal Shares path, or a specific Equal Shares pipeline term.
- Project-document prefetch is now scope-gated, so a generic question about a
  setup or rule cannot inject a film-document search into an unrelated chat.
- Persistent memories categorised `project` are injected only in an explicit
  Equal Shares chat. They are retained on disk and still available through the
  memory tool; this changes only automatic prompt context.
- Recorded the operator's general-first scope rule as a durable, user-confirmed
  memory, so future chats retain the intended boundary.
- Added regression coverage for a generic ComfyUI vacation-video workflow.

## Why

The local agent has grown from a film helper into a general desktop assistant.
The former `ComfyUI` trigger was broad enough to pull the Equal Shares handbook
into unrelated generation requests, causing incorrect story-project references.

## Verification

- Full local-agent test suite must pass.
- `test_general_assistant.py` verifies ordinary creative and generic ComfyUI
  requests do not receive the Equal Shares handbook, while a real clip question
  still does.
- The Equal Shares 124-prompt validation remains required before release.
