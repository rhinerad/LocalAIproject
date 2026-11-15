# Local Agent current handoff — 2026-09-03

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This handoff — current general-agent state as of 2026-09-03 (end of day),
   organized by thread rather than by changelog letter.
3. `local_agent/README.md` — product/runtime architecture.
4. `TODO.md` — authoritative execution queue.
5. `docs/ARCHITECTURE.md` and `docs/FARM_HEALTH_RUNBOOK.md` / `docs/RUNBOOK.md`
   — both refreshed today to describe the current persistence state; do not
   trust their 2026-09-02-era wording if you find an un-refreshed copy.
6. `CHANGELOG/README.md` then individual `CHANGELOG/2026-09-03*.md` entries
   (60 entries today, letters `a`–`bh`; two letters collided — see the full
   index at the bottom of this doc).
7. `HANDOFF_STATUS.md` — the generated mechanical snapshot (recent
   changelog, open TODOs, orphan/persistence seeds). Regenerate with
   `python scripts/write_handoff_status.py` if it looks stale; as of this
   writing it was last generated 2026-09-04 10:46:01 ET, already current.

The previous handoff is `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`.
Read it for the full history of changes made on 2026-09-02. This document
supersedes it as the current handoff and carries forward only what is still
current, adding everything done on 2026-09-03.

## Current state

Equal Shares remains a preserved, paused specialist profile. Do not resume its
audio pipeline, launch a Stage-1 render, or alter evidence/manifests. The active
product is the local general-purpose assistant.

Today's work was overwhelmingly **infrastructure persistence and live
verification**, not new features: getting the Mac worker, the Windows relay,
WSL Docker, and farm Redis to all survive an unattended reboot without a
human present, plus finally wiring and live-testing the `agent.py` farm
router that was the single biggest gap in the 2026-09-02 handoff. Two real
bugs were found and fixed during that live verification that 90 passing unit
tests had missed — see Thread 4. The WSL Redis migration (Thread 6) went
further than planned: Phase C (the actual cutover) ran and passed its
delayed-login reboot proof, so farm Redis is no longer on Docker Desktop.

---

## Thread 1 — Mac persistence: LaunchAgent → LaunchDaemon, WireGuard login-item bug fixed

**Problem:** Ollama and Celery ran as per-user LaunchAgents on Louises-MBP.
LaunchAgents only start at GUI login, so neither survives an unattended/
headless boot — an explicit open blocker carried in both of the prior
session-handoff notes (`CHANGELOG/2026-09-03h_session_handoff.md`,
`CHANGELOG/2026-09-03i_session_handoff.md`).

**Fix:** `com.local-agent.celery-worker` and `com.local-agent.ollama`
converted to `/Library/LaunchDaemons/*.plist`, running as
`UserName=rhineduran GroupName=staff` (uid 503, not root) — LaunchDaemons
start at boot regardless of GUI login.
(`CHANGELOG/2026-09-03z_mac_headless_launchdaemons.md`)

**Proof it tracks boot, not login:** cold boot with nobody at the GUI
(`kern.boottime` Thu Sep 3 15:53:17, no autologin user). Both daemons
started **15:53:49** (~32s after boot): Ollama pid 336 (curl `127.0.0.1:11434`
→ 200), Celery pid 339 (children 582/585, ready log line 15:54:18). Rhine's
GUI login came later, ~15:58 — a recheck at 16:00:16 showed **the same
pids/`lstart`** (336/339, still 15:53:49), i.e. login spawned nothing new.
That's the actual proof: if login had produced new pids near 15:58, the
LaunchDaemon conversion would have failed to matter.

**WireGuard login-item bug:** WireGuard.app's GUI login-item helper
(`com.wireguard.macos.login-item-helper`) could silently re-register as an
enabled login item across reboots even after being told to stay off.
`launchctl disable` on the GUI helper labels was the wrong layer —
`print-disabled` showed them disabled, but that isn't a substitute for
unchecking the item in **BTM** (macOS's Background Task Management /
"Login Items & Extensions" list), which is the actual control point that
persists. The fix was unchecking it there, not launchctl.
(`CHANGELOG/2026-09-03r_mac_persistence_reboot.md`)

**Second real reboot, proving the WireGuard fix:** boot `kern.boottime` Thu
Sep 3 14:41:30. Post-reboot: no `WireGuardLoginItemHelper` process, no
`WireGuard.app` process — only the expected LaunchDaemon dataplane
(`wireguard-go utun` root pid 377, `wg-quick up` root pids 354/396 under
`com.local-agent.wireguard-wg0`). `log show` since boot confirmed
`registerLaunchItem` fired only for the legacy daemon, never for the GUI
helper. Tunnel came up automatically (`utun0` = `10.90.90.2`) with nobody
running `wg-quick` by hand; Windows-side ping succeeded throughout. Ollama
and Celery LaunchAgents (this recheck predates their full daemon-ization in
some entries — some inconsistency in ordering across changelog entries, not
worth over-resolving) auto-started; `farm_health` confirmed
`workers_responding=true` at 15:03:22 after one transient false negative at
14:57:41 attributed to an unrelated concurrent DuranGamingPC disconnect.

