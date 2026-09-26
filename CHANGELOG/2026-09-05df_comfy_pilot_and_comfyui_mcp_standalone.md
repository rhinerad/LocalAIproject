# 2026-09-05df — comfy-pilot + comfyui-mcp installed for standalone trial

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write:
**2026-09-05df**.

Authorized by `2026-09-05cy`. Standalone / manual only — **not** wired into
`local_agent/tools.py`, `agent.py`, or `router.py` (those files are
unchanged). No Equal Shares render, no `outputs/equal_shares/**` writes,
no GOLDEN_REFERENCE / pinned-workflow edits, no existing custom node
removed or overwritten.

Evidence dir:
`artifacts/comfy_pilot_mcp_standalone_2026-09-05/`
(custom_nodes before/after, startup log, object_info keys, MCP tools
list, pilot chat transcript).

## Preflight (before any start)

| Check | Result |
|---|---|
| Clock | 2026-09-05 17:56:58 |
| GPU | RTX 5080, **32 C / 5% / 8462 MiB** then **35 C / 0% / 73 MiB** (llama-server unloaded between samples) |
| `:8188` | not listening |
| `render_queue_owner.json` | pid **16900** claimed 2026-08-10 — **process dead** (stale) |
| `batch_render_queue_owner.json` | pid 0, released 2026-08-25 |
| `render_supervisor.log` | mtime **2026-08-10 01:46:11**, not advancing |
| Thermal start ceiling | 70 C — pass |

One Rockernow backend only, via the standing
`~/.grok/long-running-background-tasks/start_comfy_rockernow.bat`.

## custom_nodes/ before

Snapshot:
`artifacts/comfy_pilot_mcp_standalone_2026-09-05/custom_nodes_BEFORE.txt`

112 entries under
`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes`.
Already present (not added this pass): `comfyui-agent-panel`
(2026-09-04) and `comfyui-mcp-throwaway-probe` (2026-09-04).

After this pass: **113** entries; the only addition is `comfy-pilot`
(see `custom_nodes_AFTER.txt`).

## 1. comfy-pilot (GPLv3 custom node)

Clone per README into the Rockernow `custom_nodes/` tree:

- URL: https://github.com/AdamPerlinski/comfy-pilot
- Path: `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes\comfy-pilot`
- Commit: `a89fc7de03e16fcb324374003ef6626215257e8a` (2026-08-01,
  `Merge pull request #4 from maxlibin/main`)
- Declared version in `__init__.py`: **0.1.0** (alpha)

`pip install -r requirements.txt` against Rockernow
`.venv` (`python 3.13.12`, `aiohttp 3.13.5`, `pyyaml 6.0.3`):
**would_install 0**. No torch / CUDA / existing-node package changes.

Node class added: `AgenticPromptGenerator` (unique in `/object_info`).
Routes: `/comfy-pilot/*`. Frontend: `/extensions/comfy-pilot/panel.js`
(Pilot menu button).

## 2. comfyui-mcp (standalone MCP, not local_agent)

README quick start is `npx -y comfyui-mcp` — used that, pinned.

- npm: **comfyui-mcp@0.52.199**
- Source pin clone (not npm-installed): `external/comfyui-mcp` at
  `2bc1460b5455b1e00be986ccff1dbed8667d7589`
  (`chore: release v0.52.199 (#2888)`, 2026-09-05)
- Env for the process: `COMFYUI_URL=http://127.0.0.1:8188`,
  `COMFYUI_PATH=A:\Users\rhine\ComfyUI-Shared`,
  `COMFYUI_CODE_PATH=A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI`,
  `COMFYUI_MCP_AUTO_UPDATE_DISABLE=1`, `COMFYUI_MCP_TOOL_MODE=full`
- HTTP transport: `npx --yes comfyui-mcp@0.52.199 --http --host 127.0.0.1 --port 9100`

On start it logged **panel already present** at
`custom_nodes/comfyui-agent-panel` **0.15.173** and left it untouched
(on-load check installs a missing panel only; not a version upgrade).

`local_agent/mcp_client.py` already exists from an earlier integration
plan. This pass did **not** spawn it from the agent loop and did not
edit tools/agent/router.

## Smoke tests (no generation, queue stayed empty)

Rockernow came up: `http://127.0.0.1:8188`, ComfyUI **0.34.0**,
pytorch **2.10.0+cu130**, idle VRAM **356 MiB**, queue
running=0 pending=0. Startup log:
`[comfy-pilot] Routes registered successfully` in 0.1 s.

`/object_info` **3245** node types. Equal-Shares-relevant types still
present: `MiniMaxH3ReferenceToVideo`, `MiniMaxH3ImageToVideo`,
`MiniMaxH3TurboSampler`, `VHS_LoadVideo`, `VHS_VideoCombine`,
`WanVideoSampler`. New: `AgenticPromptGenerator`.

Pre-existing import warnings (piexif / dill / cupy / …) are unchanged
and **not** caused by comfy-pilot.

### comfy-pilot

- `GET /extensions/comfy-pilot/panel.js` → 200, ~48 KB, contains
  the **Pilot** menu button.
- `GET /comfy-pilot/agents` → 200. Ollama / Claude Code / Gemini API
  reported available. First 30 s call timed out (every backend is
  probed in parallel; CLI agents are slow).
