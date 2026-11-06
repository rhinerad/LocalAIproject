# comfyui-mcp integration plan for local_agent — 2026-09-04

## Decision record

Operator asked to install `https://github.com/artokun/comfyui-mcp` and
integrate it with **the custom Ollama-based `local_agent` project**
(`agent.py`/`tools.py`), not just as a Claude Code MCP config entry. Given
two options for scope, operator chose **full access** — generation, model
management (including deletion), custom-node install (git clone + pip
install), and ComfyUI process control (start/stop/restart) all wired in, not
scoped down to generation-only and not pointed at an isolated instance.

This is recorded explicitly because it's a real tension with standing rules
in `CLAUDE.md`: "One ComfyUI, ever," the stage supervisor owning process
lifecycle, `work/thermal_guard.py` gating GPU jobs, and "never destroy
evidence." Full access was still the operator's explicit choice after that
tension was raised — this doc is where that decision lives, not a place to
silently relitigate it. The design below keeps the letter of `tools.py`'s
"fixed whitelist, not a shell" model even while wiring in comfyui-mcp's full
surface: every comfyui-mcp action gets an explicitly named, individually
whitelisted `local_agent` tool. There is no raw "call any MCP tool"
passthrough — that would turn `tools.py` into an actual shell, which is the
one thing `CLAUDE.md` says not to do "for convenience."

## What comfyui-mcp actually is

A Node.js (>=22) MCP **stdio server** — not a Python library, not a REST
service by default. It talks to a locally running ComfyUI over ComfyUI's own
REST/WebSocket API, and exposes ~38 MCP tools: image/video/audio generation,
workflow authoring/validation/visualization, model search/download/delete,
custom-node search/install (registry + git clone + pip install), VRAM
control (`/free`), and **process control** (`restart_comfyui`
start/stop/restart, which finds and manages the ComfyUI process directly —
this is a second, independent lifecycle owner alongside this project's own
stage supervisor and `thermal_guard.py`).

`npx -y comfyui-mcp` is the normal invocation — no repo clone is required
for use, only for building from source. It speaks MCP (JSON-RPC over
stdio), which `local_agent` has never spoken before; `tools.py` is a flat
Python dict of `def foo(args: dict) -> str` functions dispatched by
`tools.call(name, args, ...)` — completely synchronous, no MCP client
exists anywhere in this codebase today (confirmed: no `asyncio` in
`agent.py`, concurrency is `ThreadPoolExecutor`-based).

## Architecture

### 1. `local_agent/mcp_client.py` (new)

A minimal, synchronous MCP stdio client — not a general-purpose MCP SDK,
just enough to drive this one server, matching the project's preference for
small dependency-free modules over heavy frameworks (see `context_compactor`,
`ollama_client` for the existing style).

- Spawns `npx -y comfyui-mcp` (or a pinned local install — decide during
  implementation whether `npx` fetching a possibly-newer version on every
  restart is acceptable, or whether to pin an exact version / vendor a
  local `node_modules` install for reproducibility) as a subprocess once,
  lazily, on first use. Kept alive across calls; not respawned per call.
- Speaks MCP's JSON-RPC-over-stdio handshake (`initialize`, `tools/list`,
  `tools/call`), with a lock around request/response so concurrent
  `ThreadPoolExecutor` tool calls don't interleave on the same stdio pipe.
- Bounded timeout per call (comfyui-mcp's own generation calls can run long
  — match or exceed `COMFYUI_MCP_STALL_S` semantics, don't impose a tighter
  ceiling that kills a legitimately slow render).
- Environment for the child process sets `COMFYUI_PATH`/`COMFYUI_URL`
  explicitly (see "Which ComfyUI instance" below) rather than relying on
  comfyui-mcp's own auto-detection, so there is no ambiguity about which
  installation it's driving.
- Logs go to stderr on the child process side already (per comfyui-mcp's
  own design, "safe for stdio transport") — capture and surface that
  through `local_agent`'s existing logging, not silently discarded.

### 2. New whitelisted tools in `local_agent/tools.py`

