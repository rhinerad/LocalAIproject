# Prompt-pack debugging and QA handoff - 2026-09-08

Repository: A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09

Conversation: f8f7f70e364d40c0
Revision: 72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a
Production target: 204 SDXL stills and 102 MiniMax first/last-frame videos,
4:3 camcorder POV, approved last of clip N as first reference for clip N+1.

Read CLAUDE.md, TODO.md, local_agent/README.md, and HANDOFF_STATUS.md first.
This is bounded debugging/QA, not a claim that the production target is complete.
The directory is not a Git worktree. Preserve existing unrelated changes.
Server APP_REVISION remains 2026-09-07-prompt-pack-full-production-r98;
server.py and managed_prompt_pack.py were inspected but not changed.

## Findings and live evidence

The original restricted startup stall is in built-in node import:
comfy_extras/mesh3d/uv_unwrap/pack.py:44 -> Numba enable_caching ->
ensure_cache_path -> tempfile.NamedTemporaryFile/_mkstemp_inner.
Repeated 45-second stacks are preserved in
work/runtime/startup_diagnostics/20260908_155346/startup.log.
The OpenGL_accelerate message is informational. The mitigation remains
NUMBA_CACHE_DIR under work/runtime/numba_cache; no installed ComfyUI code changed.

Live production-path startup verification, no graph submission:

- First probe: 45-second alive_not_listening timeout earlier in import,
  after 'Using pytorch attention'. Cleanup succeeded and port was released.
  work/runtime/startup_diagnostics/verified_63954fe3bf1c4a41884b34f3bb474505/report.json
- Second probe, 90-second bound with stack capture enabled: /object_info
  returned 905 nodes in 19.3627 seconds. Cleanup succeeded, port released,
  zero submitted graphs. This does not establish repeatable startup reliability.
  work/runtime/startup_diagnostics/verified_88e05ef1791b4c5087a246b868997bef/report.json
- Prior probes' 6.797/9.031-second readiness records checked the port only;
  some reported failed cleanup. Do not reinterpret them as clean current tests.

Physical audit:
local_agent/runtime/managed_tasks/f8f7f70e364d40c0/audits/physical_1e7c8df4eb0843e5ab19a77bfc5803ec.json

There are 139 historical PNGs covering 139 distinct still jobs. 126 pass
mechanical checks. None of the 139 embedded positive prompts exactly matches
the current corresponding job. For C001_start, the embedded positive is 884
characters versus the current 964; the current camera-exclusion clause is absent
from the old render. These are preserved historical candidates, not new attempts.

Ledger-backed counts (physical file and SHA-256 required):

| Media | Generated | QA-passed | Approved | Stills used in video |
| --- | ---: | ---: | ---: | ---: |
| Current accepted-attempt still records | 0 | 0 | 0 | 0 |
| Video records | 0 | 0 | 0 | 0 |

No new still or video was rendered in this pass. Semantic QA is not_run.
There is no verified real video example using approved stills, because no
stills meet the gate. The C001-last -> C002-first path/hash and graph socket
connection are verified only by a bounded synthetic unit test; never call that
a live render verification.

## Exact VLM Identity

The installed files were hashed without loading the model:

- Model: Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf
  SHA-256 e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d
- Projector: Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf
  SHA-256 470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1
- Directory: A:\Users\rhine\ComfyUI-Shared\models\LLM\GGUF\mradermacher\Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF
- Runtime: A:\Users\rhine\ComfyUI-Shared\runtimes\llama.cpp-cuda\llama-server.exe
  version 0.1.2-dev, build 10516, commit b95502ba9, Clang 20.1.8 Windows x86_64
  SHA-256 5a3cbd5613c45ef2d53d3afc6734fd9e67229c0066c2415626ddc7c18901d36c
- Existing lazy media watcher owns VLM lifecycle on 127.0.0.1:11436.
  No substitute model, new runtime, download, model load or router change.

## Changes

- work/image_render.py: attempt IDs, unique prefixes, result receipts with
  resolved output paths/hashes; reject foreign output; preserve stale owner and
  health snapshots; refuse live backend children; recheck port immediately before
  launch; verify owned PID command line before termination; retain failed-cleanup
  evidence; four-thread environment caps and post-render cooling.
- work/run_prompt_pack_production.py: replace stdout parsing and historical file
  scans with receipt validation; version every media/QA/failure attempt; no automatic
  review approval; bind approved physical paths/hashes before each video; stage
  unique input copies and rehash; require live 4:3 option; use owned backend and
  thermal guard; record submitted workflow, prompt ID, references and result.
  Video generation alone ends awaiting_video_qa, never falsely complete.
- local_agent/production_integrity.py (new): receipt contract, immutable copies,
  semantic/explicit approval gates, chained bindings, physical counts, process
  lock, stale-progress diagnosis with last 100 lines, ledger and owner snapshots.
