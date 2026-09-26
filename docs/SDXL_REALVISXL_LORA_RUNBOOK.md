# RealVisXL / SDXL LoRA training

This runbook is for the local agent's RealVisXL image workflow. It is separate from the MiniMax H3 video LoRA process and must not modify it.

## Safety boundary

- The legacy `A:\Users\rhine\kohya_ss\.venv` is preserved; it is currently broken because its managed Python 3.11 runtime disappeared.
- Use only `A:\Users\rhine\kohya_ss\.venv-local-agent`, created by `work\setup_sdxl_lora_trainer.ps1`.
- Setup, verification, and dataset preflight never load the SDXL checkpoint or start a training job.
- A training run needs an explicit operator choice of dataset, objective, output name, and GPU permission.

## Decide the objective before collecting data

Train one objective per LoRA:

1. **Identity LoRA:** 20–30 varied, consented images of one adult subject. Use a unique trigger token. Do not mix artistic style teaching into this set.
2. **Style LoRA:** a consistent visual style with captions describing subject matter, composition, and lighting. Do not include private identities unless consented.

Keep source images and captions outside the project evidence tree. Store training outputs in a distinct local LoRA output directory after approval.

## Hardware-aware starting configuration

For RTX 5080 16 GB VRAM and an SDXL/RealVisXL checkpoint:

- resolution: 1024, with aspect-ratio buckets
- batch size: 1
- precision: bf16 when the isolated environment verifies it; otherwise fp16
- gradient checkpointing: enabled
- cache latents to disk: enabled
- first controlled run: UNet-only, rank 16, alpha 16
- UNet learning rate: `1e-4`; text encoder disabled for the initial run
- save every 250 steps; keep no more than three checkpoints

These are starting values, not a claim that a particular dataset will work. Evaluate before raising rank, steps, or adding text-encoder training.

## Setup and preflight

1. Run `work\setup_sdxl_lora_trainer.ps1 -Install`.
2. Run `work\setup_sdxl_lora_trainer.ps1 -Verify`.
3. Validate the selected dataset and generate its proposed training plan.
4. Produce baseline RealVisXL images using the final evaluation prompts.
5. Request a controlled training run. Do not automatically enqueue one.

## Acceptance check

Compare baseline and LoRA output with three fixed prompts: trigger-only, compositional variation, and an unrelated subject. Reject a run that merely memorizes training images, changes unrelated prompts, or has unstable faces, anatomy, lighting, or style.
