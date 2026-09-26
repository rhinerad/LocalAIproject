# 2026-09-08e - Prompt-pack evidence gates finish-and-prove

Scope: finish/prove Codex mid-flight prompt-pack evidence gates for conversation
`f8f7f70e364d40c0` / revision
`72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a`.
No Equal Shares, weights, predictors, registries, or router changes. Local agent
on :8760 left DOWN. No Comfy full production or videos started. Startup verify
skipped (operator step; avoid unnecessary backend probe).

## Inventory vs Codex TODO

Already landed before this pass (syntax clean; `py_compile` OK):
attempt receipts, versioned evidence copies, hash-bound explicit approval,
approved last→next video chaining (fixture-tested), independent stale-progress
watchdog, `production_integrity` + worker/audit/startup scripts, ledger
`paused_for_qa` with `auto_approve_video=false` and `semantic_check=not_run`.

Gap closed this pass:
- `local_agent/test_media_accuracy_gate.py` was free-function asserts and
  contributed **0** tests under `python -m unittest` (suite silently skipped it).
- Converted to `unittest.TestCase` (2 tests) and asserted fail-closed semantics.
- `media_accuracy_gate.check_still` now sets `approval_status: "unapproved"` when
  `semantic_check: "not_run"` (mechanical pass alone cannot authorize).

Still open (operator / later code, not this pass):
- Wire/execute exact Qwen2.5-VL Caption V4 lazy llama.cpp semantic QA.
- Regenerate current-prompt still candidates through receipts; explicit operator
  still approval.
- One real approved-input video provenance check after still gate passes.

## Validation

```
python -m py_compile local_agent/production_integrity.py
  local_agent/test_production_integrity.py local_agent/prompt_pack_production.py
  local_agent/media_accuracy_gate.py work/run_prompt_pack_production.py
  work/image_render.py work/audit_prompt_pack_production.py
  work/verify_prompt_pack_startup.py
```
OK.

```
python -m unittest local_agent.test_managed_prompt_pack
  local_agent.test_media_accuracy_gate local_agent.test_prompt_pack_production
  local_agent.test_production_integrity -q
```
**32 passed** (9 + 2 + 5 + 16).

CPU-safe physical audit (no model load, no graphs):
`python work/audit_prompt_pack_production.py --cid f8f7f70e364d40c0`
→ `audits/physical_5b9a98e604794fe8bf11a16b2552811d.json`

| Metric | Count |
| --- | ---: |
| Historical PNG files | 139 |
| Distinct still jobs with PNGs | 139 |
| Current-prompt matching jobs | 0 |
| Mechanically passing jobs | 126 |
| Semantically passing jobs | 0 |
| Approved jobs | 0 |
| Ledger stills_generated / qa_passed / approved | 0 / 0 / 0 |
| Ledger videos_* | 0 |

VLM identity verified without load: model + projector SHA-256 match expected;
llama-server build 10516 / b95502ba9. Semantic QA remains `not_run`.

## Docs

Updated TODO.md (08c finish note), `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md`,
light PowerInfer status cross-ref; regenerated `HANDOFF_STATUS.md`.
