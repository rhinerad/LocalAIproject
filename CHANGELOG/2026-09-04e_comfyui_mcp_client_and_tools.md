# 2026-09-04e — comfyui-mcp client and seven `comfy_*` tools

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04e**.
Plan and operator decisions: `docs/COMFYUI_MCP_INTEGRATION_PLAN.md`,
`CHANGELOG/2026-09-04c_comfyui_mcp_integration_plan.md`.

## What shipped

- `local_agent/mcp_client.py` — minimal synchronous MCP stdio client. Spawns
  `npx -y comfyui-mcp` once, keeps it alive, lock around request/response.
  Writes newline-delimited JSON-RPC (current `@modelcontextprotocol/sdk`
  stdio); still parses Content-Length for the mock and older servers. Waits
  for the child's `ComfyUI MCP server running on stdio` marker before
  `initialize` so `npx -y` download time cannot eat the handshake. On
  Windows the argv is `node.exe` + `npx-cli.js`, not `cmd /c npx.cmd`
  (that combination dropped stdin on the first live spawn).
- Child env is forced, not auto-detected:

  | Variable | Value |
  |---|---|
  | `COMFYUI_PATH` | `A:\Users\rhine\ComfyUI-Shared` |
  | `COMFYUI_CODE_PATH` | `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI` |
  | `COMFYUI_URL` | `http://127.0.0.1:8188` |
  | `COMFYUI_MCP_TOOL_MODE` | `full` |

  Split-install is real on this machine: Shared is models/input/output
  (Equal Shares evidence); Rockernow is `main.py` / `.venv`. comfyui-mcp's
  `.env.example` documents `COMFYUI_PATH` as the data root and
  `COMFYUI_CODE_PATH` as the checkout.
- Seven whitelist tools in `tools.py` `TOOLS`: `comfy_generate`,
  `comfy_workflow`, `comfy_assets`, `comfy_models`, `comfy_nodes`,
  `comfy_system`, `comfy_process`. Not a raw MCP passthrough.
- `comfy_process` and `comfy_nodes` added to `PROJECT_ONLY_TOOLS`. None of
  the seven are in `CONCURRENCY_SAFE_TOOLS`. All seven are in
  `GATED_REMOTE_TOOLS`. `comfy_process` / `comfy_nodes` also in
  `agent.py`'s `_SPECIALIST_PROJECT_TOOLS`.
- `comfy_process` preflight: `thermal_guard.sample_gpu()` (there is no
  on-disk thermal state file — live nvidia-smi plus `START_MAX_C` /
  `EMERGENCY_C`; unknown telemetry refuses) and supervisor liveness via
  `router.queue_owner()` plus live PIDs in `batch_render_queue_owner.json`
  and `work/runtime/image_render_owner.json` (same pattern as
  `start_batch_render`). Deletes/installs/process-control append
  `local_agent/runtime/comfy_mcp_audit.jsonl`.

## Tests (mocked subprocess — no live ComfyUI)

From `local_agent/`:

```
python test_mcp_client.py   -> Ran 10 tests in ~2.0s  OK
python test_comfy_tools.py  -> Ran 14 tests in ~0.02s OK
```

Covered: child env targeting Shared/8188, keep-alive same PID across
calls, ThreadPoolExecutor lock (two 0.2s holds >= 0.35s), isError and
JSON-RPC errors, stall timeout, stderr capture, singleton reset, all
seven registered, project-only / not concurrency-safe / phone-gated,
generate default action, workflow passthrough refusal, audit JSONL for
remove/install, `comfy_process` refuse on live supervisor PID, refuse on
91 C, refuse when nvidia-smi missing, allow when cool and unowned.

## Live evidence

**Node:** `node --version` = **v24.15.0** (>= 22). npm/npx 11.13.0. No
install needed.

**thermal_guard / supervisor as they exist today:**
`thermal_guard.py` has `sample_gpu()`, `START_MAX_C=70`, `EMERGENCY_C=82`
— no persistent state file. Live sample during this session:
`GpuSample(temperature_c=31, utilization_percent=8, power_watts=17.68)`.
`router.queue_owner()` on the real
`outputs/equal_shares/runtime/render_queue_owner.json` returned
`(False, 'queue owner released')` — file still names pid 16900 from
2026-08-10, `tasklist` had no such process. Batch and image-render
owners both `pid: 0`.

**Guardrail refuse (proved, not assumed):** wrote this process's live PID
(31092) into the real owner file, called `tools.call("comfy_process",
{"action": "restart"})`, got:

```
ERROR: comfy_process refused: stage supervisor owns ComfyUI (render queue claimed by live pid 31092 (temporary live-PID for comfy_process guardrail proof; restored immediately))
```

Owner file restored byte-for-byte (`sha256` prefix `c8b4980a0c5ffdaa`
before and after, `bytes_match True`). MCP was not invoked; no audit
line for a successful restart.

**Live MCP handshake (real `npx -y comfyui-mcp`, ComfyUI not required for
the RPC layer):** after switching to NDJSON + `node npx-cli.js` + ready
wait, `list_tools` returned **41** tools in **1.0s**, child pid 37532,
including `get_system_stats`, `generate_image`, `restart_comfyui`. First
attempt with `cmd /c npx.cmd` + Content-Length initialize timed out at
300s even though stderr already said `ComfyUI MCP server running on stdio`.

**Live `comfy_system` (read-only, first risk step):** wrapper defaulted
`action` to `stats` (server rejects a missing action:
`expected one of "stats"|"logs"|"health"`). Result against the targeted
URL, 0.9s:

```
ToolError fetch failed: (ECONNREFUSED) — while requesting
http://127.0.0.1:8188/system_stats (GET). That is the headless ComfyUI
target (COMFYUI_URL)
```

`netstat` had no `:8188` listener. Confirmed independently with
`Invoke-WebRequest http://127.0.0.1:8188/system_stats` → Unable to
connect.

**Stopped there.** Did not start ComfyUI. Did not run `comfy_generate`.
Did not live-call `comfy_models(remove)`, `comfy_nodes(install)`, or
`comfy_process` start/stop/restart. Remaining item:
`TODO.md` "comfyui-mcp live generate" when 8188 is actually up.

## Files

- `local_agent/mcp_client.py` (new)
- `local_agent/test_mcp_client.py` (new)
- `local_agent/test_comfy_tools.py` (new)
- `local_agent/tools.py`, `agent.py`, `remote_security.py`
- `local_agent/README.md`, `TODO.md`