- local_agent/prompt_pack_production.py: preserve ledger history; remove automatic
  approval flag; exact PID checks; serialize worker launches; spawn independent
  watchdog; add record_explicit_approval/load_explicit_approval and
  acknowledge_watchdog; report physical counts. Full-production intent cannot
  approve a still. Approval records are versioned under approvals/<revision>/.
- local_agent/media_accuracy_gate.py: mechanical pass explicitly records pending
  semantic QA and pending approval, with semantic_check: not_run.
- local_agent/test_production_integrity.py (new): bounded negative/positive tests.
- work/audit_prompt_pack_production.py (new): physical PNG metadata/checksum/QA
  audit and exact installed VLM identity report; no historical success import.
- work/verify_prompt_pack_startup.py (new): bounded real owned-path startup probe.
- TODO.md, local_agent/README.md, work/POWERINFER_STATUS_2026-08-30.md,
  this handoff, HANDOFF_STATUS.md, and CHANGELOG/2026-09-08c_prompt_pack_evidence_gates.md.
- Current production ledger: preserved prior snapshot, set auto_approve_video=false,
  semantic_check=not_run, status=paused_for_qa, and linked audit/startup evidence.
  The prior error and dead supervisor PID remain visible as history.

## Verification and Limits

Before edits: python -m unittest local_agent.test_managed_prompt_pack
local_agent.test_media_accuracy_gate -q -> 9 passed.

After edits: python -m unittest local_agent.test_managed_prompt_pack
local_agent.test_media_accuracy_gate local_agent.test_prompt_pack_production
local_agent.test_production_integrity local_agent.test_qwen25_vl_identity -q
-> 37 passed. python -m unittest work.test_image_render -q -> 12 passed.
Total: 49 passing tests. Syntax checks passed after fixing a Windows escaping typo.

The independent watchdog detects stale progress/owned logs after 1200 seconds,
preserves diagnostics, makes failure sticky, and blocks new attempts/retries.
It does not forcibly kill a live uncertain process; an active attempt may still
be finishing its own bounded lifecycle. acknowledge_watchdog requires diagnosis,
dead supervisor/backend ownership and a free port before a later retry.
The watchdog and video binding were tested with fixtures, not a live full pack.

Semantic review integration/execution remains unfinished by explicit fail-closed
choice allowed in the task: not_run is not approved. The next code step is to
connect hash-bound semantic verdicts from the existing exact lazy VLM lifecycle,
then regenerate current-prompt still candidates, review them, and request explicit
operator approval of the concrete still set. Do not ask for approval of unseen
or mechanically checked-only media. Only then verify one real video end to end.