One `local_agent` tool per comfyui-mcp tool group (not one giant passthrough),
each a thin `def comfy_<group>(args: dict) -> str` wrapper calling
`mcp_client.call("<comfyui-mcp tool name>", args)` and formatting the
result the way every other tool in this file already does (string return,
same error-handling conventions as `stop_all_comfyui`/`start_batch_render`
next to it). Suggested grouping, mirroring comfyui-mcp's own tool
consolidation:

| local_agent tool | wraps comfyui-mcp tool(s) |
|---|---|
| `comfy_generate` | `generate_image` (all actions: image/controlnet/ip_adapter/video/3d/upscale/remove_background/audio) |
| `comfy_workflow` | `enqueue_workflow`, `queue`, `create_workflow`, `visualize_workflow`, `get_workflow`, `save_workflow` |
| `comfy_assets` | `get_image`, `upload_image` |
| `comfy_models` | `download_model`, `list_local_models` (deletion capability lives here — see guardrail below) |
| `comfy_nodes` | `search_custom_nodes`, `install_custom_node`, `node_pack` |
| `comfy_system` | `get_system_stats`, `clear_vram`, `get_history`, `comfy_cli` |
| `comfy_process` | `restart_comfyui` (start/stop/restart — see guardrail below) |

Add all seven to `TOOLS`. Add `comfy_process` and `comfy_nodes` to
`PROJECT_ONLY_TOOLS` at minimum (process control and arbitrary node
install are not things a casual/general conversation turn should be able to
trigger incidentally) — decide during implementation whether the others
need the same treatment or are safe as general tools. None of the seven
belong in `CONCURRENCY_SAFE_TOOLS` — they all talk to a single shared
ComfyUI instance and the single shared MCP subprocess.

### 3. Which ComfyUI instance — the one open question that needs an explicit operator pick before writing code

The operator chose "full access," not "point it at a separate instance,"
but *which* ComfyUI install this targets was not asked as a separate
question and still needs a real answer, because this repo's ComfyUI-shared
tree includes Equal Shares' paused evidence:

- If `COMFYUI_PATH`/`COMFYUI_URL` points at the same install/data dir
  `local_agent`'s own `work/image_render.py` already renders story images
  against, `comfy_models`'s delete action and `comfy_nodes`'s install
  action can touch files in that shared tree, and `comfy_process`'s
  restart can race the stage supervisor for port 8188. `CLAUDE.md`'s "One
  ComfyUI, ever" becomes a real, not theoretical, collision risk the
  moment both `local_agent`'s existing render dispatch and a comfyui-mcp
  call are live at the same time.
- Concretely: `A:\Users\rhine\ComfyUI-Shared\output\...` is where Equal
  Shares evidence lives per `CLAUDE.md`. Confirm with the operator whether
  `COMFYUI_PATH` for this integration should point at that same shared
  install (accepting the collision risk, mitigated by never running both
  at once) or a distinct ComfyUI checkout/data directory reserved for
  general local_agent image work, keeping Equal Shares' tree completely
  out of reach of `comfy_models(remove)`/`comfy_nodes(install)` by
  construction.
**Decided, 2026-09-04: the same shared install** —
`A:\Users\rhine\ComfyUI-Shared\...`, the one Equal Shares' paused evidence
lives under and `local_agent`'s own `work/image_render.py` already renders
against. Operator explicitly accepted the collision risk described above on
the condition that comfyui-mcp and `local_agent`'s own render dispatch are
never run at once. `COMFYUI_PATH`/`COMFYUI_URL` should be set to that exact
path explicitly in the MCP subprocess environment (not left to comfyui-mcp's
own auto-detection) so there's no ambiguity about which installation is
targeted. Because this is the shared, evidence-bearing tree, the runtime
guardrails in the next section are not optional polish — they are the only
thing standing between "full access" and an accidental collision with the
stage supervisor or Equal Shares' evidence.

### 4. Runtime/lifecycle guardrails to build in regardless of "full access"

"Full access" was about *which tools get wired in*, not about removing
this project's own safety plumbing. Concretely:

