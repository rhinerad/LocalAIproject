# 2026-09-08c - Prompt-pack evidence and approval repair

Scope: conversation f8f7f70e364d40c0, revision
72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a.

Baseline: managed_prompt_pack + media_accuracy_gate, 9 tests passed.
Implement attempt receipts, immutable media, semantic-not-run refusal,
explicit hash-bound approval, approved last-to-next-start chaining, and a
durable stale-progress watchdog. Extend bounded startup/owner/gate tests.
Update TODO, README, PowerInfer status cross-reference and current handoff.
No Equal Shares outputs, weights, predictors, registries or router changes.
Validation: 49 tests passed (37 local-agent production/integrity/identity tests
and 12 work.test_image_render tests). Baseline required suite: 9 passed.

Files changed: work/image_render.py, work/run_prompt_pack_production.py,
local_agent/prompt_pack_production.py, local_agent/media_accuracy_gate.py.
Added local_agent/production_integrity.py, local_agent/test_production_integrity.py,
work/audit_prompt_pack_production.py, work/verify_prompt_pack_startup.py.
Updated TODO.md, local_agent/README.md, work/POWERINFER_STATUS_2026-08-30.md;
added docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md; regenerated HANDOFF_STATUS.md.
The current ledger was snapshotted and paused_for_qa with automatic approval
disabled and semantic_check not_run; previous media and errors remain preserved.

Live evidence: initial 45-second startup-only timeout cleaned up successfully.
A second 90-second bounded probe reached /object_info (905 nodes) in 19.3627 s,
submitted zero graphs, and released port 8188. Original restricted-startup stacks
identify Numba cache creation in pack.py:44; project-local NUMBA_CACHE_DIR retained.
Paths and limitations are in the new handoff.

Physical audit found 139 historical PNGs / 139 jobs, 126 mechanical passes,
zero exact current-prompt matches, zero semantic passes/approvals/videos.
Exact installed V4 GGUF and matching Q8_0 projector hashes verified; lazy
llama.cpp runtime build 10516 / b95502ba9 identified without loading the model.
No real video approval/provenance example exists; chaining is fixture-tested only.
Semantic integration/execution remains pending; not_run cannot authorize video.

The worker starts its own independent watchdog for both direct CLI and app
launches, with a per-run token. Stale failure is sticky and must be diagnosed
before retry; unknown/live ownership blocks recovery. Supervisor launch is
serialized by an OS-held lock. Backend cleanup verifies command lines.
