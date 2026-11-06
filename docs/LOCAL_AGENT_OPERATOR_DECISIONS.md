# Local Agent — operator decisions that unlock the remaining work

This is a short, non-executing decision sheet derived from `TODO.md`. It does
not grant GPU use, access to private data, networking, device access, model
downloads, rendering, or archival by itself. Each decision remains subject to
the existing local-agent safety gates.

## 1. First SDXL LoRA smoke run

Provide all of the following in one message:

- objective: `consented identity` or `style`;
- dataset folder to use, with confirmation that its material may be used for
  this bounded test;
- trigger token and desired output name;
- 3–5 evaluation prompts;
- approval for one bounded GPU smoke run.

Expected result: a single isolated LoRA run and fixed RealVisXL baseline
comparison. No production exposure follows automatically.

## 2. Historical-chat review-only staging

Provide:

- which export type to stage first (`ChatGPT`, `Claude`, or another named
  export);
- exact source file/folder;
- confirmation that review-only extraction may read it;
- whether its sanitized candidates should remain local for your review.

Expected result: encrypted, review-required candidates only. Nothing is added
to active memory or Chroma without a separate approval.

## 3. PowerInfer evaluation

There are two distinct paths; choose one, not both by implication:

- **ReluLLaMA diagnostic comparison:** approve a fresh isolated GPU quality
  comparison against the existing Ollama route. Current evidence says this
  candidate failed 9/10 instruction/format cases, so this is diagnostic only.
- **TurboSparse continuation:** supply at least 32 operator-approved paired
  harmful/harmless calibration prompts and approve a separate GPU window.
  The parked `20260830b` tree uses only eight synthetic pairs and cannot be
  promoted, profiled, converted, benchmarked, served, or routed.

PowerInfer remains loopback-only and separate from ComfyUI, VLM media work,
and worker-farm processes.

## 4. Phone / mobile-edge work

Choose the next physical test:

- paired-phone capability and scheduled-message test through Sideband; or
- Pixel 4B sparse-runtime test with the phone present for battery/thermal
  observation; or
- defer phone hardware and only review the private-overlay gateway design.

No phone test grants broad file access, unattended APK installation, or remote
render control.

## 5. Backup and archival

Provide:

- approved destination (drive, network location, or storage provider);
- who holds the recovery secret and where its recovery instructions live;
- source roots to include;
- an execution window for the first encrypted archive and a small restore
  drill.

## 6. Local 3D generation

Before any 3D model/node/job work, choose one engine and provide or approve an
exact ComfyUI workflow/API JSON contract:

- Hunyuan3D;
- TRELLIS; or
- Stable Fast 3D.

The contract must name node bindings, input/output paths, queue/preflight
behavior, GPU ownership, and the expected OBJ/GLB/STL output.

## 7. Future hardware only

These remain intentionally deferred until the hardware and credentials exist:

- secondary laptop private-overlay enrollment;
- Pixel Android sparse-runtime cross-build and physical validation;
- 10-node worker farm;
- trusted Android companion/application delivery.

## Safe response format

For example:

```text
Approve item 1. Use style data at <folder>. Trigger: <token>. Output: <name>.
Prompts: <prompt 1>; <prompt 2>; <prompt 3>. Approve one bounded GPU run.
```

or:

```text
Approve item 5. Destination: <location>. Secret custody: <method>.
Sources: <paths>. Window: <time>.
```
