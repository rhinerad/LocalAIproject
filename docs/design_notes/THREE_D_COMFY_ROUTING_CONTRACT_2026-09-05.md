# Design: 3D generation ComfyUI routing contract

| Field | Value |
|---|---|
| **Document** | Operator-approved, checksum-pinned prompt-to-mesh route |
| **Date** | 2026-09-05 |
| **Status** | Scope only — do not build, download, install, enqueue, or add a tool |
| **TODO** | `TODO.md` “Local 3D generation through ComfyUI” |
| **Existing code** | `three_d_discovery.py`, `three_d_contract.py`, `config/3d_workflow_contract.template.json` |
| **Inventory** | `CHANGELOG/2026-08-28_3d_inventory.md` |

This is the next step after the 2026-08-28 inventory. `three_d_contract.validate`
already checks that a future file is complete and checksum-pinned. It **does
not** know node names, does not POST `/prompt`, and does not authorize a tool.
This note specifies what that file (and the later submitter) must contain.

No 3D job was queued. No custom node was enabled. No model was loaded.

---

## Live facts (re-read 2026-09-05, `inspect()` only)

`three_d_discovery.inspect()` against `A:\Users\rhine\ComfyUI-Shared`:

| Item | Result |
|---|---|
| `routing_ready` | **always False** (`three_d_discovery.py` ~43–46) |
| `workflows` matching TRELLIS / Hunyuan / SF3D markers | **`[]`** |
| Shared `workflows/` | 16 JSON files, all MiniMax H3 / lipsync / remix — **none** contain trellis/hunyuan/hy3d/sf3d |
| TRELLIS | 17 assets under `models/checkpoints/TRELLIS-image-large/` (pipeline.json + slat/ss fp16 safetensors, including `slat_dec_mesh_*`) |
| Hunyuan3D | **one** file: `models/diffusion_models/hunyuan3d-dit-v2-0-fp16.safetensors` (4 928 151 594 bytes) |
| Stable Fast 3D | **0** assets |
| Rockernow `custom_nodes` | `ComfyUI-Hunyuan3DWrapper` **present**; `ComfyUI-IF_Trellis.disabled`; `ComfyUI-3D-Pack.disabled` |

The two `.disabled` packs are the 2026-09-04j sageattention incident:
`ComfyUI-IF_Trellis` imported `trellis` which patched
`F.scaled_dot_product_attention`, then failed to finish importing; the
monkeypatch stayed and broke VAEDecode (`Unsupported head_dim: 512`).
**Re-enabling them is an operator decision, not a default of this contract.**

Hunyuan wrapper `NODE_CLASS_MAPPINGS` (on-disk `nodes.py`, **not** an
approved graph): `Hy3DModelLoader`, `Hy3DGenerateMesh`,
`Hy3DGenerateMeshMultiView`, `Hy3DExportMesh`, `Hy3DPostprocessMesh`,
`Hy3DLoadMesh`, plus paint/delight/multiview helpers. These names may fill
`required_node_types` **only after** an operator-saved API workflow uses
them. Do not copy them into the template as defaults — `three_d_contract.py`
deliberately ships empty `node_id` / `input` fields
(`config/3d_workflow_contract.template.json`).

`comfy_generate` already lists `action: "3d"` in its schema
(`tools.py` ~2924–2927). That is **not** this contract: MCP
`generate_image` builds an opaque composer graph, is not checksum-pinned,
and dumps into `ComfyUI-Shared\output` with the same mixing problem as the
mug stills (`CHANGELOG/2026-09-04j`). A 3D route must not be “call
`comfy_generate` with action=3d”.

---

## What `three_d_contract.py` already requires

`validate(contract_path, shared_root=)` (`three_d_contract.py` ~23–56):

| Field | Rule |
|---|---|
| `status` | exactly `"approved"` (template is `"draft"`) |
| `approved_by` | non-empty operator string |
| `workflow` | relative `*.json`, no `..`, not absolute; file exists under `{shared}/workflows/` |
| `workflow_sha256` | SHA-256 of that file’s bytes |
| `bindings` | **exactly** keys `prompt`, `reference_image`, `mesh_output`; each `{node_id, input}` non-empty strings |
| `required_node_types` | non-empty list of non-empty strings |
| `mesh_extensions` | non-empty subset of `.obj`, `.glb`, `.stl` |

