# Image/storyboard Phase 0 inventory — 2026-08-25

## What changed

- Added `work/notes/image_stack_inventory.md`, a read-only inventory and staged
  approval plan for the general image/storyboard roadmap.
- Added `work/image_render.py`, a core-node graph planner and owned-backend
  driver for text-to-image and reference image-to-image. Its `--plan` mode is
  read-only; execution requires explicit model-load authorization and refuses
  an existing backend/owner.
- The operator approved the exact `RealVisXL_V5.0_fp16.safetensors` download.
  The first transfer was retained as failed evidence after a checksum mismatch;
  a clean retry was verified and promoted without overwriting any file.

## Why

The image-stack plan requires a hard approval gate before model downloads or
generation. The workstation already has usable SDXL and ControlNet assets, so
an inventory prevents unnecessary duplicate downloads.

## Evidence and verification

- Read the live `http://127.0.0.1:8188/object_info` catalogue without submitting
  a workflow. It exposes samplers, SDXL checkpoint/LoRA/VAE/ControlNet nodes but
  not InstantID, IPAdapter FaceID, PuLID, or a GGUF loader.
- Read model directories only: the shared library contains DreamShaper XL,
  SDXL base, RealisticVision, SDXL ControlNet assets, CLIP Vision, and an
  incomplete InsightFace set (`inswapper_128` only).
- Verified upstream artifact metadata for RealVisXL V5 FP16 (6.94 GB) and
  InstantID's Apache-2.0 adapter/ControlNet source files (1.69 GB/2.50 GB).
- `python work/test_image_render.py` — **6/6 passed**, covering core t2i/i2i
  graph construction, live-node validation, read-only planning, explicit model
  load authorization, and refusal to reuse an existing ComfyUI backend. The
  real API plan was safely refused when the pre-existing server did not answer
  `/object_info` in time; no second backend was started.
- Verified installed RealVisXL SHA-256:
  `6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80`.

## Still unverified

- No checkpoint was loaded, no node was installed, and no image was generated.
  The owned-backend execution lifecycle is implemented; the measured first-image
  run remains model-load/render-gated.
