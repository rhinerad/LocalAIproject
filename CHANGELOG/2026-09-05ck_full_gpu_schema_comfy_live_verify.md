# 2026-09-05ck — Catalog-drowning fix live-verified with ComfyUI up (full 68-tool GPU schema)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ck**. No routing code
change. Re-verifies **2026-09-05bn** (the 2026-09-05bc build) under a real
Rockernow ComfyUI on `127.0.0.1:8188`, not a mock or unit-test pass.

## Why this ticket

2026-09-05bn's case 4 live hop selected `comfy_workflow` on Huihui-14B but
got `ECONNREFUSED` because `:8188` was down — no `prompt_id`. The
production farm-down path uses `gpu_core` (12 tools). This session also
drove the **pinned Huihui** path that still advertises the drowning
catalog (~68 tools, including `see_image` and `fetch_url`) while Comfy
was actually running.

## Preflight (one-backend-ever + thermal)

Before start: `:8188` closed, no `ComfyUI\main.py`, GPU **31 C / 67 MiB /
0%**, `render_supervisor.log` mtime 2026-08-10 (not advancing). Thermal
guard start ceiling 70 C — passed. One Rockernow backend started with the
standing flags (`--listen 127.0.0.1 --port 8188 --disable-auto-launch
--enable-manager --use-pytorch-cross-attention --reserve-vram 1` plus
extra-model-paths / shared input+output). Huihui-14B preloaded so
timeshare took `already_claimed` (avoids the harness `clear_vram` MCP
`client is not started` CPU-8B compact hop).

## Independent estimates (still live)

`artifacts/benchmarks/2026-09-05_full_gpu_schema/independent.json`

| | tokens | vs 16000 |
|---|---|---|
| old `len(json)/3.4` on case 4 + 68 tools | **19352** | over — would demote 14B→8B |
| 2026-09-05bn measured estimator | **11536** | under |

Full GPU schema count **68** (`see_image` present). `gpu_core` on the
same Comfy prompt: **12** (`see_image` absent).

## Live turn — pinned Huihui, full 68-tool schema, Comfy up

Harness: `artifacts/benchmarks/2026-09-05_full_gpu_schema_live.py`
(`agent.answer(..., model=huihui_ai/qwen3-abliterated:14b)`). Evidence:
`artifacts/benchmarks/2026-09-05_full_gpu_schema/case4_pinned_full_gpu.json`.
**205.6 s**.

**Hop 0 (the enqueue hop)**
- Tier: GPU **Huihui-14B**, timeshare `already_claimed`
- Wire: **68** schemas, `see_image=true`, `fetch_url=true`,
  `comfy_workflow=true`
- Live Ollama `prompt_eval_count`: **14360** (under 16k; old heuristic
  19352 would have demoted)
- Native tool: **`comfy_workflow` only** — not `fetch_url`, not
  `comfy_generate`, not `see_image`
- Args: `{tool: enqueue_workflow, action: enqueue, workflow_path:
  …/txt2img_mcp_test.json}`
- Result: `status=enqueued`, **`prompt_id=e9346c53-6654-48a2-8cde-3672f6bbfc9e`**,
  `queue_remaining=1`

**Hop 1** was CPU Huihui-8B compact (3 meta-tools) because after enqueue
the Comfy queue showed `running: 1` and timeshare yielded the GPU. Reply
only; the enqueue already succeeded.

**Comfy `/history/{prompt_id}`** (not simulated): `status_str=success`,
`completed=true`, output `mcp_test/task_completion_20260905_00003_.png`.

## Versus the pre-fix baseline

`artifacts/benchmarks/2026-09-05_catalog_drowning/huihui.json` (README
probe, 14B, 68 schemas, Comfy not involved): native call **`fetch_url`**
on `local_agent/README.md`, `prompt_eval_count=4098`. Same 68-tool
surface here, different operator prompt: Huihui-14B picked
**`comfy_workflow`** and Comfy accepted the graph.

Farm-down unpinned `gpu_core` path was already live-verified with Comfy
up in the prior session: 12-tool schema, Huihui-14B,
`comfy_workflow` → `prompt_id=75436fc1-9c95-4faa-9dbf-9ae424e0bfd2`
(`artifacts/benchmarks/2026-09-05_gpu_core/case4.json`). That is the
unpinned CAP_TOOL fallback; this ticket is the full-catalog pin.

## Cleanup (one-backend-ever)

Rockernow `main.py` killed. `:8188` down. Huihui 14B/8B `keep_alive:0`.
No Equal Shares content; no writes under `outputs/equal_shares/**`.
