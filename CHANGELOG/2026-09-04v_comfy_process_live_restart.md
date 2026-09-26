# 2026-09-04v — live `comfy_process(restart)`: refusals, then a real cycle

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04v**.
Plan: `docs/COMFYUI_MCP_INTEGRATION_PLAN.md`. Follow-up to
`CHANGELOG/2026-09-04j_comfyui_mcp_live_generate.md` and
`CHANGELOG/2026-09-04t_comfy_generate_audit_and_probe_output.md`.

This entry is **only** `comfy_process`. Nodes install and model remove are
separate.

## 1. Guardrail refusals (live wrapper, MCP not invoked)

GPU was cool: `nvidia-smi` **31 C**, 0% util, 13.2 W. Production
`thermal_guard.START_MAX_C=70`, so a hot-GPU refuse could not fire
without cooking the card. The live path was still exercised: in-process
`START_MAX_C` temporarily set to **30** (source file not edited), real
`sample_gpu()` still 31 C, then restored to 70.

`tools.call("comfy_process", {"action": "restart"})` returned:

```
ERROR: comfy_process refused: GPU 31 C exceeds thermal_guard start ceiling 30 C
```

Audit line count unchanged.

Fake owner lock: wrote this process's live PID **30984** into the real
`outputs/equal_shares/runtime/render_queue_owner.json`, same call:

```
ERROR: comfy_process refused: stage supervisor owns ComfyUI (render queue claimed by live pid 30984 (temporary live-PID for comfy_process guardrail proof; restored immediately))
```

Owner file restored byte-for-byte (`sha256`
`c6b65a654a73da2f8c7a392b27d4905b26b44ac0f1e390c29e7f2d40e6659713`
before and after). MCP not invoked.

Evidence: `.grok/long-running-background-tasks/comfy_process_live.json`.

## 2. Default MCP restart did **not** cycle the process

With owners idle, the wrapper passed preflight and called
`restart_comfyui`. comfyui-mcp 0.52.x **refused to stop** the Rockernow
Python backend:

- `stopped: false`, `started: false`, `startup: not-attempted`
- classified as ComfyUI Desktop because argv includes Desktop
  `--extra-model-paths-config ...\Comfy Desktop\instance-model-paths\...`
- parent identity unreadable (`PID 2604`, parent of `8688`)
- listener PID **40924** unchanged

The wrapper still appended `comfy_mcp_audit.jsonl` (`risk=process_control`)
because it audits **before** the MCP result. That JSON is not a process
cycle. `comfy_generate` after this no-op still succeeded
(`prompt_id ebd57717-…` → `ComfyUI_00217_.png`, 529921 bytes) because
the old process never died.

## 3. Real restart via `COMFYUI_RESTART_COMMAND`

Wired MCP's documented recovery for an externally managed install:

- `A:\Users\rhine\.grok\long-running-background-tasks\restart_comfy_rockernow.ps1`
  — kills only a Rockernow `main.py` listener on 127.0.0.1:8188, waits
  for the port to free, `Start-Process` of `start_comfy_rockernow.bat`,
  exits (MCP polls `/system_stats`).
- `mcp_client.child_env()` now sets `COMFYUI_RESTART_COMMAND` to that
  script (override: `EQUAL_SHARES_COMFYUI_RESTART_COMMAND`) and
  `COMFYUI_REMOTE_REBOOT_BUDGET_S=300` (`setdefault`).

Live call after `reset_client()`:

| | before | after |
|---|---|---|
| 8188 listener PID | **40924** | **37056** |
| argv | same Rockernow flags (`--use-pytorch-cross-attention`, Shared in/out, Desktop extra-paths yaml) | same |
| version | 0.34.0 | 0.34.0 |

MCP returned `stopped: true` but `startup: unconfirmed` — its 120s
readiness budget expired at 119s; `/system_stats` was healthy shortly
after. Probe waited and confirmed the new PID.

`comfy_generate` after the cycle: `prompt_id`
`bc1d7c5b-8fb1-4d9d-a8ef-82f4a4b2647a`, `status_str=success`,
`ComfyUI_00218_.png` **377697 bytes**, copy in
`output/mcp_test/mcp_process_restart_real_20260904_ComfyUI_00218_.png`.
Original left in place.

Audit (successful cycle):

```
{"ts": "2026-09-04T17:55:21", "local_tool": "comfy_process", "mcp_tool": "restart_comfyui", "action": "restart", "args": {"action": "restart"}, "risk": "process_control"}
```

Evidence: `.grok/long-running-background-tasks/comfy_process_restart_real.json`.

One ComfyUI, ever: did not start a second listener on top of 8188.
Equal Shares owner file left as the 2026-08-10 dead pid 16900 record.

## Files

- `local_agent/mcp_client.py` (`COMFYUI_RESTART_COMMAND`, reboot budget)
- `.grok/long-running-background-tasks/restart_comfy_rockernow.ps1` (new)
- probe scripts `comfy_process_live.py`, `comfy_process_restart_real.py`
