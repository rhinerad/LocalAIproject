# 2026-09-04w — live `comfy_nodes(install)` against a throwaway git pack

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04w**.
Plan: `docs/COMFYUI_MCP_INTEGRATION_PLAN.md`. Separate from
`CHANGELOG/2026-09-04v_comfy_process_live_restart.md`.

Did **not** pip-install an arbitrary registry pack. Target was a local
throwaway repo with **no requirements.txt** and no third-party imports.

## Pack

Local git, commit `e047a3b5bd0ccbdd5da28a0bb099b64161fb23f3`:

- working tree: `.grok/long-running-background-tasks/comfyui-mcp-throwaway-probe/`
- bare clone (MCP requires a `.git` URL):
  `.grok/long-running-background-tasks/comfyui-mcp-throwaway-probe.git`
- node class `McpThrowawayProbe` returns the string `mcp-throwaway-probe`

## Attempts

1. `file:///…/comfyui-mcp-throwaway-probe` (no `.git` suffix) —
   MCP `VALIDATION_ERROR`: not a recognized git URL. Wrapper still wrote
   an audit row (audit happens before the MCP result).
2. Same URL with `.git` suffix, default `COMFYUI_PATH=ComfyUI-Shared` —
   MCP `PROCESS_CONTROL_ERROR`: would write `custom_nodes` under Shared,
   but the live listener is Rockernow
   (`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI`). Nothing written.
   Audit row written anyway.
3. **Live install that landed:** same `.git` URL, `mcp_client.COMFYUI_PATH`
   temporarily set to `COMFYUI_CODE_PATH` (Rockernow) for this call only,
   then restored. Git-clone fallback (not in Manager registry).

Return:

```
mechanism: git-clone
nodeDir: A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes\comfyui-mcp-throwaway-probe
warnings: []
message: cloned it directly into custom_nodes … RESTART ComfyUI to load it.
```

On disk: `__init__.py` present, matches the throwaway source. No pip
packages. ComfyUI was **not** restarted after this install (process
restart was already live-verified separately).

## Audit log (`local_agent/runtime/comfy_mcp_audit.jsonl`)

Successful clone row:

```
{"ts": "2026-09-04T18:01:49", "local_tool": "comfy_nodes", "mcp_tool": "install_custom_node", "action": "install", "args": {"action": "install", "id": "file:///A:/Users/rhine/.grok/long-running-background-tasks/comfyui-mcp-throwaway-probe.git", "source": "git", "ref": "main"}, "risk": "custom_node_install"}
```

Correct fields: `local_tool`, `mcp_tool`, `action`, `args.id` (the git
URL), `risk=custom_node_install`. The two earlier refuse rows have the
same shape because the wrapper logs intent, not MCP success.

Evidence: `.grok/long-running-background-tasks/comfy_nodes_install_live.json`.

The pack is still on disk under Rockernow `custom_nodes/`. It is a
no-op probe node, not loaded until a later restart.
