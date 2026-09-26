# 2026-09-05bn — GPU-core fallback schema + measured schema token estimate

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bn**. Builds both
fixes proposed in `CHANGELOG/2026-09-05bc`. Qwythos compact-when-farm-up
is unchanged.

## Fix 2 — measured per-schema token constant (independent)

`router.estimate_context_tokens` no longer does `len(json.dumps(messages+tools))/3.4`
for schemas. Message text still uses the character heuristic; each tool
schema adds `MEASURED_SCHEMA_TOKENS = 60` from live Qwen
`prompt_eval_count=4098` on a 68-schema wire (old estimate 11940).

Case 4 messages + **full 68-tool GPU catalog**:

| | tokens | vs 16000 |
|---|---|---|
| old `len/3.4` | **19352** | over (would demote 14B→8B) |
| new measured | **11536** | under — stays Huihui-14B |

## Fix 1 — `gpu_core` schema on farm-down tool GPU fallback only

Unpinned `CAP_TOOL` that would have gone to Qwythos, when farm is down or
`skip_farm=True`, sets `detail["gpu_tool_fallback"]`. `tools.profile_for`
returns `gpu_core`. Advertised tools: `CORE_DIRECT_TOOLS`, plus
`COMFY_CORE_TOOLS` when the prompt is a Comfy/workflow turn.

Not applied to: farm-up Qwythos (still 3 meta-tools), pinned Huihui
conversation, `CAP_CODE`/`CAP_LOGIC` specialists.

Case 4 curated catalog old `len/3.4` estimate: **9563** (under 16k even
without fix 2). 12 tools, no `see_image`.

## Tests

`test_capability_routing` + `test_native_tool_calling` +
`test_router_switching`: **160 OK**.

New: farm-up still Qwythos compact; farm-down / skip_farm is `gpu_core`;
Comfy prompt adds `comfy_workflow`; pinned Huihui keeps full GPU schema;
CAP_CODE is not `gpu_core`; estimator independently keeps case 4 under
16k; curated catalog independently under 16k on the old heuristic;
farm-down case 4 `decide()` picks Huihui-14B not 8B.

## Live (farm forced down)

Independent checks: `artifacts/benchmarks/2026-09-05_gpu_core/independent.json`.

**Case 1a** (10.2 s): Huihui-**14B**, `gpu_tool_fallback`, 6-tool core
schema, **`read_file`** `{path: local_agent/README.md}`. File contents
returned (`# Local Agent — a local ChatGPT Desktop equivalent`). 2026-09-05bc
with 68 tools had called `fetch_url`.

**Case 4** (50.2 s): Huihui-**14B** (not 8B), 12-tool core+comfy schema,
**`comfy_workflow`** `{tool: enqueue_workflow, action: enqueue, workflow_path: …txt2img_mcp_test.json}`
— the path-load wrapper from 2026-09-05d. Enqueue itself **ECONNREFUSED**
because Comfy :8188 was down. Tool selection and tier are the 2026-09-05b
gaps this ticket owns; a live `prompt_id` needs Comfy up.

Farm-up path was not used (forced `_farm_reachable=False` so this verifies
the fallback, not Qwythos).
