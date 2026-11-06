# 2026-08-25 — portfolio ADRs and sanitized architecture diagrams

## Added

- Five evidence-linked Architecture Decision Records under `docs/adr/`:
  localhost/LXMF transport, native tool calling, lazy VLM/render ownership,
  explicit-feedback-only learning, and GPU/CPU fallback.
- `docs/portfolio/architecture_overview.md` with sanitized Mermaid diagrams for
  system boundaries, GPU lifecycle, and remote-permission decisions.

## Scope and guardrails

- The diagrams intentionally omit paths, identities, radio configuration,
  private media, prompts, tokens, and model-file locations.
- LoRa/RNode is labeled experimental; Android Tier B remains in progress.
- These documents describe design and existing evidence. They do not claim new
  performance, render, transport-reliability, or device acceptance results.

## Verification

- `python -m json.tool local_agent/memory.json` passed after persistent-memory
  update.
- ADR claims were cross-checked against the current handoff, local-agent README,
  native tool loop, LXMF bridge, and current changelog entries.

## Follow-up update

- Added `docs/portfolio/validation_matrix.md` to keep verified tests, pending
  device checks, and pending measurement work distinct in one reproducible,
  sanitized index.

## License triage

- Added `docs/portfolio/dependency_license_inventory.md` from local requirement
  files and bundled license texts.
- Marked Sideband-derived source private: its bundled license is CC BY-NC-SA
  4.0 and the bundled LXST component is CC BY-NC-ND 4.0. This is a release
  boundary, not a legal conclusion about unrelated, independently written code.

## Sanitized-demo preparation

- Added `docs/portfolio/sanitized_demo_runbook.md`: a no-download, no-render
  preparation and redaction checklist for a future portfolio recording.

## Portfolio audit follow-up

- Replaced the VLM benchmark draft's private runtime-output reference with the
  portable `artifacts/benchmarks/` path. The public-release audit now passes
  against the complete `docs/portfolio` tree with zero findings.

## VLM benchmark harness

- Added `local_agent/measure_qwen25_vl_lifecycle.py` and a static safeguard
  test. Its default invocation is plan-only; a live run requires `--execute`,
  refuses render ownership, records only metadata/hashes, and releases the
  exact lazy runtime in `finally`.
- Verified the plan-only invocation and static test without loading a model.

## Follow-up validation

- The public-release audit now passes against `docs/portfolio` with zero
  findings. The validation matrix writes aggregate evaluation output to a
  portable `artifacts/evaluations/` path rather than a private runtime path.
- The older `local_agent/UPGRADE/BUILD_STATUS.md` remains explicitly marked as
  superseded; its canonical successor is the updated current handoff.
- Added `docs/portfolio/public_release_boundary.md`, which separates candidate
  open-source patterns from private material and makes the remaining audit gates
  explicit.

## Current regression evidence

Run 2026-08-25 without model loading, rendering, or a network request:

- `python local_agent/test_native_tool_calling.py` — **19/19 passed**.
- `python local_agent/test_h3_evaluation.py` — **1/1 passed**.
- `python local_agent/test_lxmf_bridge.py` — **11/11 passed**.
- `python local_agent/test_sideband_tier_b.py` — **4/4 passed**.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
  — **124/124 valid**.

## Offline public-release audit foundation

- Added `local_agent/public_release_audit.py`: non-destructive scanner for a
  proposed public tree. It reports only rule/path/line metadata and never echoes
  a matched secret value.
- `python local_agent/test_public_release_audit.py` — **2/2 passed**.
- `python local_agent/public_release_audit.py --dir docs/adr --json` — **0
  findings**. This is an early content check, not a final license/secret audit
  for a future public repository.

## Local-only public candidate verification

- Verified the existing separate `local-agent-core` candidate repository with
  10/10 synthetic tests and zero findings from the non-destructive release
  audit. No remote repository was created or published.
- Corrected its README quick-start instructions so a source-layout checkout
  sets `PYTHONPATH=src` before running tests/audit.
# Follow-up validation

- The public-release audit now passes against `docs/portfolio` with zero
  findings. The validation matrix writes aggregate evaluation output to a
  portable `artifacts/evaluations/` path rather than a private runtime path.
