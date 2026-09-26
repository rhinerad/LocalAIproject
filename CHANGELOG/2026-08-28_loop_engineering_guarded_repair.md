# 2026-08-28 — Loop engineering guarded repair stage

## Delivered

- Extended the disabled-by-default loop controller's repair proposal path to
  queue the proposed **exact** text in the existing sidebar file-edit gate.
- The controller still cannot call `write_file` or otherwise edit a project
  file. A normal, separately approved write path must consume the one-shot
  approval and apply the exact content.
- Added `verify_approved_repair`: it verifies the gate's approval history and
  the file's expected SHA-256 content digest before it reruns only the named
  fixed regression check.
- Added a stable post-repair failure fingerprint. Two identical failures after
  approved repairs halt retries and create an operator-review item.
- Added a non-consuming approval lookup to `file_edit_gate.request()` so a
  loop proposal cannot accidentally spend an already-issued one-shot approval.

## Verification

- `python local_agent/test_loop_controller.py` — 8/8 passing, including the
  independent-approved-write/retest path and the repeated-failure halt.
- `python local_agent/test_general_assistant.py` — 7/7 passing.
- `python local_agent/test_native_tool_calling.py` — 28/28 passing.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
  — 124/124 valid.

## Boundaries retained

- No render, model load, download, deletion, permission grant, or project file
  write was initiated by the loop controller.
- Protected-file safeguards and the existing exact-edit sidebar approval remain
  the authority boundary; a schema or loop record is never an approval.

## Independent-review control plane

- Added `local_agent/loop_independent_verifier.py`: an opt-in CPU-only,
  `keep_alive="0"` review call to the configured abliterated 8B model. It sees
  only the compact goal, diff/content fingerprints, targeted-test result, and
  deterministic evidence—not a project tree, tools, chat history, or hidden
  reasoning.
- Its strict JSON verdict is `supported` or `needs_operator`. Invalid model
  output, transport errors, and an unrequested call all fail closed to
  `needs_operator`.
- `agreement()` requires both a deterministic pass and an independent
  `supported` opinion, but returns only a policy result; it cannot write, grant
  permission, or make an autonomous completion claim.
- `python local_agent/test_loop_independent_verifier.py` — 3/3 stubbed tests
  passed. No local model was loaded for this verification; live calibration is
  separately gated.
