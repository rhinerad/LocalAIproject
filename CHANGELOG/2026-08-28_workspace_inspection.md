# 2026-08-28 — Read-only workspace inspection

## What changed

- Added `inspect_workspace`, a read-only tool that examines an explicitly
  supplied local root and reports its classified project type, confidence,
  lightweight evidence, and likely authoritative documentation.
- Classification is deliberately conservative: only distinctive Equal Shares
  markers select that type. A generic ComfyUI folder remains a general ComfyUI
  project; code repositories and dataset/LoRA folders get their own types.
- The inspection result cannot change a chat workspace, authorize a tool,
  start a render, or loosen any file or GPU guard.
- Added deterministic fixture coverage for code repositories, dataset/LoRA
  projects, generic ComfyUI projects, and Equal Shares projects.
- Added `workspace_evaluation.py`, a reviewable nine-case aggregate baseline.
  It measures specialist-context routing and project-only schema exposure
  without calling a model or recording chat contents.
- Replaced operating-memory keyword deletion with explicit reviewed Markdown
  sections: General policy, Machine policy, and Project policy. General chats
  cannot receive the entire project block because it happens to contain an
  unrelated shared word.

## Verification

- `test_workspace_inspector.py`: **4/4 pass**.
- `test_workspace_profiles.py`: **3/3 pass**.
- `test_workspace_evaluation.py`: **1/1 pass**; baseline is **9/9** scope and
  schema checks, with **0** false specialist activations, **0** missed
  specialist activations, and **0** false project-tool exposures.
- `test_operating_memory.py`: **2/2 pass** (scoped block exclusion plus legacy
  unsectioned-file compatibility).
- `test_general_assistant.py`: **7/7 pass**.
- `test_native_tool_calling.py`: **28/28 pass**.
- Tool catalog: **53 tools / 53 schemas**.
- `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.

## Deliberately not changed

- Workspace inspection does not infer authority from a chat history or alter
  the persisted workspace choice.
- It does not access the network, start a model, submit a ComfyUI job, or
  modify project files.
- This does not make an inferred workspace authoritative: the explicit chat
  workspace choice remains the only persistent scope control.