- `comfy_process` (`restart_comfyui`) must check `work/thermal_guard.py`'s
  current state and the stage supervisor's own liveness (same checks
  `stop_all_comfyui`/`start_batch_render` in `tools.py` already do) before
  acting, and must refuse if the stage supervisor currently owns the
  process — two independent things starting/stopping the same ComfyUI is
  exactly the failure mode "One ComfyUI, ever" was written to prevent.
- `comfy_models` deletion and `comfy_nodes` install should log what they
  did somewhere durable (this project's existing pattern: a CHANGELOG
  entry per session, not silent) since both are effectively irreversible
  or code-execution-risk actions.
- `comfy_generate` also appends `local_agent/runtime/comfy_mcp_audit.jsonl`
  on every call (desktop agent or a Grok probe script): timestamp, caller
  (pid / script / function), args, `prompt_id`. Generate is not
  irreversible in the delete/install sense, but without this log a probe
  mug in the shared output folder cannot be distinguished from an
  operator job.
- None of this should be allowed to touch anything under the Equal Shares
  paused tree, however "Which ComfyUI instance" above gets answered.

### 4b. `filename_prefix` on `generate_image` — MCP limitation, not our wrapper

Live 2026-09-04 mug probes passed `filename_prefix` (`mcp_live_verify_20260904`,
`vram_phase_probe_20260904`). ComfyUI wrote `ComfyUI_00214_.png` /
`ComfyUI_00215_.png`. History for prompt_id `8182b9d1-…` shows SaveImage
node 7 with `"filename_prefix": "ComfyUI"`.

This is **comfyui-mcp 0.52.x**, not a drop in `tools.comfy_generate` and
not ComfyUI ignoring a correctly-set SaveImage widget:

- `dist/tools/generate-image.js` action `"image"` calls `generateImage({
  prompt, width, height, steps, cfg, sampler, scheduler, seed,
  checkpoint, batch_size })` — **`filename_prefix` is not passed**.
  The same file *does* pass `filename_prefix` for actions `"audio"`,
  `"video"`, and `"remove_background"`. The Zod field description names
  only those three actions.
- `dist/services/workflow-composer.js` `buildTxt2Img` / `buildImg2Img`
  hardcode `filename_prefix: "ComfyUI"`. ControlNet / IP-Adapter /
  upscale similarly hardcode `ComfyUI_controlnet` / `ComfyUI_ipadapter`
  / `ComfyUI_upscale`.
- Official docs (comfyui-mcp.artokun.io generate_image parameters):
  `filename_prefix` is documented as applying to audio, video, and
  remove_background only.

Do **not** work around this inside `comfy_generate` (rewriting the MCP
graph would fork their composer). Probe scripts that need isolated files
enqueue their own graph via `local_agent/mcp_test_output.py`
(`SaveImage` prefix `mcp_test/<stem>`). Operator generation is unchanged.

## Implementation steps (for whoever has real shell access — this plan was
written without it; see the handoff note below)

1. Confirm Node >=22 is installed on DuranGamingPC (`node --version`); install
   or update if not — do not assume.
2. Answer the "Which ComfyUI instance" question above with the operator
   before setting `COMFYUI_PATH`/`COMFYUI_URL` anywhere.
3. Write `local_agent/mcp_client.py` per the spec above. Unit-test it against
   a mocked stdio subprocess first (no live ComfyUI needed) — same pattern
   this project already uses for `ollama_client`/farm-task tests (mock the
   external process, don't require live infra for the base test suite).
4. Add the seven `comfy_*` tools to `tools.py`, `TOOLS`, and the appropriate
   whitelist sets.
5. Live-verify against a real running ComfyUI: at minimum `comfy_system`
   (read-only, lowest risk) first, then `comfy_generate` with one real
   render, before touching `comfy_models`/`comfy_nodes`/`comfy_process` live.
6. Update `local_agent/README.md`, `TODO.md`, and add a dated `CHANGELOG`
   entry per the standing pattern — cite the actual test run and the actual
   live verification, not just "should work."

## What this doc does not do

It does not install anything, does not add `local_agent/mcp_client.py` or
the `comfy_*` tools yet, and does not answer the "Which ComfyUI instance"
question — that still needs the operator, and everything downstream in
"Implementation steps" needs real shell access this session doesn't have.
