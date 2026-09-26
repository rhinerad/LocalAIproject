# 2026-09-05d — `comfy_workflow` loads a local graph file for enqueue

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05d**.
Parent: live fail `CHANGELOG/2026-09-05b_routed_model_task_completion.md`
case 4.

## Why

Huihui 8B called `enqueue_workflow` with `workflow_path=<json>` then with
`workflow="<same path string>"`. MCP requires `workflow` as a record
(node id → `{class_type, inputs}`). Models must not inline a ComfyUI
graph in a tool call.

## What shipped

`local_agent/tools.py` `comfy_workflow` / `_coerce_enqueue_workflow`:

- `tool=enqueue_workflow` and `action` empty or `enqueue`: if `workflow`
  is already an API-format object, validate and forward. If it is a JSON
  string of that object, parse it. If it is a local path — or
  `workflow_path` / `path` / `file` / `filename` is set — load and parse
  the file server-side (absolute or repo-relative, same rule as
  `read_file`). Default `action` to `enqueue` when omitted.
- Path aliases are stripped before the MCP call.
- URLs refused. Missing file / invalid JSON / UI-format (`nodes`/`links`)
  raise `ToolError` and do not call MCP. Size cap 4 MiB. Optional
  `{prompt: <graph>}` wrapper unwrapped.
- Schema + TOOLS one-liner tell the model to pass a file path, not the
  graph.

`test_comfy_tools.py`: 16 → **25**. New: dict passthrough, `workflow_path`,
path-in-`workflow`, JSON string, prompt wrapper, missing file, URL, UI
format, `queue` ignores `workflow_path`.

```
python local_agent/test_comfy_tools.py -v
  Ran 25 tests in 0.043s
  OK
```

## Live verify

Rockernow :8188 was down; started one instance
(`ComfyUI\.venv\Scripts\python.exe` `main.py` `--listen 127.0.0.1 --port 8188`
same argv as `start_comfy_rockernow.bat`). GPU Ollama empty. Equal Shares
not touched.

Direct wrapper call (the 2026-09-05b first shape, not a mocked MCP):

```
tools.comfy_workflow({
  "tool": "enqueue_workflow",
  "action": "enqueue",
  "workflow_path": ".../txt2img_mcp_test.json"
})
```

MCP return (35.3 s including generate):

```
{"status": "enqueued", "prompt_id": "60b78f0f-f3e1-4f11-b4bc-2239e438ff5f",
 "queue_remaining": 1}
```

`GET /history/60b78f0f-f3e1-4f11-b4bc-2239e438ff5f`: `status_str=success`,
`completed=true`. SaveImage wrote
`A:\Users\rhine\ComfyUI-Shared\output\mcp_test\task_completion_20260905_00001_.png`
**446242 bytes**. Isolated `mcp_test/` prefix from the graph; not the
operator `ComfyUI_*.png` root.

Receipt:
`artifacts/benchmarks/2026-09-05_task_completion/enqueue_path_live.json`.

## Not changed

No router/agent/prompt edits. `comfy_generate` still does not honor
`filename_prefix` for action image (upstream MCP). Compact `call_tool`
unwrap still hits this wrapper, so a farm model that passes a path now
gets the same load.
