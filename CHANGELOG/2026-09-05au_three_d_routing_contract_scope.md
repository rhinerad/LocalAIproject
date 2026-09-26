# 2026-09-05au — 3D ComfyUI routing contract: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05au**.

Task #52. Design note only — no download, node install, enqueue, or tool.

Doc: `docs/design_notes/THREE_D_COMFY_ROUTING_CONTRACT_2026-09-05.md`.

## Live re-inventory (`inspect()` only)

Same conclusion as `CHANGELOG/2026-08-28_3d_inventory.md`:
`routing_ready` is False. TRELLIS-image-large assets (17) and
`hunyuan3d-dit-v2-0-fp16.safetensors` are on disk. Shared `workflows/`
has 16 MiniMax H3 JSON files and **zero** 3D graphs. Rockernow
`ComfyUI-Hunyuan3DWrapper` is present;
`ComfyUI-IF_Trellis.disabled` and `ComfyUI-3D-Pack.disabled` remain
from the 2026-09-04j sageattention break. Stable Fast 3D: no assets.

## What the note specifies

Bindings already required by `three_d_contract.py` (`prompt`,
`reference_image`, `mesh_output` with `node_id`/`input`; checksum-pinned
API workflow; `.obj`/`.glb`/`.stl`). Gaps to fill before a submitter:
Comfy `/prompt` API shape via existing `enqueue_workflow` (not
`comfy_generate` `action=3d`), output-root allow-list, queue/preflight
aligned with `comfy_process_preflight()` / `gpu_busy()` / thermal /
owner PIDs, exclusive GPU occupancy. Operator sign-off list is explicit
(pipeline pick, saved graph, contract `approved`, disabled-node
question, no new TOOLS entry until then).

No production code changed. Template stays `status: "draft"`.
