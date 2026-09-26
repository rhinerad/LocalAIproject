# 2026-08-29 — Model Conversion & Profiling preparation track

## What changed

- Added `docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md`.
- Added a Kanban-ready mandatory preparation phase to `TODO.md`.
- Linked the new gate to the PowerInfer control-plane plan and Claude/current
  handoff notes.

## Architecture decision

PowerInfer conversion is treated as a lineage-controlled offline process, not a
generic “convert any GGUF/Safetensors” operation. A candidate must have
evidence for its exact architecture, predictor, activation statistics,
calibration manifest, conversion artifacts, hashes, baseline comparison, and
resource-release behavior before it can reach the interactive Control Plane,
Harmon Town post-LoRA stage, or Judge loop.

## Deliberate non-changes

- Did not download, merge, profile, convert, quantize, load, or deploy any
  model.
- Did not create a model vault, modify GPU routing, start a GPU process, or
  alter ComfyUI, the worker farm, or the local-agent picker.

## Evidence boundary

The inspected upstream PowerInfer documentation states that its special GGUF
contains model and predictor weights and documents conversion from original
weights plus predictor weights. It lists limited sparse model families and says
ordinary llama.cpp-compatible model weights may run for compatibility without
sparse performance gain. This plan therefore puts predictor/profiler method
verification before any claimed automation for abliterated or LoRA-merged
checkpoints.
