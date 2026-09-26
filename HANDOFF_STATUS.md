# HANDOFF_STATUS

This file is **generated** and is overwritten on every run (never append).
Do not edit it by hand.

Regenerate from the repository root:

```
python scripts/write_handoff_status.py
```

Generated at: 2026-09-26 01:30:14 Eastern Daylight Time (UTC-04:00) (local)

`TODO.md` is the execution queue. Lettered `CHANGELOG/` entries are evidence. Farm *procedures* live in `docs/FARM_HEALTH_RUNBOOK.md` and `docs/RUNBOOK.md` — this file points to those runbooks and does **not** duplicate their checklists.

**Caveats (not a live probe):** open TODO items are the checkbox line only — wrapped continuation lines in `TODO.md` are omitted. Orphan and persistence sections are seeded from documented CHANGELOG/runbook text, not from live process/service checks.

---

## 1. Recent CHANGELOG (last ~15)

Newest first, so a new agent sees tonight first. Lettered files matching `YYYY-MM-DDx_...` only; same letter-order as `scripts/next_changelog_id.py` (`a` < `b` < … < `z` < `aa`). Same-day duplicate letters both appear, disambiguated by filename. Title is the first markdown `#` heading, else the filename slug.

- 2026-09-26 · `2026-09-26b` · `2026-09-26b_gvd_router_minimax_first_wan_fallback_policy.md` — 2026-09-26b — GVD tool router: MiniMax-first engine policy, Wan only by request or as an announced last resort
- 2026-09-26 · `2026-09-26a` · `2026-09-26a_motion_transfer_video_face_detail_pass.md` — 2026-09-26a — Motion transfer: an Impact Pack video face-detail pass on the AnimateDiff clip; no added flicker (measured), late frames move toward the reference at denoise 0.5; faces stay soft because they are ~60 px at 768×448
- 2026-09-25 · `2026-09-25v` · `2026-09-25v_motion_transfer_identity_face_crop_and_mask.md` — 2026-09-25v — Motion transfer identity, no download: a tight face crop of the character still fixes the 24-frame identity drift; an IP-Adapter attention mask confines colour bleed; adapter strength makes no difference; late-clip softening remains
- 2026-09-25 · `2026-09-25u` · `2026-09-25u_advanced_controlnet_installed_multiwindow_clips_render.md` — 2026-09-25u — ComfyUI-Advanced-ControlNet installed (operator approval); 24-frame, two-window AnimateDiff-SDXL motion-transfer clips now render upright and follow the reference motion; identity drift is the remaining blocker
- 2026-09-25 · `2026-09-25t` · `2026-09-25t_motion_transfer_inversion_root_cause_face_hand_keypoints.md` — 2026-09-25t — Motion transfer: the upside-down AnimateDiff-SDXL output is root-caused (DWPose face + hand keypoints drawn together, which xinsir's union model never saw); with face keypoints off, one 16-frame window renders upright and follows the reference motion
- 2026-09-25 · `2026-09-25s` · `2026-09-25s_motion_transfer_stage1_depth_and_animatediff_single_window_proof.md` — 2026-09-25s — Motion transfer follow-up: depth maps + node schemas proven; real AnimateDiff-SDXL single-window generations ran and came out upside down; seven ablations pin the inversion on the union-promax ControlNet path (unresolved); the AnimateDiff path is one node pack short for multi-window clips
- 2026-09-25 · `2026-09-25q` · `2026-09-25q_queued_analysis_honesty_and_motion_transfer_plan.md` — 2026-09-25q — A queued analysis followed by a silent model now ends in an honest progress report (with a way to fetch the queued result); reference-video motion transfer investigated, routed honestly, planned read-only, stage 1 proven
- 2026-09-25 · `2026-09-25p` · `2026-09-25p_scope_guard_regenerate_status_and_refused_tool_honesty.md` — 2026-09-25p — Stale specialist-scope guard: "regenerate that one" / "status" now continue this chat's own real render work, and a refused specialist tool can no longer be followed by a model narration that it ran
- 2026-09-25 · `2026-09-25o` · `2026-09-25o_gvd_judge_cold_prefill_rebaseline.md` — 2026-09-25o — GVD judge: cold prefill on every call (`cache_prompt: false`); re-baselined, byte-identical to the 25n cold measurements and to the live rows
- 2026-09-25 · `2026-09-25n` · `2026-09-25n_gvd_judge_nondeterminism_is_cache_state.md` — 2026-09-25n — GVD judge non-determinism, measured: a deterministic judge whose answer depends on llama-server's prompt-cache state; the live metric judges cold, the eval runner has judged warm since 24q
- 2026-09-25 · `2026-09-25l` · `2026-09-25l_gvd_judge_measured_turn_not_a_cut.md` — 2026-09-25l — GVD judge: a measured camera turn is not a cut (estimator readings over the sampled-frame gaps, marked in the user prompt)
- 2026-09-25 · `2026-09-25k` · `2026-09-25k_gvd_judge_retry_when_scores_missing.md` — 2026-09-25k — GVD judge: one retry when the answer arrives without the three scores
- 2026-09-25 · `2026-09-25j` · `2026-09-25j_mechanical_gate_before_render.md` — 2026-09-25j — GVD live metric: the mechanical gate runs before the render
- 2026-09-25 · `2026-09-25i` · `2026-09-25i_gvd_live_mipro_validation_pass.md` — 2026-09-25i — first live MIPRO pass with every 24q–25h judge change active (4 rows, 0.80 bar, 0.10 floor)
- 2026-09-25 · `2026-09-25h` · `2026-09-25h_gvd_judge_flicker_not_a_cut.md` — 2026-09-25h — GVD judge: a requested flicker is not a cut (CPU dip rule, dark-frame annotation, prompt rule)

---

## 2. Open TODO.md items

88 open items (`[ ]` or `[~]`; closed `[x]` omitted). Checkbox lines copied verbatim from `TODO.md` (first line of each item only — wrapped continuations omitted):

- [ ] Subject spanning the whole frame vs camera move: needs parallax
- [ ] Whether to relax the Backrooms motion-keyword table: the prompt row
- [ ] Judge misses still open: D02 `614e` (rig read as viewpoint), D02
- [ ] With the current judge every clip's minimum axis is ≤ 0.40 or ≥ 0.80,
- [ ] Do not start videos.
- [ ] Run and review the one bounded C026 recovery. Do not start videos.
- [ ] Next: C026 start Mode B recovery. Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Do not start videos.
- [ ] Operator visually reviews and explicitly accepts or rejects that exact
- [ ] Formal hash-bound approval of the complete 204-still set remains pending;
- [ ] Operator reviews worksheet keep/replace notes (notes are NOT approval) and explicitly approves or replaces pairs.
- [ ] TurboSparse remains parked â€” do not dump/train/convert/bench/register from this draft.
- [ ] Semantic QA is not run. Implement/execute review through the installed exact
- [ ] Regenerate current-prompt candidates through receipts, then obtain explicit
- [ ] Verify a real approved-input video and its embedded graph/hashes only after
- [ ] Optional operator step: bounded verify_prompt_pack_startup.py only if
- [ ] After Rhine restarts: paste/continue Backrooms pack on a fresh chat and confirm outputs under local_agent/runtime/managed_tasks/<cid>/
- [ ] Full 18-clip Flux sheet after operator paste + review gate (VRAM: t5xxl_fp16 + ~12GB UNet on 16GB â€” expect slow / sequential only)
- [ ] After Rhine restarts: regenerate or continue on chat d98731129ac743ac and confirm render/plan no longer stale-blocked
- [ ] After Rhine restarts: hard-refresh GUI and verify Stop returns Send mid-turn
- [ ] WAITING operator sidebar approve **gpu_a38b751666c5** then retry Flux smoke PNG
- [ ] **Task 1 â€” Evaluate PowerInfer architecture (resume, don't restart).
- [ ] **Task 2 â€” Evaluate TinyEngine architecture â€” researched 2026-09-02,
1. [ ] **KV cache quantization** â€” BLOCKED by Phase 1. Update the chosen
3. [ ] **RAG-first memory retrieval** â€” BLOCKED by Phase 1. Enforce Chroma DB
4. [~] **Agentic RAG upgrade for local-docs retrieval** â€” Stages 1-2
- [ ] **Operator goal:** experiment with
- [ ] **2026-09-05, follow-up: KTransformers / PowerInfer MoE feasibility
- [ ] **2026-09-01, operator feedback:** "Claude, Claude Code, GPT are all very
- [ ] Select one first training objective (consented identity *or* style), its
- [ ] With explicit GPU approval, make one bounded SDXL LoRA smoke run and
- [ ] Obtain an explicit operator decision and source selection before staging
- [ ] Add the secondary laptop only after it connects over a private encrypted
- [ ] Conduct a human quality comparison against the current Ollama routes
- [ ] Require a fresh GPU-gateway approval and keep PowerInfer separate from
- [ ] Parked: TurboSparse-Mistral projected abliteration. Canonical weights
- [ ] Bamboo-DPO Q4 runtime intake is complete and byte-verified as a
- [ ] After an accepted model exists, deliberately wire the registered endpoint
- [ ] Run a single benign, battery/thermal-observed Pixel test with
- [ ] Later, separately: abliterate `PowerInfer/SmallThinker-4BA0.6B-Instruct`
- [ ] **10-node asynchronous Worker Farm** â€” planned control-plane/worker-plane
  - [ ] Establish the 1-GbE capacity baseline: inventory every node, measure
  - [ ] Prototype a private RabbitMQ ingress with publisher confirms, manual
  - [ ] Add Celery for durable fetch/extract/encrypt workflows and Ray actors
  - [ ] Build four operator-reviewed workflows: encrypted Judge evaluation;
  - [ ] Encrypt raw artifacts and backups with authenticated AES-256-GCM;
  - [ ] Gate all production work on private-network isolation, source/license
  - [ ] See `docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md` for the
- [ ] **Farm efficiency, ticket 4 â€” Ratchet Loop (autoresearch-style
- [ ] **Farm efficiency tickets 1/4** (full entries: Phase 2 section
- [ ] **Operator-approved phone-call assistant** â€” let the local agent complete
- [ ] **Trusted Android companion: approved phone files and app delivery** â€” evolve
- [ ] **Local 3D generation through ComfyUI** â€” accept a text prompt and optional
- [ ] Add optional exact-Qwen2.5-VL semantic review only when the GPU is explicitly idle; never substitute another VLM.
- [ ] Re-run production with the gate enabled after the current r98 worker naturally finishes or is resumed.
- [ ] Integrate the exact Qwen2.5-VL Caption V4 output into a prompt-grounded
- [ ] After the semantic image/video checker is proven reliable, count consecutive
- [ ] On threshold, capture the prompt, negative prompt, model/profile, seed,
- [ ] Have the local agent diagnose the failure pattern and propose a bounded
- [ ] Apply an adjustment only after deterministic validation and preserve the
- [ ] Add regression tests proving the escalation occurs at 3â€“4 failures and
- [ ] Add a durable task controller that converts a user request into explicit
- [ ] Require each stage to report physical evidence (file path, checksum,
- [ ] Add prompt-pack-specific state: source revision, clip/shot IDs, approved
- [ ] Add a failure classifier that distinguishes bad prompt, bad graph/payload,
- [ ] Add bounded recovery: retry the failed stage with preserved evidence,
- [ ] Add semantic image/video QA that compares the exact VLM caption against
- [ ] Add an operator-visible execution timeline showing what the agent did,
- [ ] Add regression tests for stage resumption, stale context, wrong-project
- [ ] C003_last is paused after two reviewed whole-frame failures. Use targeted
- [ ] **Approve one download, or accept the installed-only path.** No tool in this
- [ ] Never put a real, identifiable person's likeness into sexual content with

---

## 3. Known orphaned / leftover infrastructure

Seeded from tonight's documented CHANGELOG/runbook text only. **Not** live-probed. Do not treat this list as current OS state.

### Crash-looping leftover Mac LaunchAgent `com.local-agent.celery-worker`

- **Machine:** Louises-MBP / 10.90.90.2
- **Source:** `CHANGELOG/2026-09-03e_farm_health_runbook.md; docs/FARM_HEALTH_RUNBOOK.md`
- **Documented status:** Leftover (not the WG root cause): crash-looping LaunchAgent `com.local-agent.celery-worker`. Replaced in place with farm `.env` wrapper, queues `probe,judge,summarize,embed`, `ThrottleInterval` 10.

### Pre-existing Mac LaunchDaemon `com.local-agent.wireguard-wg0`

- **Machine:** Louises-MBP / 10.90.90.2
- **Source:** `CHANGELOG/2026-09-03e_farm_health_runbook.md; docs/FARM_HEALTH_RUNBOOK.md`
- **Documented status:** Loaded, had not been running (last exit 1); `/usr/local/bin/wg-quick` shebang `env bash` hit launchd PATH bash 3.2 vs Homebrew bash 4+. Later kickstarted; restored ~1:19 AM ET to LaunchDaemon/`wireguard-go`. Reboot persistence is not confirmed. Do **not** install a second daemon `com.local-agent.wg-quick`. One label: `com.local-agent.wireguard-wg0`.

### WireGuard.app login item `gui/503/com.wireguard.macos.login-item-helper` / Network Extension `workstation_gateway` owning `utun5`

- **Machine:** Louises-MBP / 10.90.90.2
- **Source:** `CHANGELOG/2026-09-03e_farm_health_runbook.md; docs/FARM_HEALTH_RUNBOOK.md`
- **Documented status:** Login item was on; app + Network Extension owned `utun5` (`workstation_gateway`); handshake never completed. Disabled during datapath restore ~1:19 AM ET (`scutil --nc stop workstation_gateway`; quit WireGuard.app/NE).

### Leftover `tunnel_relay.py` process (PID 37480 documented)

- **Machine:** DuranGamingPC / Windows hub
- **Source:** `CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md`
- **Documented status:** Stopped leftover `python.exe` PID 37480 running `local_agent/worker_farm/relay/tunnel_relay.py --bind-ip 10.90.90.1`. Current listener is the logon task from `2026-09-03s` / `2026-09-04a`, not that leftover PID.

### Boot/S4U task `\local-agent-tunnel-relay` still not registered

- **Machine:** DuranGamingPC / Windows hub
- **Source:** `CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md; CHANGELOG/2026-09-03s_tunnel_relay_logon_interactive_task.md; CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md`
- **Documented status:** Approved S4U At-startup task was **not** registered (03h Access Denied / 0x80070005). Fallback is LogonTrigger + InteractiveToken (`2026-09-03s`). That logon task started at delayed interactive logon 2026-09-04 00:18:03 (`2026-09-04a`); Listen on `10.90.90.1:6379`. Pre-login / Session-0 relay remains the gap. Do not retry `Register-ScheduledTask` without an elevation plan.

### Windows Task `\local-agent-farm-status-daemon`

- **Machine:** DuranGamingPC / Windows hub
- **Source:** `CHANGELOG/2026-09-03f_windows_farm_status_daemon_task.md; CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md; CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md`
- **Documented status:** 03f created the per-user logon task (InteractiveToken, Limited, Hidden, RestartCount 999 / PT1M, ExecutionTimeLimit PT0S). 03h set `StopOnIdleEnd` false. Real delayed logon start verified `2026-09-04a`: Last Run 2026-09-04 00:18:03 with explorer / User Profile Service session 1 (not `Start-ScheduledTask`).

---

## 4. Persistence / supporting services

Most recent documented CHANGELOG/runbook sentence for each service on each machine the docs mention. If a service was not documented: `not documented in recent CHANGELOG/runbook`. **Not** live-probed. Procedures: `docs/FARM_HEALTH_RUNBOOK.md` and `docs/RUNBOOK.md`.

### WireGuard — DuranGamingPC / Windows hub (`WireGuardTunnel$hub` / 10.90.90.1)

- **Source:** `CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md (hub UP also in CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md / CHANGELOG/2026-09-03e_farm_health_runbook.md / docs/FARM_HEALTH_RUNBOOK.md)`
- **Documented status:** `2026-09-04a` post-logon of the 23:35:43.500 boot: adapter `hub` Status Up; `10.90.90.1/28` Preferred; service `WireGuardTunnel$hub` Running / Automatic.

### WireGuard — Louises-MBP / 10.90.90.2 (`utun5` / LaunchDaemon)

- **Source:** `CHANGELOG/2026-09-03i_session_handoff.md; docs/FARM_HEALTH_RUNBOOK.md; CHANGELOG/2026-09-03e_farm_health_runbook.md`
- **Documented status:** Restored ~1:19 AM ET to LaunchDaemon/`wireguard-go` as root; login item disabled. **Reboot persistence is not confirmed.** Do not reboot unless Rhine explicitly says to. Loaded launchd job may still be stale vs the patched plist until `bootout`+`bootstrap` or a planned reboot.

### Celery worker — DuranGamingPC / Windows hub

- **Source:** (none in recent CHANGELOG/runbook)
- **Documented status:** not documented in recent CHANGELOG/runbook

### Celery worker — Louises-MBP / 10.90.90.2 (`celery@Louises-MBP`)

- **Source:** `CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md (03e restore: docs/FARM_HEALTH_RUNBOOK.md / CHANGELOG/2026-09-03e_farm_health_runbook.md)`
- **Documented status:** After delayed logon 00:18:03, workstation `farm_health --json` `status=ok`, `workers_responding=true`, worker `celery@Louises-MBP`, expected tasks registered (`2026-09-04a`).

### tunnel_relay — DuranGamingPC / Windows hub

- **Source:** `CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; CHANGELOG/2026-09-03s_tunnel_relay_logon_interactive_task.md; CHANGELOG/2026-09-03am_tunnel_relay_logon_self_start_verified.md`
- **Documented status:** LogonTrigger / InteractiveToken task `\local-agent-tunnel-relay` started 2026-09-04 00:18:03 on delayed interactive logon; Listen `10.90.90.1:6379` python 15260; Mac `10.90.90.2` Established. Boot/S4U registration still failed (03h); relay is dark until rhine logs on.

### tunnel_relay — Louises-MBP / 10.90.90.2

- **Source:** (none in recent CHANGELOG/runbook)
- **Documented status:** not documented in recent CHANGELOG/runbook

### WSL Docker CE (Ubuntu-24.04) — DuranGamingPC / Windows hub

- **Source:** `CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; CHANGELOG/2026-09-03au_wsl_docker_boot_delayed_login_watchdog_alive.md`
- **Documented status:** BootTrigger S4U task `\local-agent-wsl-docker-boot` (RunAs rhine, PT30S) fired on the 23:35:43.500 boot: Last Run 23:36:27, Docker 29.7.2, `wsl-boot-probe` running, same `SOURCE=boot` instance through delayed logon 00:18:03 (`RESULT=ALIVE`, `2026-09-04a`). Farm Redis is on this engine (`2026-09-03bg` / `bh`).

### Redis/Docker — DuranGamingPC / Windows hub

- **Source:** `CHANGELOG/2026-09-04a_post_reboot_recovery_inspection.md; CHANGELOG/2026-09-03bh_wsl_redis_cutover_reboot_pass.md; CHANGELOG/2026-09-03bg_wsl_redis_phase_c_cutover.md`
- **Documented status:** Phase C persisted the 23:35:43.500 boot (`2026-09-03bh` PASS; post-logon reconfirm `2026-09-04a`): Ubuntu-24.04 Docker CE `local-agent-phase1-redis` (`6ea76294c9cf`) StartedAt 23:36:52 healthy; Windows `127.0.0.1:6379` is wslrelay (not `com.docker.backend`). PING PONG; ACL `default` `mac_worker`. Desktop AutoStart off, HKCU Run Docker Desktop absent, `docker-desktop` distro Stopped.

### Redis/Docker — Louises-MBP / 10.90.90.2

- **Source:** (none in recent CHANGELOG/runbook)
- **Documented status:** not documented in recent CHANGELOG/runbook
