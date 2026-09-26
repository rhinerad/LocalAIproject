# 2026-09-04b — docs: farm Redis live path is Ubuntu CE, Docker Desktop is rollback only

Date: 2026-09-04. Docs-only. No code, no compose, no task, no GPU, no service changes.

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-04b**.

Live Redis has been Ubuntu-24.04 Docker CE since `2026-09-03bg`/`bh`, reboot-verified `2026-09-04a`. User-env `FARM_REDIS_ENGINE=wsl` is the effective default on DuranGamingPC. `START_PHASE1_BROKER.ps1` / `doctor.py` still treat unset as `desktop` — that unset-default is not the live path.

## What changed

Operator docs no longer present Docker Desktop / “wait for **Engine running**” as the primary Redis procedure.

| File | Change |
| --- | --- |
| `local_agent/worker_farm/README.md` | Bootstrap: live engine is Ubuntu CE + user-env `wsl`. Desktop **Engine running** wait marked **Desktop rollback path only**. |
| `docs/FARM_HEALTH_RUNBOOK.md` | New “Farm Redis engine (live vs rollback)” section. Mac reboot-unconfirmed vs workstation Redis reboot-verified split. |
| `docs/RUNBOOK.md` | Same split; new “Redis engine (workstation)” recovery: `wsl docker info`, not Desktop. |
| `docs/ARCHITECTURE.md` | Current-state persistence: Redis-at-boot on Ubuntu CE; Desktop rollback only. Limitations bullet no longer says boot task never fired / Redis still on Desktop. |
| `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-26.md` | 2026-08-29 “Engine running” wait marked historical / rollback only. |

Unchanged: launcher/doctor code default when `FARM_REDIS_ENGINE` is unset (`desktop`). Dated CHANGELOG / Phase 1 plan files left as historical.

## Not done

Did not change `START_PHASE1_BROKER.ps1`, `doctor.py`, or `Resolve-FarmRedisEngine.ps1`.
