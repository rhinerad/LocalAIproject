# 2026-08-28 — Record future local 3D generation capability

## Recorded only; no runtime behavior changed

- Added a low-priority backlog item for guarded local 3D mesh generation from
  text and optional visual references through ComfyUI.
- Candidate local pipelines: Hunyuan3D, TRELLIS, and Stable Fast 3D.
- Intended reviewed outputs: OBJ, GLB, and STL.

## Explicit gate

This capability remains inactive until exact local ComfyUI API workflow JSON,
node inputs, output paths, queue/preflight behavior, and GPU-ownership routing
are captured and validated. No models or nodes were downloaded, no workflow was
submitted, and no render was started by this record.
