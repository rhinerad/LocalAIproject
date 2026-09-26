# 2026-09-04j — comfyui-mcp live `comfy_system` + `comfy_generate`

Date: 2026-09-04. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04j**.
Plan: `docs/COMFYUI_MCP_INTEGRATION_PLAN.md`. Follow-up to
`CHANGELOG/2026-09-04e_comfyui_mcp_client_and_tools.md` (mocked tests +
handshake only; 8188 was down).

Did **not** live-call `comfy_models(remove)`, `comfy_nodes(install)`, or
`comfy_process` start/stop/restart.

## Preconditions (verified, not assumed)

- **Node:** `node --version` = **v24.15.0** (>= 22).
- **Port 8188:** already LISTENING when this pass started. Owner was
  Rockernow `ComfyUI\.venv\Scripts\python.exe` running `ComfyUI\main.py`
  with `--input-directory A:\Users\rhine\ComfyUI-Shared\input` and
  `--output-directory A:\Users\rhine\ComfyUI-Shared\output` (PIDs 42952
  parent / 40472 child). Did **not** start a second instance on top of it
  (`CLAUDE.md` "One ComfyUI, ever").
- **Stage supervisor:** `outputs/equal_shares/runtime/render_queue_owner.json`
  still names pid **16900** from 2026-08-10; that PID is dead.
  `render_supervisor.log` last line 2026-08-10 01:46:11
  (`ComfyUI API ready`). Equal Shares is paused; supervisor does not own
  8188.
- MCP child env unchanged: `COMFYUI_PATH=A:\Users\rhine\ComfyUI-Shared`,
  `COMFYUI_CODE_PATH=A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI`,
  `COMFYUI_URL=http://127.0.0.1:8188`.

## Live `comfy_system` (read-only)

`tools.comfy_system({"tool": "get_system_stats", "action": "stats"})`
against the running instance, **39.81s** including `npx -y comfyui-mcp`
spawn. Not a mock. Returned the same `/system_stats` payload as a direct
HTTP GET:

```
os=win32
comfyui_version=0.34.0
python=3.13.12
pytorch=2.10.0+cu130
deploy_environment=local-desktop2-standalone
device=cuda:0 NVIDIA GeForce RTX 5080 : cudaMallocAsync
vram_total=17094475776
vram_free=15679225856
input-directory=A:\Users\rhine\ComfyUI-Shared\input
output-directory=A:\Users\rhine\ComfyUI-Shared\output
```

Final live argv on the instance used for generate (after the attention
fix below): `--listen 127.0.0.1 --port 8188 --disable-auto-launch
--enable-manager --use-pytorch-cross-attention --reserve-vram 1
--extra-model-paths-config ...inst-1780719620766.yaml`.

## Live `comfy_generate`

Wrapper call (one successful render; one earlier enqueue failed — see
below):

```
tools.comfy_generate({
  "action": "image",
  "prompt": "a small red ceramic mug on a wooden table, studio lighting, photograph",
  "checkpoint": "v1-5-pruned-emaonly-fp16.safetensors",
  "width": 512, "height": 512, "steps": 8, "cfg": 5.0, "seed": 42,
  "batch_size": 1, "sampler": "euler", "scheduler": "normal"
})
```

MCP return (not mocked):

```
{
  "status": "enqueued",
  "prompt_id": "8182b9d1-e080-4d9e-9f85-bc5bccdb4be6",
  "queue_remaining": 1,
  "checkpoint": "v1-5-pruned-emaonly-fp16.safetensors"
}
```

`GET /history/8182b9d1-e080-4d9e-9f85-bc5bccdb4be6`:
`status_str=success`, `completed=true`, `execution_success` at
timestamp 1788549177909. SaveImage node 7 wrote
`ComfyUI_00214_.png`.

On disk: `A:\Users\rhine\ComfyUI-Shared\output\ComfyUI_00214_.png`
**317295 bytes**, **512×512 RGB**, LastWriteTime 2026-09-04 15:12:57.
`GET /view?filename=ComfyUI_00214_.png&type=output` → HTTP 200, 317295
bytes. That is a real file from this prompt_id, not a leftover.

## What broke the first enqueue (and what was changed)

First `comfy_generate` against the Desktop-style process
(`--use-ck-attention`) enqueued `prompt_id=504e0b22-b688-4e04-9a63-83832db547d3`
and died in VAEDecode:

`ValueError: Unsupported head_dim: 512` inside `sageattention` (global
`F.scaled_dot_product_attention` replacement). KSampler had already run.

Cause: `custom_nodes/ComfyUI-IF_Trellis` imports `trellis`, which assigns
`F.scaled_dot_product_attention = sageattn`, then the node itself fails
to finish importing (`Unknown attention module: flash_attn`). The sage
monkeypatch stays installed. `--use-ck-attention` vs pytorch does not
matter while that patch is live.

Fix for this pass (not `comfy_process`): stopped the unmanaged backend,
renamed `ComfyUI-IF_Trellis` → `ComfyUI-IF_Trellis.disabled` (already an
IMPORT FAILED node), restarted **one** Rockernow process with
`--use-pytorch-cross-attention` on 8188 pointed at Shared input/output.
Also left `ComfyUI-3D-Pack.disabled` (already IMPORT FAILED,
`torch_scatter` missing). Then the 8182b9d1 generate succeeded.

Did not call MCP `restart_comfyui`.

## Stopped there

No `comfy_models` delete, no `comfy_nodes` install, no MCP
`comfy_process`. Those still need their own explicit go-ahead.
