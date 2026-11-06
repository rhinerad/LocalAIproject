# 2026-09-01 — Stop assuming ComfyUI / H3 / Equal Shares is the current job

## What changed

Live local-agent context no longer treats Equal Shares / MiniMax H3 / ComfyUI
as the operating purpose or as a render in progress.

- `GROK_STATUS.md` Current now leads with the general-purpose assistant and
  does not mention Equal Shares. Stay-out-of-the-way keeps one line: do not
  touch ComfyUI / Equal Shares / H3 / any render pipeline unless that is the
  actual current topic. Historical notes were left in place.
- `AGENTS.md` (auto-loaded by Codex) is retitled and has a 2026-09-01 scope
  notice. The 2026-08-16 soundtrack "Current job" section is marked superseded.
- `local_agent/knowledge/SYSTEM_PROMPT.md` leftover identity no longer says
  "You are the offline assistant for Equal Shares".
- Always-on `CONVERSATION_RULES` / coding rules in `agent.py` no longer name
  H3, ComfyUI, clip `00B`, or `overall_soundscape`.
- `OPERATING_MEMORY.md` general/machine policy no longer primes ComfyUI or an
  assumed live render.
- Durable memory: recategorized Equal Shares/H3 rules as `project`; rewrote the
  media-queue rule so it does not name ComfyUI; forgot stale 2026-09-01
  "render has started / still ongoing" workflow facts (ids 58-62).
- `memory.recall()` skips ephemeral `workflow` rows and scopes `project state`
  the same way as `project`.
- General tool schemas no longer say Equal Shares, MiniMax H3, or Kent.
- Cleared the stale MiniMax H3 `current_workflow` pointer in
  `A:\Users\rhine\.localagent\state.json`.

`test_general_assistant.py` now forbids H3 / ComfyUI / `00B` /
`overall_soundscape` in general-chat system prompts, and forbids Equal Shares /
MiniMax H3 / Kent in general tool descriptions.

## Why

The local agent and first-bot status chats kept assuming an H3 / ComfyUI /
Equal Shares video render was in progress even when the conversation was not
about rendering. The specialist handbook was already gated, but always-on
rules, memory, tool blurbs, GROK_STATUS Current, and AGENTS.md still named
that pipeline.

## Behavior now

Ordinary chats get a general-purpose assistant. Equal Shares remains an
optional paused profile and is injected only for an explicit project request
or the Equal Shares workspace. No GPU, ComfyUI, PowerInfer execute, ReluLLaMA
retrain, or Harmontown work was started.

## Verification

- `python local_agent/test_general_assistant.py`
- `python local_agent/test_operating_memory.py`
- `python local_agent/test_prompt_prefix.py`
- `python local_agent/test_context_resilience.py`

## Still unverified

Live GUI chat against a GPU model was not run. This change is prompt/memory
scope only.

## 2026-09-01 addendum — runtime guard added after repeated live failures

The prompt/memory cleanup above was not enough. The local model still sometimes
used old H3/ComfyUI/render context in unrelated turns, especially PowerInfer
calibration follow-ups, and sometimes selected batch-render tools from stale
history.

This pass adds a hard current-turn specialist scope guard in `local_agent/agent.py`:

- old H3/ComfyUI/MiniMax/Equal Shares/render history can remain in the chat;
- those topics are available only when the current operator message explicitly
  opens that scope, or when a same-turn tool result makes it relevant;
- specialist project tools such as `batch_plan`, `start_batch_render`,
  `start_current_chat_render`, `duration_ladder`, `read_prompt`,
  `validate_prompt`, and story-image render/status tools are blocked before
  execution on unrelated turns;
- if the model leaks a stale specialist answer or tool call anyway, the loop
  discards that path once and forces a scope-corrected retry on the actual
  current request.

The launcher was also corrected:

- `START_LOCAL_AGENT_GUI.ps1` now expects app revision
  `2026-09-01-specialist-scope-guard-r74`, matching `server.py`;
- this prevents the launcher from treating the current server as stale solely
  because the revision string lagged;
- if PowerShell cannot stop an old loopback listener, it tries `taskkill` for
  that exact PID and then gives a clearer recovery message instead of failing
  with a raw `Stop-Process` stack trace.

Verification:

- `powershell ... [scriptblock]::Create(...)` parsed
  `local_agent/START_LOCAL_AGENT_GUI.ps1` successfully.
- `python -m py_compile local_agent\agent.py local_agent\server.py`
- `python local_agent\test_native_tool_calling.py` — 57 tests, 0 failures.

New regression coverage:

- stale H3/render prose is discarded on an unrelated PowerInfer turn;
- stale H3/render tool selection is blocked before the tool runs on an
  unrelated PowerInfer turn.
