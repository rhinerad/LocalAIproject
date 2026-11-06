# 2026-08-28 — Local 3D inventory

## What changed

- Added `three_d_discovery.py`, a read-only inventory utility for the shared
  ComfyUI model library. It reports relevant local TRELLIS, Hunyuan3D, and
  Stable Fast 3D asset paths plus any saved matching workflow JSON.
- The live inventory finds TRELLIS image assets and
  `hunyuan3d-dit-v2-0-fp16.safetensors`, but no saved 3D workflow JSON or
  reviewed node/API output contract.

## Safety boundary

- The utility does not load weights, contact the network, change ComfyUI,
  create a local-agent tool, queue a job, or claim the GPU.
- `routing_ready` is deliberately always false. Model files do not establish a
  safe prompt-to-mesh route; a reviewed workflow, installed nodes, preflight,
  GPU ownership, and output-path contract remain required.
- Added a checksum-pinned contract validator and a deliberately invalid draft
  template. It does not supply node types or IDs: those must come from an
  operator-reviewed workflow. A valid contract only means it is ready for a
  later tool review, never that a 3D job is authorized.

## Verification

- `test_three_d_discovery.py`: **1/1 pass**.
- `test_three_d_contract.py`: **1/1 pass**.
