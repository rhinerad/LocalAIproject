# 2026-11-06b — Audit remediation, part 2: the last code fixes, verification, lint

Branch `claude/epic-hypatia-6mrayy`, on top of `fb62127` (part 1 is
`CHANGELOG/2026-11-06a_audit_remediation_part1.md`). Work done 2026-11-07 on
the workstation (Windows 11, Python 3.12) with a WSL Ubuntu 24.04 run for the
Linux comparison. Per-finding status now lives in the "Remediation status"
table at the top of `AUDIT_2026-11-02.md`.

Verification note (CLAUDE.md §3): everything below is code review plus unit
tests. No render was run and no workflow was extracted from an MP4/PNG, so
none of it is render-verified.

## 1. The three regressions left by part 1

All three turned out to be test/behaviour mismatches; no production code had
to change for them.

| Test | Cause | Fix |
|---|---|---|
| `test_agent_tracing.py::test_mug_image_join_resolves_audit_line` | The test patches `router.gpu_busy` to "busy" so the agent takes the CPU route; the new comfy GPU preflight (finding 4) reads the same call and correctly refused before the MCP call, so no audit line or span ref was written. | The test stubs `tools._comfy_gpu_preflight` (and asserts it ran once). Refusal paths stay covered by `test_comfy_tools.ComfyGpuGateTests`. |
| `test_lxmf_rate_limit.py::test_rate_limit_refusal_reply_is_itself_throttled` | The throttle was already applied. The bucket refills one token per 600 s / 10 = 60 s, which is not longer than `LIMIT_REFUSAL_INTERVAL_SECONDS` (60), so after +61 s the next message is a legitimate turn, not a second refusal. | Test drains the refilled token, then expects exactly one new refusal; also asserts the refilled turn ran and the next two did not. |
| `test_remote_security_defaults.py::test_tool_dispatch_refuses_ungranted_read_file_from_a_phone` | `tools.call` already consults `context.permits()` and refuses; it audits an ungranted capability as `"denied"` (the vocabulary `test_lxmf_bridge` pins), not `"refused"`. | Test asserts `outcome == "denied"` and `tool == "read_file"` on the last audit row. |

## 2. Area C (router / client / retrieval / farm / compactor)

Already in `router.py` from part 1, now covered by tests
(`local_agent/test_router_eviction_poll.py`, 23 tests): status-poll eviction
(`maybe_evict_for_render`, cooldown, in-flight, probe interval, chat-busy and
foreign-resident guards, `status()` passing its own snapshot), `_CACHE_TTL`
memo (one spawn per TTL, unknown never cached, per-PID), `CAP_SWITCH_HYSTERESIS`
(hold, switch on the threshold turn, reset on agreement), `thermal_blocks_gpu`
refusing rather than raising when `thermal_guard` is missing,
`set_media_pressure` through `atomic_io`, and `_pick(cpu_tier=True)` skipping
the family fallback.

New code:

- `ollama_client.py`: `http.client.HTTPException` (IncompleteRead,
  RemoteDisconnected, BadStatusLine) → `OllamaModelFailure` in `_post` and
  `chat_stream`, so a mid-stream runner OOM reaches the 14B→8B fallback
  (finding 14). `embed()` `keep_alive` "0" → `EMBED_KEEP_ALIVE = "5m"` (CPU
  only; stops a reload per retrieval batch).
- `retrieval.py`: embedding cache v2 keyed by chunk-text sha1 (legacy
  `{chunk_id: {hash, vector}}` entries migrate on load and are still read if a
  caller passes an unmigrated dict); vectors persisted after every embed batch
  (farm slice and each local batch), so an interrupted first build keeps its
  progress; BM25 tf/df computed once per chunk list (`_lexical_stats`,
  warmed by `load_index`); scoring uses `array('f')` vectors with
  precomputed norms (`_FAST_VECTORS`), public `vectors_for()` still returns
  lists; chunk hashes stored in the index; file index keyed by content sha1
  with mtime:size kept only as a fast path, so a fresh clone does not
  re-chunk or rewrite anything; orphan vectors pruned when the index changes
  (only when the cache sits beside the index file, so a redirected cache is
  never pruned). New helpers `cached_vector`, `store_vector`,
  `prune_embedding_cache`; `eval_retrieval_human.py` uses them.
- `farm_offload.py`: `validate_embed_vectors` (every vector 768 finite
  non-bool numbers, keys a subset of the requested ids, else the whole result
  is discarded) and `validate_summary_result` (`summarized` must be a real
  bool; summaries re-validated and clipped by `context_compactor._valid`;
  extra keys such as `tool_calls` dropped; non-string model dropped);
  `_run_helper` rejects non-object JSON.
