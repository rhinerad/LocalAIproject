# 2026-09-08 — Prompt collapse root cause

Audit of the reviewed-pack production ledger found the image mismatch was caused
by prompt assembly, not SDXL randomness. `backrooms_prompt_adapter.py` truncated
the still text at the shared `For every SDXL still...` LoRA paragraph. In the
reviewed source, each clip's unique shot description follows that paragraph, so
many effective prompts lost their actor/entity/action details and became a
generic apartment or empty Backrooms hallway. C015 also retained motion text in
a still prompt.

The adapter now removes only the shared LoRA boilerplate, preserves the unique
shot description, and the media gate rejects motion instructions and visible
camera requests. Existing rendered files were not overwritten. The interrupted
production revision remains evidence; corrected prompts require a fresh safe
production revision before video generation.
