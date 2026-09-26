# 2026-09-01 — LoRA workflow launchers

Five verified saved ComfyUI graphs with LoRA controls now have double-click
launchers under `local_agent/LORA_WORKFLOW_SHORTCUTS/`.

Each launcher calls the installed Comfy Desktop executable with the original
workflow JSON as an argument. It validates both paths before opening anything.
The index identifies the specific LoRA nodes so the operator can change only
the intended LoRA filename and strength. No workflow JSON, LoRA file, ComfyUI
configuration, GPU owner, render queue, or active render was modified.