**Net result:** both the earlier session-handoffs' "Confirm WireGuard
LaunchDaemon-owned utun5 datapath survives reboot (unverified)" and
"Restore Mac Celery workers" blockers are closed as of today.

---

## Thread 2 — Tunnel relay: S4U impossible for a standard user → logon-trigger task; WinError 121 investigated and found benign

**S4U/BootTrigger attempts, all failed:** first attempt to register
`\local-agent-tunnel-relay` as At-startup/S4U/Limited failed outright —
`Register-ScheduledTask` "Access is denied", `-Xml -Force` same, COM
`RegisterTaskDefinition` with `TASK_LOGON_S4U` → `0x80070005`.
(`CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md`)

Rhine was then granted `SeBatchLogonRight` ("Log on as a batch job") via
`secedit`/`LsaAddAccountRights`, confirmed via `LsaEnumerateAccountRights`.
Even with that right, and from an elevated admin session, **every** S4U
registration attempt for principal `rhine` still failed with the same
`0x80070005` — tried via `schtasks /Create /XML /F`, `Register-ScheduledTask
-Xml`, COM `RegisterTask`, principal objects, even a temporary SYSTEM helper
task. Control probes showed an admin account *could* register S4U
Logon/BootTrigger tasks fine, and rhine could self-register **Interactive**
LogonTrigger fine — but rhine could never be registered as an S4U principal
by anyone, admin or self. This isolated the blocker to rhine's account type
(standard, not admin), not a permissions or session issue — the same finding
independently confirmed in Thread 3's WSL boot-task work.
(`CHANGELOG/2026-09-03p_sebatch_rhine_relay_task_register.md` — result:
**partial**, manual listener stayed the live path)

**Pivot to logon-trigger/Interactive**, mirroring the already-working
`\local-agent-farm-status-daemon` shape. Registered without UAC. First
functional test was messy (bind conflict against the still-running manual
listener, then a mystery `LastTaskResult -1` with no Listen appearing).
(`CHANGELOG/2026-09-03s_tunnel_relay_logon_interactive_task.md` — **partial**)

**Diagnosed:** the `-1` mystery was a **log-capture bug**, not a task fault —
the task's log redirect and a still-live manual listener had the same log
file open for append, masking the real error. A separate capture file
surfaced it: `OSError [Errno 10048]`, an ordinary bind conflict because the
manual listener still held the port. Fixed with a proper wrapper script and
separate run/capture logs; principal/triggers unchanged.
(`CHANGELOG/2026-09-03w_tunnel_relay_task_diagnose_capture.md`)

**Free-bind proof:** manual listener stopped, task run — Listen on
`10.90.90.1:6379` came up owned by the task-spawned process, `relaying` in
the capture log, Mac reconnected. **Success**, and it explains the earlier
mystery cleanly: a masked bind-conflict, not a real defect.
(`CHANGELOG/2026-09-03x_tunnel_relay_free_bind_run_success.md`)

**Genuine sign-out/sign-in self-start proof:** a real Type-2 interactive
logon cycle (old session/explorer confirmed gone; new session/explorer both
starting 18:33:10/11) triggered the task automatically at 18:33:11 — one
second after the new logon, and confirmed **not** a leftover from an earlier
manual `/Run` (that process tree was confirmed gone). New process tree owned
the port; 19 Mac connections established; capture log showed `relaying`
with no bind errors. **Clean close** — the logon-trigger design genuinely
self-starts with no manual intervention.
(`CHANGELOG/2026-09-03am_tunnel_relay_logon_self_start_verified.md`)

**Two separate "not proven" delayed-login attempts** — these were about
validating the *different* WSL-boot task (Thread 3), not the relay itself,
but land in the same evidence chain: both attempts failed to prove
unattended (Session-0) behavior because sign-in happened too fast (~14s and
~11s after `LastBootUpTime` respectively) — before the boot task's own
30-second delay had even elapsed, so the interactive logon-watchdog started
WSL first instead of the boot task proving it could run unbothered. Both
explicitly call for a redo with a deliberate wait before authenticating.
(`CHANGELOG/2026-09-03an_delayed_login_reboot_not_proven_logon_too_fast.md`,
`CHANGELOG/2026-09-03ao_delayed_login_reboot_again_logon_11s_not_proven.md`
— superseded later the same day by `03at`/`03au` in Thread 3, which used a
one-shot lock-screen-wait flag to finally engineer a real delayed window)

**WinError 121 saga** — `OSError [WinError 121] semaphore timeout period has
expired` (`ERROR_SEM_TIMEOUT`), from asyncio's Proactor loop finishing a
socket read on an already-torn-down transport. First appeared right after
the sign-out/sign-in proof above, immediately following a Mac reconnect —
worth investigating to rule out a real relay/task fault before calling it
benign.

