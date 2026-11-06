# 2026-09-24k — test triage; director instructions restored; MiniMax steps decoupled from FLUX

Covers two rounds of work in one session. The first round (test triage) was
done without a CHANGELOG entry; this entry records it too.

Backups: `*.bak_testtriage_20260924T005613` (round 1),
`dspy_orchestrator.py.bak_mmsteps_20260924T013437`,
`test_dspy_orchestrator.py.bak_mmsteps_20260924T013437` (round 2).

## Round 1 — 16 failing non-live tests (13 failures + 3 errors)

Full non-live suite after: **1417 tests OK (2 skipped)**.

Real regressions, fixed in code:

- `START_LOCAL_AGENT_GUI.ps1`: `$ExpectedAgentRevision` was `…-r98`, server
  `APP_REVISION` is `2026-09-22i-gvd-video-pipeline-readiness`. `Test-AgentReady`
  therefore never matched: every launch treated a current server as stale and
  killed it. Updated (CRLF kept).
- `remote_security.py`: `plan_shot_reasoning` (loads a model, writes
  `shot_decisions.jsonl`) was unclassified; added to `GATED_REMOTE_TOOLS`.
- `agent.py`: bare "image/picture/photo" opened the specialist render scope,
  so "Describe this attached image." lost the scope boundary. Now an
  inspection-only turn does not open it; generation turns still do.
- `generalized_video_director.py`: **`Signature.instructions =
  DIRECTOR_SIGNATURE_INSTRUCTIONS` restored.** `_patch_safety3.py`
  (2026-09-16) replaced the signature class with a lookahead for
  `\.instructions=` (no spaces); the file had `.instructions = …`, so the
  match ran to `return` and deleted the line. The student saw only the
  one-line docstring from then on. Mock LM now emits start/video prompts.
- `dspy_orchestrator.py` `_fail_penalty`: matched `"positive_prompt is empty"`;
  the pivot renamed the error, dropping empty-prompt failures 0.02 → 0.01.
  Now matches `"prompt is empty"`.
- `test_production_integrity.py`: `test_kill_pid_posix_sends_sigkill` did not
  force the POSIX branch, so on Windows it ran a real
  `taskkill /PID 4321 /T /F`. It could never have killed anything: Windows PIDs
  are multiples of 4 (all 496 live PIDs checked), 4321 is not. Test now forces
  POSIX and asserts `subprocess.run` is never called.

Stale tests updated: launcher/revision pin, tracing default-DB check (now
asserts the unittest guard, not file absence), denoise expectations (pinned
1.0), pivot field names, `_fail_penalty` scalars, 0.7·min+0.3·mean MIPRO
scalar, retired `build_wan_graph` → `build_minimax_graph` test.

Server restarted: PID 56652 (started 00:50, predated these edits) stopped;
`server.py` relaunched as PID 43244, logs
`local_agent/server_restart_20260924_testtriage.{out,err}.log`, revision
check passes.

## Round 2 — MiniMax steps coupled to FLUX step_count

`_inject_prompt_fields` wrote the FLUX `step_count` into every `steps` input,
including MiniMax `BasicScheduler` node 35. Measured from the workflow embedded
in **144** FLUX+MiniMax MP4s under `ComfyUI-Shared\output`: **143** ran MiniMax
at the FLUX step count (12–40); 3 happened to be 20; 1 kept the template's 15.

The target is **20**, not the template's 15: CLAUDE.md fixes MiniMax H3 at 20
steps, and `backend_profiles.H3_DISTILLED["steps"] == 20`. (The Backrooms batch
passes that profile's 20 as `step_count`, so its renders at 20 were correct by
coincidence; its 28/32-step ones were not.)

- `dspy_orchestrator.py`: new `MINIMAX_H3_STEPS` (from `backend_profiles`,
  fallback 20). `_inject_prompt_fields` skips cfg/steps/denoise for
  `MINIMAX_PHASE_NODES`. `_apply_flux_minimax_node_map` sets node 35 steps from
  `hparams["minimax_step_count"]`, else `MINIMAX_H3_STEPS`.
- Not changed, flagged: `FluxGuidance` node 12 still receives `cfg_scale`
  (guidance == cfg on all 144 renders; template value 3.5). Changing it alters
  the look of stills the operator has already accepted.
- Tests: node 35 == 20 regardless of FLUX step_count; explicit override.
  `test_metric_entrypoint_stores_json_feedback` no longer appends to the real
  `runtime/dspy_opt/gvd_live_metric_history.jsonl` (13 fake `ok.mp4` rows,
  0-based indices 4, 130, 234–244, were added by past test runs; left in place
  as evidence).

## Director-instruction regression: blast radius

- `build_director_program()` is used only by `compile_director` (both
  modules), `run_gvd_live_2row.py` and `_lock_denoise_run.py`. No production
  render path (chat, `render_story_image*`, `execute_*`, Backrooms batch,
  prompt packs) uses the director.
- Affected: **61** live metric renders, 2026-09-16 23:25 → 09-17 14:36, all in
  `ComfyUI-Shared\output\dspy_opt`, from the two MIPRO runs that saved
  `models/dspy_compiled/generalized_video_director_mipro.json` and
  `…_path_b_20260917T004757.json`. Both artifacts contain only the one-line
  docstring as instructions and zero demos (compile uses 0 demos, 1 candidate,
  all proposers disabled). Nothing loads them. Not recompiled — see Open.

## Verification render (real, one clip)

`local_agent/_verify_gvd_render_20260924_v2.py`, GVD-D01. v1
(`_verify_gvd_render_20260924.py`) used `BackroomsWatch`, whose custom-node
whitelist omits KJNodes → HTTP 400 on `PathchSageAttentionKJ`; no render.
v2 used the sanctioned `restart_comfy_rockernow.ps1`, wrapped with
`thermal_guard` pre/post, an 82 °C watchdog, queue owner, and stop-after-render.
Peak 77 °C, no trip; 8188 closed and owner released after.

Output `ComfyUI-Shared\output\dspy_opt\gvd_GVD-D01_086ab1a1b8_00001_.mp4`,
1280×704, 24 fps, 192 frames, 8.0 s. Embedded workflow: KSampler 3 steps 28,
cfg 4.0, denoise 1.0; **BasicScheduler 35 steps 20**; sampler
`res_multistep`; FluxGuidance 4.0.

Visual review (native frames + 2 fps sheet in
`local_agent/runtime/dspy_opt/verify_20260924/frames/`): opening frame matches
the brief (basalt, nesting seabirds, golden hour, no text). **Last ~2 s drift
to green pasture clifftops — location drift, would be rejected.** VLM scored
temporal 0.98 "no random scene change"; that is wrong.

Also found with the restored instructions: the 1.5B student prefixes its
prompts with the instruction labels ("FLUX.1 T2I:", "MiniMax I2V:"), which
reach the CLIP and MiniMax prompts. And `parse_director_hparams` still
expects `denoise`, so every correct prediction logs a "denoise missing;
fallback 0.9" warning (value is clamped to 1.0; the warning is noise).

## Open

- Recompile of the director: not run. Nothing consumes the artifacts, compile
  is ~15 h of GPU at the 09-16/17 rate, and it should wait for the label-echo
  and denoise-warning fixes above. Operator decision.
- `run_gvd_live_2row.py` starts with `HISTORY.write_text("")`, wiping the
  production metric history. Do not run it as-is.
- FluxGuidance coupling (above).
