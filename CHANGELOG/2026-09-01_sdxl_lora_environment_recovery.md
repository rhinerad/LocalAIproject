# 2026-09-01 — SDXL LoRA environment recovery

## Diagnosis

The existing `A:\Users\rhine\kohya_ss\.venv` is not used or modified. Its uv trampoline cannot find the Python 3.11 child interpreter. Kohya's checked-in metadata requires Python `>=3.10,<3.12`; the workstation's available Python 3.12 cannot safely replace it.

## Added

- `work/setup_sdxl_lora_trainer.ps1` creates only a new `.venv-local-agent` from managed Python 3.11 and can verify imports without loading a model.
- `work/sdxl_lora_readiness.py` validates a chosen image/caption dataset without torch, GPU, checkpoint load, or training.
- `docs/SDXL_REALVISXL_LORA_RUNBOOK.md` separates RealVisXL/SDXL LoRA work from the MiniMax H3 video LoRA workflow and records RTX 5080-safe starting settings.

No image model, evidence, legacy environment, ComfyUI process, or training dataset was modified. Training remains operator-approved work.