Root cause, found and independently reverified: a **Mac software-initiated
shutdown/reboot** (`pmset` "SMC shutdown cause: 5") tore down the live TCP
connection without a clean Winsock close; the relay's overlapped recv on
Windows then timed out as WinError 121. The relay process, its Listen
socket, and the scheduled task all stayed up the whole time — nothing on
the Windows/relay side broke. DuranGamingPC-side event logs for the affected
window showed zero relevant events, ruling out a local Wi-Fi/NIC/sleep
cause. Recurrence pattern across the day: correlates with Mac reboots or
Mac low-power sleep with inactive TCP keepalive, but isn't guaranteed —
some Mac reboots and one Celery-only warm restart produced no 121 at all, so
it's not a reliable bug counter, just a benign side-effect of a specific
"peer vanished mid-recv" case.
(`CHANGELOG/2026-09-03as_tunnel_relay_winerror_121_mac_reboot.md`,
`CHANGELOG/2026-09-03av_tunnel_relay_winerror_121_reverify.md`)

**Cosmetic fix applied anyway:** `tunnel_relay.py` gained
`_is_expected_disconnect(exc)` — true for `ConnectionResetError`,
`BrokenPipeError`, and specifically the *Windows* `winerror==121` (not POSIX
errno 121, which is excluded on purpose). Expected disconnects now log at
`INFO` instead of surfacing as an unhandled-exception traceback; other
`OSError`s (e.g. the real WinError 10048 bind conflict from earlier in this
thread) still propagate. 6/6 tests pass, including one confirming POSIX
errno 121 is *not* treated as expected. Source+tests only — the live running
task process still runs the pre-fix code until its next restart.
(`CHANGELOG/2026-09-03ay_tunnel_relay_winerror_121_expected_disconnect.md`)

---

## Thread 3 — WSL Docker-at-boot: the real blocker was standard-user S4U, not permissions; rhine made local admin

**Blocking constraint:** S4U + BootTrigger registration for principal
`rhine` failed consistently with `0x80070005` — from an elevated admin
session, from SYSTEM, from raw XML, from COM — **while rhine was a standard
(non-admin) user**. This exactly confirmed Thread 2's finding: a
standard-user account cannot be registered as an S4U task principal on this
machine, even by an elevated caller or SYSTEM acting on its behalf. Admin
accounts registering *themselves* as S4U already worked fine, isolating the
constraint to the target principal's account type, not the caller's
privilege level.