- `context_compactor.py`: `MAX_SOURCE_CHARS` 12,000 → 7,000, `NUM_CTX` 4096
  plus `num_predict` 1024 — the old source alone was ~3,500 tokens, leaving
  no room for the JSON reply. Chosen over raising `num_ctx` to 8192 because a
  4-thread CPU prompt eval of ~3.5k tokens cannot finish inside the 12 s
  compaction timeout anyway.
- `test_router_switching.py`: `setUp` stubs `thermal_blocks_gpu` → None.
  The two "coding model" failures on Linux were the thermal guard failing
  closed on a clone with no `work/thermal_guard.py` (correct behaviour, not
  what the test examines). The two `test_router_comfy_timeshare.py` failures
  from AUDIT §3 no longer fail at HEAD on Linux or Windows (fixed by part 1's
  router work); nothing to do.

New tests: `test_router_eviction_poll.py`, `test_retrieval_cache.py` (19),
`test_farm_result_validation.py` (16), `test_ollama_disconnect_and_compactor_budget.py` (8).
`test_farm_offload.py`'s embed fixture now uses 768-d vectors.

## 3. Areas A, B, E verified item by item

Read against AUDIT §2 with `git show HEAD~1 -- <file>` and the current source.

**A — tools.py / gates.** Confirmed: `comfy_workflow` enqueue/run/queue-write
actions, `comfy_system` `clear_vram`/`comfy_cli`, `comfy_process`
start/restart run `_comfy_gpu_preflight`; `comfy_models` remove/download and
`comfy_nodes install_custom_node` need a one-shot `_comfy_approval` and are
audited; every MCP call goes through `_pop_mcp_tool` + `_check_mcp_keys`
(per-tool argument allowlist, no raw passthrough). `approve_story_stills`,
`ingest_prompt_pack`, `export_prompt_pack_outputs`,
`run_prompt_pack_production` read only the server-injected
`__conversation_id` (the model-controlled `conversation_id` fallback is gone)
and refuse when it is empty; `_stills_review_blocks_video("")` refuses. The
module docstring no longer says "Nothing here deletes anything" (pinned by
`test_tools_containment`). `write_file` → `_resolve_in_root` (symlinks
resolved, inside ROOT, never EQ/runtime/work-runtime/protected names), atomic
write. `gpu_gate`: fail-closed `_load`, read-only `snapshot`, msvcrt/fcntl
cross-process lock.

Added while verifying: `file_edit_gate` had only a thread lock, so the GUI
server and the LXMF bridge could still race (second half of finding 11); it
now holds the same cross-process file lock across load+save in `request` and
`decide` (`snapshot` stays lock-free). `comfy_models` compared
`action == "remove"` case-sensitively; it now normalises the action before the
risk checks and sends the normalised value. Tests:
`test_gate_hardening_part2.py` (5, including a real second process holding the
lock); `test_gpu_gate_locking.py` now expects the `.lock` file beside the state.

**B — server.py / agent.py.** Confirmed: `_chat_busy_guard` wraps `answer()`
with a refcount (`_chat_busy_enter`/`_exit`, marker cleared only on 1→0);
`server._active_turns` claim + 409 per conversation; `_render_watch_lock` is
held only for the snapshot and the merge, the tasklist/ComfyUI checks run
outside it under a non-blocking `_render_watch_check_lock`; `isinstance(…,
dict)` checks after `json.loads` added at 5 sites in `agent.py` and 4 in
`server.py`; the dead `OPERATING_MEMORY.read_text()` (overwritten on the next
line) is removed; farm `tool_calls` are recorded and never dispatched
(finding 5); `f"localhost:{PORT}"` (16); sha256 escalation key (17);
`ACTION_ROUTE_ALLOWLIST` + 403 (20); `Range` media streaming (P2).

**E — farm / edge / LXMF.** `compose.yaml` no longer passes
`--requirepass ${REDIS_PASSWORD}`; `redis-with-acl-restore.sh` writes
`requirepass` to a 0600 file (umask 077, chowned to `redis`) and passes it as
redis-server's first argument; `redis-cli` authenticates via `REDISCLI_AUTH`
(healthcheck too), ACL lines go on stdin. Statically confirmed that the
official `redis:7-alpine` entrypoint keeps the config-file-first order when it
appends `--protected-mode no` and drops to the `redis` user, and that the
generated password (URL-safe base64) needs no quoting in a config line. **Not
started live**: Docker Desktop was not running and the image is not pulled;
`REDIS_PASSWORD` is still in the container environment (visible to
`docker inspect`), which the audit accepted. ACL: `-@dangerous -slaveof
-replicaof -module -keys -select …`, `distill` grant refused; key pattern
still `~*` and `distill` still on db 0 (open, operator). `semantic_judge`
validates `chat_id`; edge gateway locks key files (icacls / chmod 0600);
LXMF: token bucket, throttled refusals, 32-message inbox, 1 GiB per-identity
upload quota, one unpaired refusal per hour. `worker_farm/test_farm_core.py`
and `test_tunnel_relay.py` failures pre-date this (missing celery, Windows
`WinError` constants).

