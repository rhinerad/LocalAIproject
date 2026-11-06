# 2026-09-03aj — Architecture docs: persistence owners as they actually stand

Date: 2026-09-03. Hosts: DuranGamingPC + Louises-MBP. All times America/New_York (UTC-4). Docs only; no Python / plist / task change.

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-03aj**.

`docs/local_agent_architecture.html` does not exist. The GPU/CPU visual is repo-root `local_agent_architecture.html`. The farm current-state architecture (queues, fallback, persistence) is `docs/ARCHITECTURE.md`. Both were stale vs today's LaunchDaemon / Task Scheduler work. Both updated.

## What was stale

`docs/ARCHITECTURE.md` §5 still described the 2026-09-02 picture: Mac Ollama as `nohup`, launchd not configured, relay "not started by any existing launcher," restart relay manually after reboot.

`local_agent_architecture.html` farm box + section 11 still said Celery+Redis was loopback-only, offline/review-only distillation, and "does not touch a live chat turn."

## Live reconfirm (this session, before the edit)

Mac SSH `rhineduran@10.90.90.2`:

- `kern.boottime` Thu Sep 3 **15:53:17**.
- `system/com.local-agent.ollama`: LaunchDaemon, `UserName=rhineduran` / uid **503**, pid **336**, `lstart` 15:53:49, `runs=1`, curl tags HTTP 200. Plist `/Library/LaunchDaemons/com.local-agent.ollama.plist`.
- `system/com.local-agent.celery-worker`: LaunchDaemon, same user/uid, pid **5933** (`lstart` 16:33:54; `runs=2` after afternoon SIGTERM/kickstart — still the system job). Plist `/Library/LaunchDaemons/com.local-agent.celery-worker.plist`.
- gui/503 labels `com.local-agent.ollama` and `com.local-agent.celery-worker` **disabled**. `~/Library/LaunchAgents/com.local-agent.*` gone.
- `id -u rhineduran` = **503**.

Workstation:

- Administrators: `Administrator`, `rhine`, `tiffa`.
- `\local-agent-tunnel-relay`: Running, RunAs `rhine`, LogonType **Interactive**, trigger **MSFT_TaskLogonTrigger**. Listen `10.90.90.1:6379` OwningProcess **43152** (task-spawned `tunnel_relay.py`, SessionId 1). Last Run 15:30:21. Not a manual listener.
- `\local-agent-wsl-docker-boot`: Ready, RunAs `rhine`, LogonType **S4U**, trigger **MSFT_TaskBootTrigger** delay PT30S. **Not proven at boot** (Last Run `11/30/1999`, Last Result 267011).
- Redis `local-agent-phase1-redis` Up, `127.0.0.1:6379`.

## What the docs now say

- Mac Ollama + Celery: system LaunchDaemons, `UserName=rhineduran` / uid 503, not user LaunchAgents.
- Tunnel-relay: registered `\local-agent-tunnel-relay` (logon / Interactive), currently owns Listen. Not a manually-started listener. Not a Boot/S4U job.
- WSL/Docker at boot: registered `\local-agent-wsl-docker-boot` (S4U / BootTrigger under `rhine`, now a local admin). Registered, not boot-proven. Redis/Docker Desktop were not migrated onto it (`2026-09-03y`).
- HTML farm box also drops the false "loopback-only / no live chat" claim: summarize/embed offload is live; distill stays workstation-local.

## Not claimed

Did not reboot. Did not kickstart Mac jobs. Did not `/Run` either Windows task. Did not edit `TODO.md`, `GROK_STATUS.md`, `HANDOFF_STATUS.md`, or `docs/FARM_HEALTH_RUNBOOK.md`. Did not claim `\local-agent-wsl-docker-boot` has ever fired.

## Files

- `docs/ARCHITECTURE.md` (§5 persistence + §6 launchd/relay bullets)
- `local_agent_architecture.html` (farm box, section 11, footer)
- this changelog
