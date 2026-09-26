# 2026-09-04c — comfyui-mcp integration: research, decisions recorded, plan written (no code)

## Scope

Operator asked to install `https://github.com/artokun/comfyui-mcp` and
integrate it with the local agent. Two decision points were surfaced and
answered before any code was written, since this tool's capability set (it
can start/stop/restart ComfyUI directly, delete model files, and install
arbitrary custom node packs via git clone + pip install) runs directly
against this project's own standing rules: "One ComfyUI, ever," the stage
supervisor owning process lifecycle, `work/thermal_guard.py`, and "never
destroy evidence."

## Decisions (operator, 2026-09-04)

1. **Target:** the custom Ollama-based `local_agent` project
   (`agent.py`/`tools.py`), not Claude Code's own MCP config. That project
   has no MCP client today — this is a real architecture addition, not a
   config edit.
2. **Scope:** full access — generation, model management/deletion,
   custom-node install, and ComfyUI process control all wired in, not
   restricted to generation-only.
3. **ComfyUI instance:** the same shared install
   (`A:\Users\rhine\ComfyUI-Shared\...`) local_agent's own
   `work/image_render.py` already renders against, and that Equal Shares'
   paused evidence lives under. Operator explicitly accepted the collision
   risk on the condition comfyui-mcp and local_agent's own render dispatch
   are never run at the same time.

## What was written

`docs/COMFYUI_MCP_INTEGRATION_PLAN.md` — full architecture: a new
`local_agent/mcp_client.py` (minimal synchronous MCP stdio client, matching
this codebase's existing dependency-light style and its fully-synchronous
concurrency model — no `asyncio` anywhere in `agent.py` today), seven new
explicitly-named `comfy_*` tools added to `tools.py`'s `TOOLS` dict
(`comfy_generate`, `comfy_workflow`, `comfy_assets`, `comfy_models`,
`comfy_nodes`, `comfy_system`, `comfy_process`), each wrapping one group of
comfyui-mcp's ~38 tools. Deliberately **not** a single raw
"call any MCP tool" passthrough — that would turn `tools.py` into a shell,
which is the one thing `CLAUDE.md` says not to do for convenience even
under "full access." Runtime guardrails specified: `comfy_process` must
check `thermal_guard.py`/stage-supervisor state and refuse if the
supervisor currently owns the ComfyUI process; deletions and node installs
must be logged durably (CHANGELOG, per this project's existing pattern).

`TODO.md` — new tracked item recording the decisions and linking the plan
doc.

## What was not done

No code. No `npm install`, no `local_agent/mcp_client.py`, no `comfy_*`
tools in `tools.py`. No Node version check on DuranGamingPC. This session
had no shell access to do any of that — see
`docs/COMFYUI_MCP_INTEGRATION_PLAN.md`'s "Implementation steps" for what a
shell-capable session should do next, in order: confirm Node >=22, write
and unit-test `mcp_client.py` against a mocked subprocess (no live ComfyUI
needed for the base suite), add the seven tools, then live-verify starting
with the lowest-risk read-only tool (`comfy_system`) before touching
deletion/install/process-control tools live.