## 4. Lint

`ruff check .` (ruff 0.17.4, config in `pyproject.toml`) went from 134 findings
to 0: 106 unused imports removed by `--fix` after a script checked every one
for use as `module.name` elsewhere, `from module import name`, and
`patch("module.name")`. Eight feature-probe imports inside `try:` blocks were
kept with `# noqa: F401`, and one aliased re-export
(`farm_offload.STATUS_STALE_AFTER_S`, read by `test_farm_offload`) was restored
with a noqa. 15 `raise … from` added by hand (`from exc` where the cause is
informative, `from None` for the NVML→nvidia-smi fallback, input validation
and the diagnostics re-raise). 2 f-strings, 2 duplicate imports fixed.
`live_vram_test.py` reported `"clip": CLIP_GGUF`, which is undefined (the
graph uses `CLIP_WAN_FP8`), so the report line now names `CLIP_WAN_FP8`. The
"4 duplicate dict keys" were already gone (part 1 codemod clean-up).

## 5. Docs

`AUDIT_2026-11-02.md`: "Remediation status" table (fixed / verified / open,
with the owner for every open item). `docs/CURRENT_HANDOFF.md`: remediation
marked complete; the pointer to the paste-into-next-agent prompt removed and
that prompt moved to
`archive/handoffs/HANDOFF_PROMPT_2026-11-06_finish_audit_remediation.md`;
operator-only list; the `work/*.py` situation stated plainly (allowed by
`.gitignore`, but none are in git). `CHANGELOG/README.md` and
`HANDOFF_STATUS.md` regenerated.

## 6. Test evidence

Per-test diffs of the `FAILED` lists, not just counts.

| Run | Before (HEAD `fb62127`) | After (this entry) | New failures | Fixed |
|---|---|---|---|---|
| Linux, WSL Ubuntu 24.04, Python 3.12.3, native LF clone, `requirements-dev.txt` | 2071 passed, 95 failed, 37 skipped | **2147 passed, 90 failed, 37 skipped** | **0** | 5 (the three part-1 regressions + the two coding-model tests) |
| Windows 11, Python 3.12.10, workstation checkout | 2077 passed, 118 failed, 28 skipped | **2154 passed, 112 failed, 28 skipped** | **0** | 6 |
| `ruff check .` | 134 findings | **0** | | |

The handoff's Linux baseline was 2074 / 96 / 33; the HEAD rerun here gave
2071 / 95 / 37 (different machine; same failing causes). The target of
≥ 2,077 passed with no new failures is met on both platforms.

Notes on the runs:
- The Windows "before" run overlapped with the first edits, so it is a
  slightly mixed snapshot; the diff still shows no test that passed before
  and fails now.
- Windows-only extra failures are environmental: `work/*.py` absent, the
  workstation's `EQUAL_SHARES_PRIMARY_REASONING_MODEL` override (11
  `test_router_switching` tests; all pass with it unset), Windows path tests.
- A first Linux run against the CRLF Windows checkout over `/mnt/a` showed
  three apparent new failures: two were artefacts (`test_motion_transfer_graph`
  pins template sha256 over LF bytes; `test_gvd_qa_local`) and pass on the
  native clone. The third, `test_media_gpu_queue::test_interactive_priority_is_fifo_and_precedes_batch`,
  was a real pre-existing flake (failed 4 of 5 runs on HEAD+patch): `media_queue.claim_next`
  ordered FIFO by file mtime, and jobs enqueued in the same coarse kernel
  clock tick tied and were ordered by their random id. Fixed: `enqueue`
  records a strictly increasing `queued_seq` (time_ns + per-process
  counter) and `claim_next` sorts on it, falling back to mtime for older
  jobs. 6 of 6 runs pass after the fix.

## 7. Operator-only (listed, not done)

1. History rewrite on GitHub to purge the committed Reticulum identity, chats
   and uploads (untracked going forward, still in old commits).
2. On the workstation: back up `local_agent/chats`, `uploads`, `render_jobs`,
   `logs`, `rns_wifi/storage`; pull with the updated `scripts/sync_down.ps1`;
   run `scripts/untrack_private_data.ps1`; delete
   `local_agent/rns_wifi/storage/transport_identity` so RNS mints a new
   identity; re-pair the phone; rotate the Mac worker's Redis password.
3. Commit `work/*.py` (thermal guard, image renderer, scene reasoner) from the
   workstation; `git ls-files work` is empty on this branch.
4. Move the private `distill` queue off the tunnelled Redis instance.
5. Decide whether `.claude/settings.local.json` and `.claude/launch.json` stay
   tracked.

Undecidable here, safest option taken: none of the above was attempted.
