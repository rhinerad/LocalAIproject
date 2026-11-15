# Handoff: finish the 2026-11 audit remediation

Paste everything below the line into the next agent's first message.

---

You are continuing a remediation of the findings in `AUDIT_2026-11-02.md` on
branch `claude/epic-hypatia-6mrayy` of `rhinerad/LocalAIproject`. Read, in
order: `CLAUDE.md` (binding rules, two pages), `README.md`, this file, then
`AUDIT_2026-11-02.md` §2 and §6. Then `git log --oneline -6` and
`git show --stat HEAD` to see what the previous session left.

## Where things stand

Five parallel agents applied fixes on 2026-11-06 and were cut off by a rate
limit before all of them finished and wrote notes. Their work was committed
as-is (commit "WIP: audit code fixes from five parallel agents") after a full
test run showed only three regressions. Repo hygiene, docs consolidation,
dependency manifests, `conftest.py` and CI were completed earlier and are in
the commit before it.

Test baseline on Linux with `requirements-dev.txt` installed (the numbers to
beat; `conftest.py` skips 8 modules that need Windows, `work/` or heavy deps):

```
2074 passed, 96 failed, 33 skipped
```

Of the 96 failures, 93 were failing before any agent edit (missing `dspy`,
`work/image_render.py`, `vendor_sideband/`, Windows paths on Linux, etc.) and
are listed by cause in `AUDIT_2026-11-02.md` §3. The three that are new:

1. `local_agent/test_agent_tracing.py::AgentTracingTests::test_mug_image_join_resolves_audit_line`
   — a real regression. The `comfy_generate` tool span no longer gets its
   `comfy_mcp_audit` span ref. Most likely cause: `comfy_generate` in
   `local_agent/tools.py` now runs the GPU-gate preflight before the MCP call
   and the test's fixture does not grant the gate, so the audit line is never
   written; or the new `logging.exception` path in `tools.call` changed the
   result shape. Make the test grant the gate (or stub `router.gpu_busy` and
   `gpu_gate.request`) if the refusal is correct behaviour; fix the code if
   the audit ref should be recorded even on refusal.
2. `local_agent/test_lxmf_rate_limit.py::TurnRateLimitTests::test_rate_limit_refusal_reply_is_itself_throttled`
   — new test by the farm/bridge agent; the per-identity throttle on the
   "rate limited" refusal reply in `local_agent/lxmf_agent.py` is not yet
   applied (expects 1 refusal per `LIMIT_REFUSAL_INTERVAL_SECONDS`, gets 2).
3. `local_agent/test_remote_security_defaults.py::RemoteDefaultToolTests::test_tool_dispatch_refuses_ungranted_read_file_from_a_phone`
   — new test; `read_file` was removed from `REMOTE_DEFAULT_TOOLS` in
   `local_agent/remote_security.py`, but `tools.call(..., context=phone_ctx)`
   still executes it. Check how `tools.call` consults `context.permits()`
   (around the `_public_args` / `__conversation_id` injection in
   `local_agent/tools.py`) and make an ungranted tool return a
   `"... not permitted"` refusal plus a `"refused"` audit line.

## Per-area status

Notes exist for the pipeline agent only; for the others, derive status from
the diff (`git show HEAD -- <file>`) and the marker list below, which was
produced by grepping for each fix's signature.

### A. `local_agent/tools.py`, `gpu_gate.py`, `file_edit_gate.py`, `action_resolver.py` — mostly done
Present: `_resolve_in_root` containment for writes, deny-list for reads,
`fetch_url` private-range refusal (`ipaddress`), `__operator_text`
re-injection, `_json_strict`/`_UNREADABLE` owner-file reads, gate calls in
the comfy wrappers (10 `gpu_gate.` call sites vs 7 before), `logging.exception`
at the dispatch seam, `gpu_gate` TTL (`APPROVAL_TTL_SECONDS`), cross-process
lock (`msvcrt`/`fcntl`), atomic saves, read-only `snapshot()`,
`file_edit_gate` via `atomic_io`, receipt parsing guarded in
`action_resolver`. New tests `test_tools_containment.py`,
`test_gpu_gate_locking.py` pass.
To verify: every item in AUDIT §2 findings 3, 4, 11, 13 against the diff;
specifically that `comfy_workflow` enqueue/run actions, `comfy_system
clear_vram`, `comfy_process start/restart`, `comfy_models remove/download`
and `comfy_nodes install_custom_node` are all gated and argument-allowlisted,
that the `conversation_id` fallback is gone from `approve_story_stills`,
`ingest_prompt_pack`, `export_prompt_pack_outputs`,
`run_prompt_pack_production`, and that `_stills_review_blocks_video` refuses
on an empty cid. Confirm the module docstring no longer says "Nothing here
deletes anything".

