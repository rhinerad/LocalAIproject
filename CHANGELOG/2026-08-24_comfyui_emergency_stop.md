# 2026-08-24 — Local-agent ComfyUI emergency stop

## Why

A general desktop batch render launched from the current chat remained in a
GPU-busy state after its ComfyUI log recorded a CUDA out-of-memory failure. The
operator needs an intentional recovery control that stops an already-started
render without risking evidence or the local agent itself.

## What changed

- Added the desktop-only `stop_all_comfyui` tool and native Ollama schema.
- Added the red **Stop ComfyUI render** sidebar control and its local
  `POST /api/stop_comfyui` route.
- Both paths first send ComfyUI's local `127.0.0.1:8188/interrupt` request,
  then terminate only the current batch-runner PID and positively identified
  ComfyUI Python processes (the port listener and ComfyUI executable paths).
  Discovery uses `netstat` and `Get-Process`, not a CIM/WMI query, because the
  workstation's normal desktop account is denied CIM process inspection. They
  do not target Ollama, the local agent, browser, uploads, prompts, sources, or
  outputs.
- A forced runner stop resets only a dead `batch_render_queue_owner.json` lock,
  allowing normal queue preflight on the next deliberate render.
- When a ComfyUI backend was launched elevated and the desktop app is denied
  process termination, the button now requests normal Windows UAC consent for
  `local_agent/STOP_COMFYUI_ELEVATED.ps1`. That fixed, argument-free helper
  repeats the same port/path/queue discovery and records its result; it never
  receives a model-supplied command or PID.
- Exact desktop imperatives `stop render`, `kill ComfyUI`, `abort render`, and
  equivalents route deterministically to the same fixed action; questions such
  as “how do I stop render?” do not trigger it. Remote identities are denied by
  the existing per-identity capability layer and audited.
- Bumped the server/launcher revision to
  `2026-08-24-comfyui-emergency-stop-r39`.

## Evidence and verification

- The active job's immutable provenance records five complete prompts from its
  originating chat, its character and setting images, and five copied video
  chunks. A sixth incomplete prompt was correctly skipped. The stop mechanism
  preserves this job and all its artifacts.
- The active ComfyUI stderr log recorded `torch.AcceleratorError: CUDA error:
  out of memory`; this change supplies recovery only and does not claim the
  render passed.
- `python -m py_compile local_agent/tools.py local_agent/agent.py
  local_agent/server.py local_agent/remote_security.py` passed.
- Schema check found 35 registered tool schemas including `stop_all_comfyui`.
- Read-only process discovery found the live ComfyUI launcher PIDs and its
  port-8188 worker PID; remote capability denial for the new tool was exercised;
  exact-stop routing tests passed while a stop question remained non-operative.

No render, source, prompt, upload, or evidence file was deleted, moved,
renamed, or overwritten while implementing this control.