- `GET /comfy-pilot/custom-nodes` → 200 but
  `found: false` — path autodetection looks at `~/ComfyUI` and
  `cwd().parent`. Rockernow cwd is
  `ComfyUI-Installs\Rockernow`, so it never sees
  `Rockernow\ComfyUI\custom_nodes`. Fragility, not a crash.
- `POST /comfy-pilot/chat` with Ollama
  `huihui_ai/qwen3-abliterated:8b`, message
  "Reply with only the word PONG. Do not output JSON. Do not create
  or modify any workflow.", `context_mode=minimal` → **`PONG`**.
  ComfyUI queue stayed empty. **Side effect:** that model was on CPU
  (`size_vram: 0`) and the chat **promoted it onto the GPU**
  (7623 MiB, 94% util). Unloaded immediately with
  `keep_alive: 0`; VRAM returned to 356 MiB ComfyUI-only.

### comfyui-mcp

- HTTP MCP `initialize` → `serverInfo {name: comfyui-mcp, version: 0.52.199}`
- `tools/list` → **41 named tools** (full mode plus the three compact
  meta-tools `list_tools` / `describe_tool` / `call_tool`). The
  "178 tools" figure is the expanded action surface behind those
  names, not 178 separate MCP registrations.
- **Did not** call `generate_image`, `enqueue_workflow`,
  `restart_comfyui`, `install_custom_node`, `list_local_models`
  `remove`, or any Equal Shares path.

## Clean shutdown

Stopped Rockernow python (`43916`/`44412`) and the MCP node
(`4368` / npx `33596`). After:

- `:8188` not listening
- `:9100` TimeWait only (no Listen)
- GPU **32 C / 0% / 73 MiB**, compute: Brave only
- `render_supervisor.log` still frozen at 2026-08-10 01:46:11
- no leftover `Rockernow\ComfyUI\main.py`

## How the operator launches these later

**One ComfyUI, ever.** Preflight GPU temp (≤70 C), `:8188` free, no live
render-owner PID, supervisor log not advancing — then:

1. Start Rockernow:
   `A:\Users\rhine\.grok\long-running-background-tasks\start_comfy_rockernow.bat`
   UI: **http://127.0.0.1:8188**
2. comfy-pilot: open that URL, click **Pilot** in the top menu.
   Chat talks to Ollama on `:11434` by default. Do **not** ask it to
   generate or apply a workflow against Equal Shares content.
3. comfyui-mcp (separate process, after ComfyUI is up):

```
set COMFYUI_URL=http://127.0.0.1:8188
set COMFYUI_PATH=A:\Users\rhine\ComfyUI-Shared
set COMFYUI_CODE_PATH=A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI
set COMFYUI_MCP_AUTO_UPDATE_DISABLE=1
npx --yes comfyui-mcp@0.52.199 --http --host 127.0.0.1 --port 9100
```

MCP HTTP: `http://127.0.0.1:9100/mcp`. Stdio form (Claude Code etc.):
the same env without `--http`. Panel orchestrator (sidebar **Connect**):
`npx --yes comfyui-mcp@0.52.199 connect` — already-installed
`comfyui-agent-panel` 0.15.173.

Stop: Ctrl+C the MCP process; stop Rockernow (kill the `main.py`
python, or the existing `restart_comfy_rockernow.ps1` stop path). Do
not leave `:8188` up idle.

Rollback for the new node only:
delete `custom_nodes\comfy-pilot` (do not touch other packs).

## Conflicts / fragility found

1. **Second lifecycle owner.** comfyui-mcp exposes `restart_comfyui`,
   `install_custom_node`, `install_comfyui`, `list_local_models`
   (includes delete), `generate_image`, `clear_vram`. Pointed at the
   shared Rockernow + `ComfyUI-Shared` tree. A generation tool would
   write under `ComfyUI-Shared\output`. Do not invoke those against
   Equal Shares evidence.
2. **Two sidebars.** `comfy-pilot` Pilot button and
   `comfyui-agent-panel` Agent panel both load. No node-id collision
   (`AgenticPromptGenerator` is unique). UI clutter only so far.
3. **Ollama on `:11434` is not CPU-safe.** comfy-pilot's Ollama
   backend used the already-resident 8B and **moved it onto the 5080**
   (~7.3 GiB). That races ComfyUI for VRAM. Unload with
   `keep_alive: 0` after poking at it, or point it at a CPU-only
   Ollama port if one is brought back up.
4. **custom_nodes autodetection is wrong on this split install.**
   `/comfy-pilot/custom-nodes` cannot find the pack list. Chat still
   works; node listing via ComfyUI `/object_info` still works.
5. **Catalog size.** 41 MCP tools (or ~178 expanded actions) is
   several times the 68-tool GPU schema that drowned Huihui today.
   Keep this **out** of `local_agent`'s tool list.
6. **No pip clash** for comfy-pilot. MCP is Node and did not
   `pip install` into Rockernow. It did not upgrade the existing
   agent-panel pack.

Unverified vs GOLDEN_REFERENCE: no render was submitted, so no
embedded-workflow extract. Startup + `/object_info` presence is the
evidence that Equal Shares nodes still load.