**Decision:** granted rhine local-Administrators membership
(`Add-LocalGroupMember -Group Administrators -Member DURANGAMINGPC\rhine`,
done by an already-elevated admin account). Explicitly flagged in its own
changelog entry as **"an account privilege change, not a boot-task
footnote"** and standing, not scoped or reverted. Stated rationale: this was
"the approved remaining lever that does not store a password and does not
fall back to a Logon trigger" — the alternatives considered and rejected
were storing a password-based task credential, or degrading to the weaker
Interactive/Logon-trigger pattern (which is what the tunnel relay ended up
using instead, in Thread 2, since it wasn't elevated to admin). No further
risk analysis is recorded beyond that.
(`CHANGELOG/2026-09-03y_rhine_added_to_local_administrators.md`)

**Immediately unblocked:** rhine (now genuinely admin) self-elevated and
successfully registered `\local-agent-wsl-docker-boot`: Ready, RunAs rhine,
LogonType **S4U**, `MSFT_TaskBootTrigger` (At system start up, PT30S delay),
launching WSL Ubuntu-24.04's `keep-alive.sh boot`. Verified via
`Get-ScheduledTask` + `Export-ScheduledTask` + `schtasks /Query /FO LIST /V`,
not just an exit code — but explicitly not yet proven to actually fire at
boot at this point.

**Real cold-reboot proof**, using a one-shot `enforce-lockscreen-wait.flag`
to bounce interactive logon until ≥180s after `LastBootUpTime` (specifically
to distinguish the BootTrigger firing genuinely unattended from the
interactive logon-watchdog racing ahead of it, which is what defeated the
two earlier attempts in Thread 2). `LastBootUpTime` 20:59:02.5; evidence
collected at 21:03:36 (274s elapsed, still pre-login):
`\local-agent-wsl-docker-boot` had run at 20:59:44, heartbeat instance
started 21:00:02 and spanned 199s (20 heartbeats) purely unattended,
`dockerOk=True`.
(`CHANGELOG/2026-09-03at_wsl_docker_boot_delayed_login_pass.md`)

Post-sign-in completion of the **same** boot cycle: real interactive logon
landed at 21:05:16 (+374s after boot). The logon-watchdog task fired and
logged `RESULT=ALIVE` at 21:05:18 — it found the boot-triggered instance
already healthy and did **not** restart it (unlike the earlier failed
attempts, which never got `RESULT=RESTART` to even matter because the
watchdog raced ahead of the boot task). Spot check at 21:21:22 (~22 min
after boot) confirmed the same instance still alive: 121 heartbeats spanning
1262s, Docker `ServerVersion 29.7.2`, `wsl-boot-probe` container up 19
minutes. This is genuine Session-0/unattended proof.
(`CHANGELOG/2026-09-03au_wsl_docker_boot_delayed_login_watchdog_alive.md`)

Both entries note this proof covers only WSL Docker CE keep-alive — farm
Redis / Docker Desktop compose were migrated separately (Thread 6).

---

## Thread 4 — farm-routing caller: `agent.py` now actually calls the farm, and live verification caught two real bugs unit tests missed

This closes the single biggest gap flagged in the 2026-09-02 handoff.

**Design:** `farm_offload.should_route()` reads the daemon-written
`farm_status.json` snapshot rather than calling live `Celery inspect.ping()`
— live inspect takes 1–5s and needs the farm venv, unacceptable to pay on
every hot-path decision. Reachable = snapshot exists, `checked_at` not older
than 90s, `status=="ok"`. Missing/stale/non-ok → run locally immediately,
avoiding a 25–30s helper timeout.

Summarize vs embed are routed differently based on measured Mac latency
(warm ~18.5s / cold ~55s summarize vs. a 12s local timeout budget):
**summarize is prefetch-only** — `should_route("summarize", blocking=True)`
is always `False`; the hop loop only ever consumes an already-ready
prefetch result or falls back local, never blocks waiting on Celery.
**Embed may block** `search_docs` when the farm is reachable, since it's
cheap once warm (~0.58s); falls back to local `_embed()` when the farm is
down. `agent.py` gained `_maybe_start_farm_summary_prefetch`, called from
the hop loop at 80% context. 90/90 tests passed in this pass (unit-level
only, no live Celery job submitted yet).
(`CHANGELOG/2026-09-03aw_farm_routing_caller.md`,
`CHANGELOG/2026-09-03ax_harness_4a_implemented.md` — marks
`HARNESS_OPTIMIZATION.md` §4a implemented, docs-only)

**Live verification, in two passes, found two real bugs:**

First pass found a **prefetch-timeout bug**: the ceiling was 25s (inherited
from 2026-09-02s), but real Mac cold/slow summarize takes ~90–117s — nowhere
near the 18.5s warm-only figure — so every first-of-session prefetch missed
and fell back local. Fixed by raising `PREFETCH_SUMMARIZE_TIMEOUT_S` to 135
(above the worker's own 120s timeout), since prefetch runs in a background
thread and correctness doesn't need a tight ceiling. With the fix, a
consume-win succeeded at 117.3s; `test_farm_offload_live.py` (real Mac
worker) ran 4/4 OK in 121.5s.
(`CHANGELOG/2026-09-03bd_farm_offload_live_verify.md`)

With that fixed, a deeper live-verify run found two more real bugs:

1. **Unbounded farm-embed payload orphaned a queued Celery job.**
   `EmbeddingScorer.vectors_for` was passing *every* stale chunk to the
   farm — on a cold or hash-mismatched cache this could be ~1000 chunks. A
   real failing run: `search_docs` submitted the full corpus, the caller's
   30s timeout expired and returned `None`, but the Celery task **kept
   running** on the Mac worker (`max-concurrency=1`), blocking all later
   summarize/embed work behind it — confirmed via `inspect` showing the
   task still active with hundreds of chunks, unacknowledged; had to be
   manually revoked. The caller then fell back to a 279s local embed — a
   large, silent latency hit. **Fixed:** `FARM_EMBED_MAX_CHUNKS = 8` caps
   what's sent to the farm; the rest stays local. After the fix: farm
   returned 8 vectors in 12.88s (the cap, not the whole corpus).
2. **Failed-prefetch fingerprint-pinning bug silently disabled future
   prefetches for a slice.** When a farm summarize attempt returned `None`
   (e.g. after a client-side timeout), the code stored the `None` result but
   left the fingerprint set, so `maybe_start()` believed that slice had
   already been attempted and never retried it — permanently, for that
   slice, until restart. **Fixed:** the fingerprint is now cleared on
   `None`/exception so the same slice can retry.

Final full live re-run after both fixes: `all_pass=true` in 136.7s across
all 4 scenarios (prefetch farm-up, embed farm-up, failure injection,
reachability timing) — e.g. embed returned exactly 8 vectors in 12.88s;
failure injection with a 180s-stale snapshot correctly made 0 farm calls and
fell back local in 0.99s; `farm_reachable()` timing mean 0.123ms.
(`CHANGELOG/2026-09-03bc_farm_routing_live_verify.md`)

---

## Thread 5 — Security: Windows `.env` ACL lockdown made durable; rhine's admin grant flagged again

**What was locked down:** three live secret-bearing files under
`local_agent/worker_farm/` — `.env` (hub Redis password, broker/result
URLs, AES key), `.env.mac_worker.generated`, and
`runtime/redis-acl/.env.mac_worker.generated`. Before: all three inherited
the parent directory's wide DACL — readable by rhine, a second interactive
admin account, `BUILTIN\Administrators`, a sandbox-users group, ten stale
unresolvable SIDs, and SYSTEM. Described explicitly as "the Windows
equivalent of the Mac world-readable `.env`" (mirroring an earlier Mac-side
fix that tightened that copy to `600`). Fixed with `icacls
/inheritance:r` + `/grant:r` to exactly `NT AUTHORITY\SYSTEM:(R,W)` and
`DURANGAMINGPC\rhine:(R,W)` — `Administrators` deliberately not re-granted
since it still contained the second admin account at the time.
(`CHANGELOG/2026-09-03aj_windows_env_acl_lockdown.md` — one of three `aj`
files today, see the collision note below)

**Made durable:** the first pass only locked files that existed at that
moment; the credential-generation scripts (`Initialize-Phase1Secrets.ps1`,
`Add-Phase1SecondaryWorkerCredential.ps1`) write *new* secret files without
setting any ACL, so a future run would silently re-inherit the wide parent
DACL and undo the lockdown. Fixed with a shared
`Lock-Phase1SecretFile.ps1` helper, wired to run automatically after every
secret write across all three scripts. Directory-level ACL was deliberately
left wide/inherited — the design is per-secret-file locking, not directory
locking, since tightening the directory would break normal legitimate
writers. New `-LockdownProbe` mode added to both scripts for safe
verification (never touches the live `.env`). 4/4 tests pass.
(`CHANGELOG/2026-09-03al_phase1_secret_write_acl_lockdown.md`)

**Standing privilege change, flagged again:** rhine's promotion to local
Administrator (Thread 3) is cross-referenced here deliberately — it changes
who "Administrators:(F)" in an inherited DACL actually means, which is part
of why both ACL passes above deliberately keep the Administrators group off
the locked secret files rather than relying on group membership.

---

## Thread 6 — WSL Redis migration: Phase C ran and passed

Staged plan written as `CHANGELOG/2026-09-03az_wsl_redis_migration_plan.md`
(verdict: Ubuntu-24.04 is a separate Docker CE engine from Docker Desktop,
not a drop-in; the migration is a *move* — copy the volume, stand up the
same compose project on Ubuntu CE, prove `127.0.0.1:6379` still answers,
then disable Desktop AutoStart).

- **Phase A** (spare-port localhost probe) — **PASS**:
  `127.0.0.1:16379` from Windows reached Ubuntu Docker CE.
  (`CHANGELOG/2026-09-03ba_wsl_redis_phase_a_localhost_pass.md`)
- **Phase B** (feature-flagged launchers, default unchanged) — landed:
  `FARM_REDIS_ENGINE=desktop|wsl` wired into `START_PHASE1_BROKER.ps1`,
  `Restore-Phase1SecondaryWorkerCredentials.ps1`, `doctor.py`; default
  stayed `desktop`, live farm untouched throughout.
  (`CHANGELOG/2026-09-03be_farm_redis_engine_flag.md`)
- **Phase C** (the actual cutover) — **ran and passed**, later the same
  night. Steps 1–6 completed: ACL synced, Desktop Redis stopped (not
  `down -v`), volume tarred (32,359,047 bytes) after the stop, Ubuntu
  compose brought up against the pre-seeded volume, verified (healthy,
  PING, ACL `mac_worker` present, AOF loaded, `127.0.0.1:6379` now owned by
  `wslrelay` not `com.docker.backend`, `farm_health` clean), then Desktop
  `AutoStart` set `false` and its HKCU Run entry removed (both backed up).
  Desktop's container and volume were left in place, exited, for rollback —
  not deleted. Rollback was not needed.
  (`CHANGELOG/2026-09-03bg_wsl_redis_phase_c_cutover.md`)
- **Delayed-login reboot proof** — **PASS**: Ubuntu Redis `StartedAt` landed
  after `LastBootUpTime` and before explorer (T+182s), `127.0.0.1:6379`
  still `wslrelay`.
  (`CHANGELOG/2026-09-03bh_wsl_redis_cutover_reboot_pass.md`)

**Net result:** farm Redis is no longer on Docker Desktop. `FARM_REDIS_ENGINE=wsl`
is set at the user-env level on DuranGamingPC, making WSL the effective
default there — though the launchers' own unset-default is still `desktop`
in code (`START_PHASE1_BROKER.ps1`/`doctor.py` weren't patched; this is a
known, accepted gap, not an oversight). Operator-facing docs
(`local_agent/worker_farm/README.md`, `docs/FARM_HEALTH_RUNBOOK.md`,
`docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`) were updated the next morning to
describe Ubuntu CE as the live path and Docker Desktop / "wait for Engine
running" as rollback-only.

**Still open on this thread:** Phase D (cleanup, e.g. optionally quitting
Desktop on login) is gated on "a second successful reboot" per the original
plan — only one cutover boot has been reboot-verified so far (the same boot
covered by `03bh` and the next morning's `2026-09-04a` recovery inspection,
not two separate reboots). Don't treat Phase D as clearable until a genuinely
second clean reboot-and-sign-in cycle confirms the same result.

---

## Brief items (smaller, self-contained changes today)

- **Docs/TODO correction** — fixed two wrong FlashRank model names in
  `TODO.md`/`RAG_EVALUATION.md` (`ms-marco-TinyBERT-L-2-v2` /
  `ms-marco-MiniLM-L-12-v2`, not `-L-6-v2`); rolled up a fully-complete
  Swarm-offload checkbox; audited `CLAUDE.md` for duplicate/contradictory
  content (found none). (`2026-09-03c`)
- **judge_transcript live integration test + outage alerting** — mirrors the
  existing summarize/embed live tests; `farm_status_daemon` now logs
  greppable `FARM_STATUS_OUTAGE`/`FARM_STATUS_RECOVERED` lines after N
  consecutive failed health checks. 29 mocked tests OK, 4 live tests
  skipped (farm was `no_workers` at the time). (`2026-09-03d`)
- **`docs/FARM_HEALTH_RUNBOOK.md` written** — captures a 2:00–2:55 AM
  datapath outage where the VPN "looked Connected" but Redis/SSH/ICMP were
  all dead (interface-up ≠ datapath); reboot persistence flagged
  unconfirmed at the time (later closed by Thread 1). (`2026-09-03e`)
- **First `farm_status_daemon` scheduled-task attempt** — Interactive/logon
  trigger; started via `Start-ScheduledTask` while already logged in, so
  real logon-persistence was still unverified at this point (later proven
  in Threads 1/2's later work). (`2026-09-03f`)
- **`scripts/write_handoff_status.py` written** — generates
  `HANDOFF_STATUS.md` idempotently (recent changelog, open TODOs, seeded
  orphan/persistence state). A proposed `CLAUDE.md` edit in this same entry
  was explicitly *not* applied yet — applied later the same day in `03u`.
  (`2026-09-03j`)
- **TurboSparse F16 agentic diagnostic** — confirms the Q4 agentic-quality
  failure from `2026-09-03b` (see the earlier handoff/this doc's opening)
  isn't quantization-specific: F16 fails the same unconstrained JSON
  tool-call gate with the same `invalid_json` class. Registry write refused,
  parked `20260830b` tree confirmed untouched. (`2026-09-03k`)
- **TurboSparse template/grammar probing follow-up** — found the model's
  baked-in chat template is ChatML, not `[INST]` as previously assumed; only
  grammar-forced probes (exact JSON via GBNF) passed, all unconstrained
  probes still failed. Classified bucket **V1** (grammar-forced capability
  only, not real unconstrained tool-calling). Registry still refused.
  (`2026-09-03t`)
- **`CLAUDE.md` edit applied** (the one proposed but not applied in `03j`),
  plus explicit caveats added to `HANDOFF_STATUS.md`'s generated header
  (checkbox-only TODOs, changelog-seeded not live-probed orphan/persistence
  sections). Verified byte-level encoding integrity. (`2026-09-03u`)
- **Phone reached the farm dashboard** — Pixel 10 on the same LAN
  successfully reached `http://192.168.50.208:8765/` after the Ethernet
  profile Public→Private fix; guest-subnet/AP-isolation already ruled out
  as a cause. (`2026-09-03v`)
- **`\local-agent-handoff-status` scheduled task** — registered in two
  passes same day (`aa` with `LogonType Interactive`, `ab` re-registering
  with the more specific `InteractiveToken`) for hourly weekday runs of
  `write_handoff_status.py`. Near-identical entries — worth noting as
  possibly two agents tightening the same task definition rather than one
  deliberate two-step process, not flagged as a problem, just as a pattern
  to watch for. (`2026-09-03aa`, `2026-09-03ab`)
- **Hop-loop exception guarding extended repo-wide** — every remaining
  unguarded `tools.call` site inside `answer()` (plan execution, URL
  prefetch, project-evidence prefetch, chat-render shortcut, Sonic Pi
  start/stop) now can't escape `answer()` and leave a turn stuck
  `in_progress`. Suite grew 60→65, all passing. (`2026-09-03ad`)
- **FlashRank/Stage 3 stays parked** — research-only decision reaffirmed:
  not a clear win given BEIR numbers, 61% of local chunks exceeding the
  512-token reranker window, and dense Hybrid not even being warm at
  measurement time. No install. (Later informed by real hand-judged data —
  see next item.) (`2026-09-03ae`)
- **`compaction_prefetch` race found and fixed, live-verified for the first
  time** — `maybe_start()`'s ignore-if-busy check wasn't atomic; the lock
  released between fingerprint reservation and publishing the started
  thread, letting a second concurrent call slip through and start a second
  farm job. Reproduced live (6/6 farm calls before fix → 1/6 after). Fixed
  by publishing the thread object inside the same critical section. Tests
  30→33. (`2026-09-03af`)
- **Same-area hardening follow-up** — confirmed holding the lock across
  `Thread()` construction adds no meaningful contention, and found/fixed a
  second gap: a `Thread()`/`.start()` failure could permanently "brick" a
  prefetch slot since the fingerprint/thread reference wasn't rolled back on
  failure. Tests 33→36. (`2026-09-03ah`)
- **Timing-assertion audit** — pure audit, no code change; found only one
  instance of the flaky-wall-clock-assertion bug class across the whole test
  tree (already fixed elsewhere), confirmed other timing-adjacent tests are
  measuring something legitimately different. (`2026-09-03ai`)
- **Farm dashboard degraded-health alert** — `FARM_DASHBOARD_DEGRADED`/
  `FARM_DASHBOARD_RECOVERED` edge-triggered log lines plus a best-effort
  Windows toast when dashboard health isn't `ok` or is stale. 13 tests OK,
  no new dependency. (`2026-09-03ak`)
- **`docs/ARCHITECTURE.md` persistence refresh** — replaced stale
  2026-09-02 descriptions (Ollama as bare `nohup`, relay "not started by any
  launcher," Celery loopback-only) with the day's actual state (LaunchDaemons,
  the Interactive relay task, WSL-boot registered-but-then-still-unproven).
  Explicitly did not claim the WSL-boot task had ever fired yet — that proof
  landed later the same day in Thread 3. (`2026-09-03aj_architecture_doc_persistence_refresh`)
- **18-query hand-judged RAG eval fixture built** — real project questions
  with ground-truth chunk ids, the gap `03ae` said was needed before a
  FlashRank decision. With dense embedding unavailable (Hybrid fail-closed
  to lexical), 13/18 hit top-5; the other 5 were found in the top-50 rerank
  window (ranks 7–19) — suggesting FlashRank could plausibly recover exactly
  those 5, but the decision stayed open pending a run with dense embeddings
  actually warm. That run happened later — see Thread 6's sibling in this
  doc's RAG coverage below. 6/6 fixture-integrity tests passed, no install.
  (`2026-09-03aj_retrieval_hand_judged_eval`)

### RAG Stage 5 — live-dense human comparison finally run

Once dense embeddings were actually warm (not the fail-closed lexical
fallback the earlier eval had been silently measuring), the 18-query
fixture was re-run: live-dense Hybrid vs. lexical `search_docs`. **Mixed
result, marginal net lift**: 13/18 vs 12/18 gold-in-top-5. Hybrid recovered
3 paraphrases lexical had ranked 6–16, but also buried two queries lexical
already answered well: `phase1_stay_on_ollama` (lexical rank 1 → Hybrid rank
9) and `judge_not_registered` (lexical rank 2 → Hybrid rank 12) — both
exact-name/exact-heading lookups where embedding similarity apparently
dilutes what BM25 nails directly. **Decision:** keep `HybridScorer` as the
default (it's safe — fail-closed-equivalent to lexical when embedding is
down) but the eval Ollama instance was stopped afterward, so dense embedding
remains inert in practice on `search_docs` pending a deliberate decision
that addresses the two regressions first. Do not treat a live CPU Ollama at
`:11435` as "Hybrid is on in production" without addressing them.
(`CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md`,
`CHANGELOG/2026-09-03bf_cpu_ollama_11435_stopped_fail_closed.md`)

### Ollama telemetry

`ollama_client.py::chat()` no longer discards `eval_count`,
`prompt_eval_count`, `total_duration`, `eval_duration` — they're copied onto
`ChatResult.telemetry`. Existing `(text, tool_calls)` unpacking unchanged.
3 new tests plus 4 existing chat-unpacking tests, all pass. Nothing consumes
these fields yet — this just stops throwing away data that's already there,
per the `LLMOPS_AUDIT.md` finding from 2026-09-02.
(`CHANGELOG/2026-09-03ap_ollama_chat_telemetry.md`)

---

## Still open going into tomorrow

- **WSL Redis Phase C's actual outcome** — no longer open; it ran and
  passed today (Thread 6). What *is* still open: the second clean reboot
  needed to clear the plan's own Phase D bar, and patching the launchers'
  code-level default (still `desktop` when unset, only correct today because
  of a user-env override).
- **The two Hybrid regressions** (`phase1_stay_on_ollama`,
  `judge_not_registered`) — must be addressed before ever turning dense
  embedding on for real; not yet investigated.
- **Tunnel-relay boot-task Access Denied** — still unresolved; the relay is
  boot-resilient via the logon-trigger fallback only, so the Mac worker
  stays dark until rhine interactively signs in, even though Redis and WSL
  Docker CE now both survive an unattended reboot on their own.
- Everything still-gated from the 2026-09-02 handoff that nothing touched
  today: SDXL LoRA (needs operator-selected objective/dataset + GPU
  approval), DeepSeek-V4-Flash (needs a hardware/tooling decision),
  TinyChatEngine (needs operator confirmation it was the intended target),
  archive export (needs source/destination/key-custody decision), the
  LLM-based judge pass local-vs-callback decision, RAG Stage 5's human
  comparison (now done, see above — this item can be marked closed), and
  Bamboo-DPO (still blocked on an unresolved prompt-template contract).
- **TurboSparse**, for completeness though not one of today's threads: the
  operator-approved 2026-09-02 tree converted/quantized/packaged clean and
  passed its mechanical bench, but failed the agentic JSON tool-call quality
  gate on both Q4 and F16 (`03b`, `03k`), and further probing found only
  grammar-forced JSON works, not real unconstrained tool-calling (`03t`).
  Registry correctly refused to promote it. The parked `20260830b` tree
  remains untouched throughout.

---

## Full CHANGELOG index for 2026-09-03

60 entries, letters `a`–`bh`. Two letters collided; both are confirmed
distinct, unrelated pieces of work, not duplicates:

- **`h`** — `2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md`
  (Task Scheduler changes, first failed S4U relay registration) **and**
  `2026-09-03h_session_handoff.md` (overnight Sep 2–3 consolidation
  narrative).
- **`aj`** — `2026-09-03aj_windows_env_acl_lockdown.md`,
  `2026-09-03aj_architecture_doc_persistence_refresh.md`, and
  `2026-09-03aj_retrieval_hand_judged_eval.md` — three unrelated pieces of
  work, a genuine triple collision.

No collision was found on `r`, `y`, or `z` in this pass — each of those
letters appears exactly once in the directory listing, contrary to an
earlier verbal note; correcting that here rather than repeating an
unconfirmed claim.

`a` main_thread_tool_exception_handling · `b` turbosparse_approved_convert_bench ·
`c` docs_flashrank_todo_arch · `d` farm_judge_live_test_and_status_outage_alert ·
`e` farm_health_runbook · `f` windows_farm_status_daemon_task ·
`g` hop_limit_varying_exception_stress_test ·
`h` farm_status_idle_stop_and_tunnel_relay_task · `h` session_handoff ·
`i` session_handoff · `j` handoff_status_generator ·
`k` turbosparse_f16_agentic_diagnostic · `l` secondary_redis_acl_restore_on_restart ·
`m` secondary_acl_operator_warning · `n` farm_status_dashboard ·
`o` restart_hook_live_verification · `p` sebatch_rhine_relay_task_register ·
`q` ethernet_profile_private_dashboard · `r` mac_persistence_reboot ·
`s` tunnel_relay_logon_interactive_task · `t` turbosparse_template_mismatch_probes ·
`u` claude_handoff_status_line · `v` farm_dashboard_phone_reached ·
`w` tunnel_relay_task_diagnose_capture · `x` tunnel_relay_free_bind_run_success ·
`y` rhine_added_to_local_administrators · `z` mac_headless_launchdaemons ·
`aa` handoff_status_hourly_task · `ab` handoff_status_hourly_task ·
`ac` celery_mainprocess_ollama_import · `ad` unguarded_answer_path_tool_exceptions ·
`ae` flashrank_stage3_close_call · `af` compaction_prefetch_live_verify ·
`ag` parallel_hop_timing_assertion · `ah` compaction_prefetch_lock_error_path ·
`ai` timing_assertion_audit · `aj` retrieval_hand_judged_eval ·
`aj` windows_env_acl_lockdown · `aj` architecture_doc_persistence_refresh ·
`ak` farm_dashboard_degraded_alert · `al` phase1_secret_write_acl_lockdown ·
`am` tunnel_relay_logon_self_start_verified ·
`an` delayed_login_reboot_not_proven_logon_too_fast ·
`ao` delayed_login_reboot_again_logon_11s_not_proven ·
`ap` ollama_chat_telemetry · `as` tunnel_relay_winerror_121_mac_reboot ·
`at` wsl_docker_boot_delayed_login_pass ·
`au` wsl_docker_boot_delayed_login_watchdog_alive ·
`av` tunnel_relay_winerror_121_reverify · `aw` farm_routing_caller ·
`ax` harness_4a_implemented · `ay` tunnel_relay_winerror_121_expected_disconnect ·
`az` wsl_redis_migration_plan · `ba` wsl_redis_phase_a_localhost_pass ·
`bb` retrieval_stage5_human_comparison · `bc` farm_routing_live_verify ·
`bd` farm_offload_live_verify · `be` farm_redis_engine_flag ·
`bf` cpu_ollama_11435_stopped_fail_closed · `bg` wsl_redis_phase_c_cutover ·
`bh` wsl_redis_cutover_reboot_pass