Success means `ready_for_future_tool_review: True` — **not** “a tool may
submit.” A valid contract is a gate for a later review, same comment as
`CHANGELOG/2026-08-28_3d_inventory.md`.

---

## What the contract must still specify (gaps)

The validator does not pin GPU policy, queue/preflight, Comfy `/prompt`
shape, output root, or weight checksums. Fill these **in the same JSON**
(or a sibling section the future submitter reads). Suggested additional
keys; adding them is a validator change **after** operator sign-off, not
this pass.

### 1. Workflow node bindings (concrete, from a saved API graph)

ComfyUI **API format** only — `node_id -> {class_type, inputs}` — the same
rule `_normalize_api_graph` already enforces for `enqueue_workflow`
(`tools.py` ~869–893). UI exports (`nodes`/`links` arrays) are refused.

Bindings already named by the validator:

| Binding | Meaning | How a submitter uses it |
|---|---|---|
| `prompt` | `{node_id, input}` | Overwrite `graph[node_id]["inputs"][input]` with the operator text |
| `reference_image` | `{node_id, input}` | Load-image node input. Text-only jobs: contract must say whether this node is skipped or fed a documented blank; do not invent a hidden default |
| `mesh_output` | `{node_id, input}` | Export node (filename prefix / format). Output files must use only `mesh_extensions` |

Optional later bindings (not in the validator today): `seed`, `negative`,
`ckpt_name`. Do not add them until the saved graph actually has those
inputs.

`required_node_types` must be the **exact** `class_type` strings from that
graph, and those types must be loaded in the **live** Rockernow
`object_info` (not merely present as a folder). A graph that lists
`Hy3DGenerateMesh` is still unroutable if the wrapper fails to import.

### 2. Exact ComfyUI API JSON payload

Do **not** inline the graph in a model tool call (`_coerce_enqueue_workflow`
already loads a path server-side, `tools.py` ~916–946).

Submit path (existing, no new HTTP client):

```
tools.comfy_workflow({
  "tool": "enqueue_workflow",
  "action": "enqueue",
  "workflow": "<relative or absolute path to the pinned API JSON>"
})
```

That wrapper POSTs through MCP to Comfy `/prompt`. Native shape (what
ComfyUI actually queues):

```json
{
  "prompt": {
    "<node_id>": {
      "class_type": "<RequiredType>",
      "inputs": { "...": "..." }
    }
  },
  "client_id": "<optional>"
}
```

The future 3D submitter (not this pass) should:

1. `three_d_contract.validate(...)`.
2. `json.loads` the pinned workflow; refuse if `class_type` set ≠
   `required_node_types` (order-insensitive).
3. Patch only the binding inputs; refuse extra keys from the model.
4. Enqueue via `comfy_workflow` / `_mcp_call("enqueue_workflow", ...)`.
5. `_comfy_audit` with `risk: "generate"`, `prompt_id`, `caller`,
   **and** `workflow_sha256` (audit rows today lack checksum —
   `tools.py` ~780–797).

A future dedicated `three_d_generate` tool is **optional** and
**operator-gated**. Until then, even a valid contract does not add a
TOOLS entry.

### 3. Output paths (OBJ / GLB / STL)

Validator already limits extensions. Missing today: **root**.

Proposal, consistent with generated-media v1 allow-lists
(`server.py` `STORY_OUTPUT_ROOT` / forbidden `equal_shares`, `uploads`,
`chats`):