Do not touch outputs/equal_shares/**, PowerInfer weights/predictors/registries,
router settings, or another ComfyUI installation. One backend only. Never kill
unknown processes. Preserve all evidence. Thermal preflight/cooling and the
82 C emergency ceiling remain mandatory. No production worker/backend was left
running by this pass; recheck process identity and port before any later launch.


## Finish-and-prove pass (2026-09-08e)

Closed the remaining evidence-gate packaging gap without starting production:

- media_accuracy_gate.check_still now records pproval_status: unapproved whenever
  semantic_check: not_run (mechanical pass stays pending_semantic QA only).
- 	est_media_accuracy_gate.py converted from free-function asserts to
  unittest.TestCase so the required suite actually executes those checks.
- Required suite: python -m unittest local_agent.test_managed_prompt_pack
  local_agent.test_media_accuracy_gate local_agent.test_prompt_pack_production
  local_agent.test_production_integrity -q → **32 passed** (9+2+5+16).
- Re-ran CPU-safe audit: udits/physical_5b9a98e604794fe8bf11a16b2552811d.json
  — 139 historical PNGs / 139 jobs, 126 mechanical passes, 0 current-prompt matches,
  0 semantic passes, 0 approvals; ledger stills/videos all 0. VLM identity hashes match;
  model not loaded.
- Agent on :8760 left DOWN. No Comfy production/videos. Bounded startup verify skipped
  (remaining optional operator step when :8188 free + thermal OK + full cleanup).

Evidence: CHANGELOG/2026-09-08e_prompt_pack_evidence_finish_prove.md.

## PowerInfer educational draft (2026-09-08d) — review-only

Separate from the prompt-pack QA work above. TurboSparse-Mistral remains parked.

Created/rewrote the four required files under
`review-only/turbosparse-mistral-projected-abliteration/`:

1. `draft-calibration-32-pairs.UNAPPROVED.2026-09-01.jsonl` — 32 pairs; taxonomy 6/6/5/5/5/5; all `operator_approved: false`; all `approval_id: null`
2. `reviewer-worksheet.md` — keep/replace notes are NOT approval
3. `DRAFT-NOT-OPERATOR-APPROVED.md`
4. `validation-report.2026-09-01.txt`

Prior frozen 2026-09-02 draft preserved under `preserved-frozen-2026-09-02/`.
Prior `approved-calibration-32-pairs.2026-09-02.jsonl` untouched.

Validator: `validate_calibration_pairs.py --draft --minimum 32` PASS.
Approved gate rejects null `approval_id` (expected). Focused draft tests 4/4;
approved tests 3/3. No model/GPU inference/ComfyUI/registry/router change.
Local agent on :8760 was not restarted.

NEXT OPERATOR DECISION: review the 32 unapproved pairs and explicitly approve or replace them. This task does not unpark TurboSparse.

## Prompt-pack QA recovery — 2026-09-09

Active production task: `3262c1f626974397` (204 still endpoints, then 102
videos). Production is deliberately stills-only until every current-gate still
passes and the concrete hash-bound set receives explicit approval.

Manual inspection disproved older VLM approvals: empty rooms, wrong people,
cropped bodies, hands-down frames, and hallway compositions had been called
valid. Root cause one was `media_tools._build_prompt()` dropping the expected
prompt when a custom rubric was supplied. Root cause two was confirmation bias
in a single prompt-conditioned VLM pass.

Current gate: `blind-evidence-enforced-v8`. It runs an independent blind
observation, then a separate prompt/reference comparison, and finally enforces
literal evidence in Python for full-body feet, requested hand/wave and smile,
camera/tripod absence, explicit positive room type, C001's sofa/couch, and core
locked outfit. Forbidden alternative room names are not treated as positive
requirements. Older gate
passes are stale by definition. Endpoint i2i uses adaptive denoise after a
prompt-bound rejection. Failures, receipts, hashes, and images are preserved.

Focused production tests pass (30 total for production integrity + prompt-pack
builder; 5 media gate; 3 cleanup). See
`CHANGELOG/2026-09-09w_prompt_bound_blind_evidence_qa.md`.

## C001 retry recovery — 2026-09-09y

The resumed still-only worker produced three fresh C001-start candidates. The
exact Qwen2.5-VL gate rejected each; manual inspection independently confirmed
the first was waist-up and the second cropped legs/shoes. The attempts,
receipts, QA JSON, and failure JSON are preserved under the current revision's
`outputs/media/stills/pack_*_c001_start/` directory. They are not continuity
frames.

The supervisor and only its verified backend children were paused after the
third rejection. `work/run_prompt_pack_production.py` now has a narrowly scoped
`c001-full-body-v1` recovery directive: after three prior C001 attempts it
prepends weighted full-length, both-shoes, floor-visible composition text and
records that fact in the new attempt evidence. It does not modify the source
pack, other clips, or the video gate. CPU tests: 35 passed. Resume stills only;
do not start a video until the established semantic and explicit-approval gates
have passed. See `CHANGELOG/2026-09-09y_c001_composition_recovery.md`.

## QA-contract repair and gate false-positive fixes — 2026-09-09z

Task `f8f7f70e364d40c0`, revision `72a7c2e5...`, still-only phase. Three gate
defects causing false QA failures were diagnosed and fixed:

1. **Negated camera phrase false positive** — `media_accuracy_gate.prompt_assertions()`
   matched `"no visible recording camera"` (a prohibition) as a request. Fixed with
   negative lookbehind `(?<!no )(?<!not )` in both camera-visibility regexes.

2. **VLM jeans terminology mismatch** — `enforce_blind_evidence()` required literal
   `"jean"` in the blind clothing list, but the exact VLM consistently uses `"pants"`.
   Fixed by also accepting `"pant"`, `"denim"`, `"trouser"`.

3. **v5 qa_prompt layered-clothing ambiguity** — The phrase `"olive-green overshirt
   over a faded gray or off-white T-shirt"` caused the VLM to set
   `identity_continuity=false` by confusing which garment each color described.
   The qa_prompt in `apply_composition_recovery()` (recovery_index >= 14) now
   explicitly labels outer and inner garments and removes adjectives not assessable
   from a still ("straight-leg", "worn", "cheap digital").

Both C001 candidates (4c775, 9f229) were reviewed:
- 4c775 delivery: mechanical QA PASS (after fix 1), VLM v5 FAIL, VLM v5b FAIL.
  Root cause for v5b: VLM labels overshirt as "green" not "olive-green" and pants
  as "blue" not "dark blue". Possible genuine color accuracy issue in the render.
  Non-overwriting receipts written. Evidence preserved. Not accepted.
- 9f229 (current ledger entry): `semantic_check: fail` from prior session, not
  re-reviewed this pass.

All 67 ledger stills have `qa_passed()=False`. Tests: 48 passed (0 failed).
Syntax checks passed. Port 8188 free, GPU 29°C.

Production loop resumed: PID 10128, log at
`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/production_2026-09-09z.log`.
C001 start attempt `5d4860c0` confirmed running.

No videos started. No Equal Shares changes. All evidence preserved.
See `CHANGELOG/2026-09-09z_qa_contract_repair_and_gate_fixes.md`.
