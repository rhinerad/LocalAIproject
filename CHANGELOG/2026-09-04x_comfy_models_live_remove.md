# 2026-09-04x — live `comfy_models(remove)` on a dummy file we created

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04x**.
Plan: `docs/COMFYUI_MCP_INTEGRATION_PLAN.md`. Separate from
`CHANGELOG/2026-09-04v_comfy_process_live_restart.md` and
`CHANGELOG/2026-09-04w_comfy_nodes_live_install.md`.

Did **not** delete `v1-5-pruned-emaonly-fp16.safetensors` or any other
operator weight. Target was a 37-byte dummy we wrote for this probe:
`embeddings/mcp_throwaway_probe.safetensors`.

## Attempts

1. Dummy under Shared `models/embeddings`, default
   `COMFYUI_PATH=ComfyUI-Shared`. MCP `MODEL_ERROR`: searched **0**
   launch-proven roots. Wrapper still wrote `risk=model_delete`. Probe
   unlinked the leftover itself.
2. Dummy under Rockernow `ComfyUI/models/embeddings`, MCP child
   `COMFYUI_PATH` set to Rockernow. MCP searched **1** proven extra root:
   `A:\Users\rhine\ComfyUI-Shared\models\embeddings` (from live argv
   `--extra-model-paths-config`). File was in the other tree, so
   not-found. Leftover unlinked.
3. **Live delete that landed:** dummy in Shared
   `models/embeddings/mcp_throwaway_probe.safetensors`, MCP child
   `COMFYUI_PATH` temporarily Rockernow (same split-install workaround
   as node install). `list` showed the dummy; `remove` unlinked it;
   `list` afterwards: embeddings empty.

MCP return:

```
Removed model:
  A:\Users\rhine\ComfyUI-Shared\models\embeddings\mcp_throwaway_probe.safetensors
  (0.0 MB freed)
```

File gone (`exists False`). No other model files touched.

## Audit log (`local_agent/runtime/comfy_mcp_audit.jsonl`)

Successful delete row:

```
{"ts": "2026-09-04T18:05:10", "local_tool": "comfy_models", "mcp_tool": "list_local_models", "action": "remove", "args": {"action": "remove", "path": "embeddings/mcp_throwaway_probe.safetensors"}, "risk": "model_delete"}
```

Correct fields: `local_tool=comfy_models`, `mcp_tool=list_local_models`,
`action=remove`, `args.path`, `risk=model_delete`. Earlier refuse rows
have the same shape (audit is intent, not MCP success).

Evidence: `.grok/long-running-background-tasks/comfy_models_remove_live.json`.