| Rule | Value |
|---|---|
| Root | `ComfyUI-Shared/output/3d/` (subfolder via export-node `filename_prefix`, slash = subdir — same as `mcp_test_output.save_prefix`) **or** a new `outputs/meshes/` under the handoff tree. Pick one in the contract; do not write both. |
| Extensions | Only the contract’s `mesh_extensions` |
| Forbidden | `outputs/equal_shares/**`, `local_agent/uploads/`, `local_agent/chats/`, MiniMax H3 workflow outputs |
| Evidence | Keep the file on disk + audit JSONL + `prompt_id`. Do not treat a chat card as proof (media v1 is images-only and story stills). |
| Naming | Prefix must include a stem the operator can grep; do not use MCP’s hardcoded `ComfyUI` image prefix |

`Hy3DExportMesh` (on disk, unreviewed) is a candidate export node; the
contract’s `mesh_output` binding must name the **actual** input that
controls path/format in the saved graph.

### 4. Queue / preflight

Reuse live gates; do not invent a second occupancy theory.

**Refuse to enqueue** (same spirit as `render_story_image`,
`tools.py` ~1832–1867, and `comfy_process_preflight`, ~998–1005):

1. `router.gpu_busy()` true — includes live `queue_owner` PID, **port
   8188 listening**, nvidia-smi fail-closed (`router.py` module docstring
   signals 1–3). A 3D job on the shared Rockernow instance **is** a
   ComfyUI claim; if 8188 is already a MiniMax/image_render/H3 session,
   do not pile on.
2. `router.queue_owner()` live PID — Equal Shares stage supervisor.
3. `batch_render_queue_owner.json` live PID — `_supervisor_owns_comfyui`.
4. `work/runtime/image_render_owner.json` live PID — same helper.
5. `thermal_guard.sample_gpu()` — unknown telemetry fail-closed;
   `temperature_c > START_MAX_C` (default 70) or `>= EMERGENCY_C`
   (default 82) refuse (`tools.py` ~949–974, `thermal_guard.py` ~16–19).
6. `gpu_gate.request("ComfyUI 3D mesh", ...)` on desktop; Block mode
   refuses; pending sidebar is not a silent start (`render_story_image`
   pattern).
7. Comfy queue not idle if we are attaching to the shared 8188: MCP
   `queue` list with `running`/`pending` **int == 0**, same timeshare
   occupancy rule (`docs/COMFYUI_GPU_TIMESHARE_CLEAR_VRAM.md`).

**Do not** call `comfy_process(restart)` to “make 3D work.”
`comfy_process_preflight()` exists to **stop** restart when thermal or a
supervisor owns the GPU. A 3D tool that restarts ComfyUI to load Hunyuan
would fight “One ComfyUI, ever.”

**Queue semantics:** one prompt at a time on 8188. Poll
`comfy_system get_history` / `/history/{prompt_id}` for completion; do
not claim a mesh from enqueue JSON (`status: enqueued` is not an output
file — same lesson as `comfy_generate`).

### 5. GPU ownership

One process owns the RTX 5080.

| Situation | 3D submitter |
|---|---|
| Idle 8188, gate granted, thermal OK, no owner PIDs | May enqueue the **pinned** graph on the existing Rockernow instance |
| Image render / batch / Equal Shares owner live | Refuse |
| Agent chat holding a 14B | Timeshare `/free` is a `decide()` concern, not a 3D restart. Do not `/free` from a 3D tool. |
| Hunyuan ~5 GB fp16 + TRELLIS mesh decoder | Fits 16 GB only if nothing else is resident. Contract should state **exclusive** occupancy, not “share with Huihui 14B.” |
| TRELLIS custom node still `.disabled` | TRELLIS weights on disk **do not** make a TRELLIS route. Enabling `ComfyUI-IF_Trellis` needs a separate sageattention sign-off. |

A 3D job is **not** a farm/Qwythos task and **not** a CPU Ollama path.

---

## Recommended contract JSON (fields beyond today’s template)

Keep every key `three_d_contract.validate` already demands. Add (future
validator, after sign-off):

