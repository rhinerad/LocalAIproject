# 2026-08-22 — Repair the Desktop local-agent launcher

## Observed failure

`Desktop\EQUAL_SHARES_LOCAL_AGENT\START_LOCAL_AGENT.cmd` delegated to a stale
PowerShell script from 2026-08-14. That script started the layered render
watchdog and the retired Open Interpreter handoff. It never called the current
browser-based `local_agent\START_LOCAL_AGENT_GUI.ps1`, so double-clicking it
could not fully start the current Equal Shares agent.

The desktop readme described the same superseded Omni-reference controlled test
and told the operator to use Open Interpreter and old numbered prompts.

## Changes

- Replaced `Desktop\EQUAL_SHARES_LOCAL_AGENT\START_LOCAL_AGENT.ps1` with a
  narrow delegate to the canonical `local_agent\START_LOCAL_AGENT_GUI.ps1`.
- Updated the `.cmd` wrapper to use `-NoProfile`, preserve the launcher's exit
  code, and pause only on a real failure.
- Added `Desktop\Equal Shares Local Agent.lnk`, targeting the repaired `.cmd`.
- Updated the desktop `README_FIRST.txt` to describe the current Ollama browser
  app and mark the dated prompt files as non-authoritative.
- Added a readiness check to `local_agent\START_LOCAL_AGENT_GUI.ps1`. If the
  GUI is already healthy on `127.0.0.1:8760`, another click opens/reports the
  existing app and exits instead of starting duplicate Python/Ollama servers.
  Browser-launch refusal is treated as cosmetic when the local HTTP status
  endpoint is already healthy.

No render path, tool implementation, validation guard, model, or project
evidence was changed. No download occurred.

## Verification

Cold-started the repaired desktop `.cmd` with the GUI port initially free:

- both Ollama endpoints were available on `127.0.0.1:11434` and `:11435`
- the knowledge pack rebuilt: 18 speakers, 124 prompts, 0 manifest records
- the GUI served HTTP 200 at `http://127.0.0.1:8760`
- `/api/status` reported CPU tier, `qwen3:8b`, both Ollama servers up, and the
  knowledge pack present

Ran the desktop launcher a second time. Listener PID `21304` remained unchanged,
proving the launcher reused the single GUI server rather than creating a
duplicate.

Sent a real question through the GUI `/api/send` path. The response stream
contained a native `project_state` tool call, its tool result, streamed tokens,
and the correct final answer: the audio-pass manifest contains 0 clip records.

## Still unverified

The Codex test shell is forbidden from launching the user's default browser, so
automatic browser focus cannot be observed inside this sandbox. The launcher
handles that restriction without reporting a false failure, and the server's
own `webbrowser.open()` path remains unchanged. The GUI URL and full chat path
are live and verified.
