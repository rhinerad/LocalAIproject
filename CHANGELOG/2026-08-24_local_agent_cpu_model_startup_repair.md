# Local-agent CPU model startup repair — 2026-08-24

## Problem

The desktop local-agent shortcut could start both Ollama servers but the chat
picker reported that no CPU model was available. This was a router allowlist
bug: `qwen3:8b` was installed on the dedicated CPU server and supports native
Ollama tools, but was absent from the conversation-model preference list.

## Change

- The initial repair exposed installed stock Qwen models to unblock the empty
  picker. Corrected in this same session: only the Huihui abliterated reasoning
  pair and explicitly abliterated local tags are now chat choices. Vision models
  remain excluded from normal chat and are still used only by sensory tools.
- The desktop launcher now checks for one configured CPU startup model before
  opening the GUI. Its default is `huihui_ai/qwen3-abliterated:8b`; set
  `EQUAL_SHARES_CPU_CHAT_MODEL` to intentionally choose a different one.
- If that configured model is absent, only the launcher issues the corresponding
  `ollama pull`; a chat request can never trigger a download. A failed pull is
  reported clearly; the agent never substitutes a stock model.
- Updated the app revision to `2026-08-24-qwen25-vl-caption-v4-r19` and the
  README startup behavior. The abliterated-only correction advanced the live
  revision to `2026-08-24-qwen25-vl-caption-v4-r20`.

## Verification

- `python local_agent\\test_router_switching.py` — 13/13 passed.
- `python local_agent\\test_general_assistant.py` — passed.
- The live CPU server was confirmed healthy before the permitted-model pull.
- The launcher pulled and registered `huihui_ai/qwen3-abliterated:8b` (5.0 GB).
- Live r20 status showed exactly one chat-picker choice:
  `huihui_ai/qwen3-abliterated:8b`, with the CPU server up.
- Re-ran `test_router_switching.py` (13/13), `test_general_assistant.py`, and
  `test_native_tool_calling.py` (10/10) after the abliterated-only correction.
- Parsed `START_LOCAL_AGENT_GUI.ps1` with PowerShell's parser — passed.

No render, ComfyUI backend, pipeline script, evidence file, or network binding
was started or changed.