```json
{
  "status": "draft",
  "approved_by": "",
  "pipeline": "hunyuan3d-wrapper | trellis | stable-fast-3d",
  "workflow": "3d/<name>.api.json",
  "workflow_sha256": "",
  "weight_pins": [
    {
      "relpath": "models/diffusion_models/hunyuan3d-dit-v2-0-fp16.safetensors",
      "sha256": ""
    }
  ],
  "required_node_types": [],
  "bindings": {
    "prompt": {"node_id": "", "input": ""},
    "reference_image": {"node_id": "", "input": "", "optional": true},
    "mesh_output": {"node_id": "", "input": ""}
  },
  "mesh_extensions": [".glb"],
  "output_root_id": "shared_output_3d",
  "output_prefix": "3d/operator_stem",
  "preflight": {
    "require_gpu_idle": true,
    "require_empty_comfy_queue": true,
    "honor_comfy_process_preflight": true,
    "gpu_gate_workload": "ComfyUI 3D mesh",
    "forbid_comfy_process_restart": true
  },
  "submit": {
    "mechanism": "enqueue_workflow",
    "forbid_comfy_generate_action_3d": true
  }
}
```

`reference_image.optional` would be a validator change: today’s schema
requires the key even for text-only. Until that change, a text-only
graph must still name a dummy binding that the submitter leaves
untouched — ugly; prefer operator choosing i2mesh vs t2mesh as **two
contracts**.

---

## Operator sign-off (required before any build)

Do not implement a submitter, enable `.disabled` nodes, download SF3D, or
add `TOOLS["three_d_*"]` until the operator explicitly approves:

1. **Pipeline pick:** Hunyuan wrapper (node pack already enabled) vs
   TRELLIS (weights present, **custom node disabled** after
   sageattention) vs SF3D (no weights). Inventory does not pick for you.
2. **A saved API-format workflow** under `ComfyUI-Shared/workflows/`,
   exported from a graph that actually ran once **in the ComfyUI UI**
   (human click, not this agent). Checksum that file into the contract.
3. **Fill `3d_workflow_contract.template.json`:** `status: "approved"`,
   real `approved_by`, exact `node_id`/`input` bindings, `required_node_types`
   matching the graph, `mesh_extensions`.
4. **Weight pin (recommended):** SHA-256 of
   `hunyuan3d-dit-v2-0-fp16.safetensors` (and TRELLIS safetensors if that
   pipeline is chosen). Not in the validator today.
5. **Custom nodes:** leave `ComfyUI-IF_Trellis.disabled` and
   `ComfyUI-3D-Pack.disabled` unless the operator accepts another
   sageattention / import-failure investigation.
6. **GPU exclusivity:** 3D enqueue refuses when `gpu_busy()`, thermal
   over `START_MAX_C`, or any owner PID is live; no `comfy_process`
   restart to load weights.
7. **Output root + prefix** so meshes do not land as anonymous
   `ComfyUI_#####` next to mug stills.
8. **No new tool** until (1)–(7) are on disk and
   `three_d_contract.validate` returns ready **and** a separate review
   says a `TOOLS` entry is wanted. `enqueue_workflow` of the pinned file
   by a human is enough for a first live mesh.

Until those exist, `routing_ready` stays False, the template stays
`draft`, and `comfy_generate` `action=3d` remains an unpinned MCP
composer path — not the 3D product.

---

## Explicitly not this pass

- Download Hunyuan/TRELLIS/SF3D extras
- `comfy_nodes(install)` for 3D packs
- Rename `.disabled` custom nodes
- POST `/prompt` or `enqueue_workflow` of a 3D graph
- New `tools.py` entry
- Validator schema expansion (listed above as post-sign-off)
- Chat mesh preview (media v1 is story stills only)

---

## v1 cut when (and only when) sign-off exists

1. Operator-placed API workflow + filled approved contract.
2. Extend `three_d_contract.validate` with `preflight` / `submit` /
   `output_prefix` if those keys were approved.
3. Submitter: validate → patch bindings → `enqueue_workflow` → audit
   with sha256 → poll history → return mesh paths under the allow-listed
   root. Still no `action=3d` composer.
4. Tests: checksum mismatch still `ContractError`; missing node type
   refuses; `gpu_busy` / thermal / owner PID refuse without enqueue
   (mirror `test_render_story_image` / `comfy_process_preflight`).