### B. `local_agent/server.py`, `agent.py` — mostly done
Present: `f"localhost:{PORT}"`, `ACTION_ROUTE_ALLOWLIST` on `/api/action`
(`project_state`, `stop_all_comfyui`), 409 on concurrent same-cid turns,
Content-Length/413/dict validation, `Accept-Ranges`/Range media streaming,
`_EVIDENCE_COPY_KEYS` reuse, sha256 escalation key, farm `tool_calls`
discarded, `STREAM_RENDER_CHECK_SECONDS` mid-stream render guard, context
trim with `reserve`, `RuntimeError` instead of `SystemExit`. New tests
`test_server_hardening.py`, `test_agent_farm_trust.py`,
`test_agent_stream_guard.py` pass. `test_http_origin_guard.py` was updated to
post an allowlisted action.
To verify: the `_chat_busy_guard` refcount (grep `_chat_busy_guard` in
`agent.py`; only one match for a counter was found), the `_render_watch_lock`
not being held across subprocess calls, the `isinstance(data, dict)` checks
after `json.loads` at the three sites, and the dead `OPERATING_MEMORY`
read removal.

### C. `local_agent/router.py` + client/retrieval — half done
Done in `router.py`: `maybe_evict_for_render()` called from `status()`,
`_CACHE_TTL` memo for `gpu_memory()`/`_pid_alive()`, `CAP_SWITCH_HYSTERESIS`,
guarded `import thermal_guard`. `local_agent/knowledge/.gitignore` updated.
NOT done (files untouched): `ollama_client.py` (`http.client.HTTPException`
→ `OllamaModelFailure` for mid-stream disconnects; embed `keep_alive` "5m"
instead of "0"), `retrieval.py` (persist per batch, precompute tf/df and
hashes at load, `array('f')` vectors with norms, content-hash index keys,
orphan pruning), `farm_offload.py` (validate embedding vectors: 768 finite
floats keyed by requested ids; validate summaries' shape), `context_compactor.py`
(`num_ctx` 8192 + `num_predict` or smaller `MAX_SOURCE_CHARS`),
`set_media_pressure` atomic write, `_pick` pass-2 skip for the CPU tier. None
of the planned new tests (`test_router_eviction_poll.py`,
`test_retrieval_cache.py`, `test_farm_result_validation.py`) exist yet; add
tests for what is already in `router.py` too. Two `test_router_switching.py`
"coding model" failures and two `test_router_comfy_timeshare.py` failures
pre-date everything; check whether they are Linux artefacts.

### D. Root pipeline — complete
See the pipeline agent's notes reproduced in
`CHANGELOG/2026-11-06a_audit_remediation_part1.md`: shared `gpu_lock.py`
used by `backrooms_watch.py`, `gvd_watcher.py`, `master_batch_runner.py`,
`gpu_watchdog.py`; one `already_done()`; merge-not-replace progress entries;
timestamped VLM dumps; watcher timeout on a silent child; `TimeoutExpired`
handling; watchdog env-driven stall timeout and launch command; fail-closed
`vram_controller`; atomic writes; codemod residue removed; `GVD_ROOT` /
`COMFY_SHARED_INPUT` / `COMFY_SHARED_OUTPUT` env vars; ffmpeg timeouts.
Deliberately not done: renaming root `gvd_qa.py` (it IS loaded by file path
from `local_agent/gvd_qa/i2v_gate.py`, `fresh_review.py` and seven tests, so
the audit's "nothing imports it" was wrong; leave it, or move it together
with those loaders in one change).

### E. Worker farm, edge gateway, LXMF bridge — mostly done
Present: ACL grant rewritten (`-@dangerous`, no `+@all`), `REDISCLI_AUTH`,
`chat_id` `fullmatch` validation, redaction regexes incl. `rediss://`,
atomic judge ledger, dashboard cache `Lock()` and no `format_exc` in
responses, termux outbox quarantine, `Administrators` removed from the
admin-token ACL, `tlsutil` key permissions, LXMF bounded inbox + token bucket
+ attachment/disk quota, `REMOTE_DEFAULT_TOOLS` narrowed, portability
constants in `Lock-Phase1SecretFile.ps1`, `Start-FarmDashboard.ps1`,
`run_farm_dashboard_task.cmd`, `doctor.py`, `celery_app.py`,
`collect.py`. New tests `worker_farm/test_redaction.py`,
`worker_farm/test_semantic_judge_paths.py` pass; two tests in the new files
fail (items 2 and 3 above). The farm agent did not write notes; read the
diffs of the `.ps1`/`.sh`/`compose.yaml` files and confirm the Redis
container still starts with the password supplied via config file or env
rather than argv (AUDIT finding, P2). `worker_farm/test_farm_core.py` and
`test_tunnel_relay.py` failures pre-date the changes (missing `celery`,
Windows `WinError` constants).

## Remaining general work, in order

1. Fix the three regressions above; re-run `python -m pytest` and confirm
   ≥ 2,077 passed with no new failures versus the list in
   `AUDIT_2026-11-02.md` §3.
2. Finish area C (ollama client, retrieval, farm result validation,
   compactor) with tests.
3. Verify areas A, B, E item by item against AUDIT §2 and write
   `CHANGELOG/2026-11-06b_audit_remediation_part2.md` with what was confirmed,
   what was added, and the test evidence. Claim the id with
   `python scripts/next_changelog_id.py`.
4. Lint: `ruff check .` (config in `pyproject.toml`) reports ~110 unused
   imports, 11 `raise ... from`, 4 duplicate dict keys, 2 f-strings, 1
   undefined name (`live_vram_test.py` `CLIP_GGUF`). `ruff check --fix` handles
   the safe ones; fix the rest by hand. CI (`.github/workflows/ci.yml`) runs
   `ruff check .` and `pytest`, so it stays red until this is done.
5. Update `AUDIT_2026-11-02.md`: add a "Status" column or section marking
   each finding fixed / verified / open, and regenerate the changelog index
   (`python scripts/build_changelog_index.py`) and `HANDOFF_STATUS.md`
   (`python scripts/write_handoff_status.py`).
6. Update `docs/CURRENT_HANDOFF.md` to say the remediation is complete and
   remove the pointer to this file.
7. Commit and push to `claude/epic-hypatia-6mrayy`. The previous session's
   `git push` was denied by the environment after one successful push; if
   that happens again, say so instead of retrying endlessly.

## Operator-only items (do not do these yourself; keep them listed)

- History rewrite on GitHub to purge the committed Reticulum identity, chats
  and uploads (they are untracked going forward but remain in old commits).
- On the workstation: back up private dirs, pull with the updated
  `scripts/sync_down.ps1`, run `scripts/untrack_private_data.ps1`, delete
  `local_agent/rns_wifi/storage/transport_identity` so RNS mints a new one,
  re-pair the phone, rotate the Mac worker's Redis password, and commit
  `work/*.py` so the thermal guard and image renderer are in git. Full steps
  are in `docs/CURRENT_HANDOFF.md`.
- Moving the private `distill` Celery queue off the tunnelled Redis instance.
- Running the Windows-only / `work/`-dependent tests on the workstation.

## How to run things here

```bash
pip install -r requirements-dev.txt
python -m pytest                     # full suite, ~90 s
python -m pytest local_agent/test_tools_containment.py   # one file
ruff check .
```

Rules that matter most while you work: never delete evidence or state files;
keep core `local_agent` modules stdlib-only; keep Windows working
(`os.name == "nt"` branches); preserve each file's line endings; every change
gets a changelog entry; do not run renders, nvidia-smi, Docker or RNS.
