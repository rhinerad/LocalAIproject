# 2026-09-04t — `comfy_generate` audit log + probe output isolation

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04t**.

Follow-up to the mug-image investigation (desktop chat
`7d474ba55d244abe` vs Grok probes writing `ComfyUI_00214_.png` /
`ComfyUI_00215_.png` into the shared output root). Process/tooling
hygiene only. Empty-completion work and Option B timeshare are
untouched.

Mug evidence files were **not** deleted.

## 1. `comfy_generate` now appends `comfy_mcp_audit.jsonl`

Every real `tools.comfy_generate` call — desktop `tools.call` or a
Grok probe importing `tools` — writes one JSONL row:

- `ts`, `local_tool=comfy_generate`, `mcp_tool=generate_image`, `action`, `args`
- `risk=generate`
- `caller`: `pid`, `argv0`, first stack frame outside `tools.py` (`file`, `function`, `line`)
- `prompt_id` from the MCP return (or `null` on error)
- `mcp_status` `ok` / `error`

Deletes/installs/process-control keep their existing rows. Generate
errors are logged then re-raised.

## 2. Why `filename_prefix` did not take effect (confirmed, not patched)

Not a bug in our wrapper. `tools.comfy_generate` already forwarded
`filename_prefix` in the MCP args. History for live prompt_id
`8182b9d1-e080-4d9e-9f85-bc5bccdb4be6` shows SaveImage node 7
`"filename_prefix": "ComfyUI"` while the caller sent
`mcp_live_verify_20260904`.

Pinned `comfyui-mcp` 0.52.x (`npx` cache `8af3af54f44861ce`):

- `dist/tools/generate-image.js` action `"image"` does **not** pass
  `filename_prefix` into `generateImage(...)`. It **does** pass it for
  `"audio"`, `"video"`, and `"remove_background"`. The Zod description
  names only those three actions.
- `dist/services/workflow-composer.js` `buildTxt2Img` / `buildImg2Img`
  hardcode `filename_prefix: "ComfyUI"`. ControlNet / IP-Adapter /
  upscale hardcode `ComfyUI_controlnet` / `ComfyUI_ipadapter` /
  `ComfyUI_upscale`.
- Official schema (artokun.io / Glama): `filename_prefix` documented
  for audio, video, remove_background only.

This is a **comfyui-mcp limitation**. Documented in
`docs/COMFYUI_MCP_INTEGRATION_PLAN.md` §4b. `comfy_generate` is not
rewritten to rebuild their graph.

## 3. Probe isolation (not the operator generate path)

New `local_agent/mcp_test_output.py` (not a TOOLS entry):

- `save_prefix(stem)` → `mcp_test/<safe-stem>`
- `build_txt2img_graph(...)` sets SaveImage to that prefix (ComfyUI
  treats `/` as `output/mcp_test/`)
- `enqueue_txt2img` POSTs `/prompt` and audits the same JSONL

Scripts:

- `vram_comfy_phases_probe.py` now uses `enqueue_txt2img` (no more
  `comfy_generate` mug in the output root).
- `comfy_generate_live.py` still calls `comfy_generate` because that
  **is** the MCP live verify; after history it **copies** the file into
  `output/mcp_test/` and leaves the original `ComfyUI_*.png`.
- `.grok/long-running-background-tasks/README.md` records the rule.

## Tests (mocked — no live ComfyUI)

```
python local_agent/test_comfy_tools.py -v
  Ran 16 tests in 0.042s  OK

python local_agent/test_mcp_test_output.py -v
  Ran 3 tests in 0.008s  OK
```

New: generate audit includes `prompt_id` + caller file/function;
generate MCP error still writes a row; isolated graph prefix is
`mcp_test/...` not `ComfyUI`; enqueue mock POSTs `/prompt` and audits.
