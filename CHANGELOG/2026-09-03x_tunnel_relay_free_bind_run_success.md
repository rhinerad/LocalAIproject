# 2026-09-03x - tunnel-relay free-bind /Run SUCCESS (task owns Listen)

All times America/New_York (UTC-4). No reboot. Secrets not printed.

Id from `python scripts/next_changelog_id.py` -> `2026-09-03x`.

## Intent

Rhine-approved free-bind proof: stop the manual `tunnel_relay.py` listener, `/Run` `\local-agent-tunnel-relay`, confirm lasting task-owned Listen + `relaying` line. Explains prior tree-up / no-Listen / LastTaskResult -1 mystery from bind-held runs.

## Baseline (before stop)

- Hub adapter `hub` Up; `10.90.90.1` Preferred.
- Listen `10.90.90.1:6379` OwningProcess **41248**.
- Manual tree SessionId **1**: cmd **36712** -> venv python **37072** -> system Python312 **41248** (CommandLine contains `tunnel_relay.py` / `--bind-ip 10.90.90.1`).
- Established count on that bind: **10**.
- farm_status still up: cmd **15684** / python **22564** / python **37500** (SessionId 1).
- Task `\local-agent-tunnel-relay` Ready; Action = `cmd.exe /c "...\runtime\run_tunnel_relay_task.cmd"`; Start In = repo root; Logon Interactive; Run As rhine. Prior Last Run 15:23:44 Last Result **1** (bind-held 10048 from `2026-09-03w`).

## Stopped (manual only)

- Stopped PIDs with `tunnel_relay.py` in CommandLine: **41248**, **37072**, **36712**.
- Did not kill farm_status / Docker / unrelated python.
- After stop: Listen on `10.90.90.1:6379` empty; no leftover `tunnel_relay.py` processes.

## Logs before /Run

- Truncated `runtime\tunnel_relay_task_run.log` (was 404) and `runtime\tunnel_relay_task_capture.log` (was 2095) to empty.
- Left `runtime\tunnel_relay.log` appending (size 16671).

## /Run

- `schtasks /Run /TN "\local-agent-tunnel-relay"` at **2026-09-03 15:30:21** local; exit 0; Scheduler reported task currently running.

## After ~25s poll

- Task Status: **Running**; Last Run Time: 15:30:21; Last Result: **-2147020576** (task still running / not finished — no END/rc in task_run yet).
- Process tree SessionId **1**:
  - cmd **43960** (PPID 2584) `run_tunnel_relay_task.cmd`
  - venv python **18996** (PPID 43960) `tunnel_relay.py --bind-ip 10.90.90.1`
  - system Python312 **43152** (PPID 18996) same script
- Listen `10.90.90.1:6379` OwningProcess **43152** (task-spawned). Single Listen on that address/port. (`127.0.0.1:6379` Listen PID 37600 is separate local service, not relay.)
- Established count ~9 after restore of traffic.
- farm_status unchanged (15684/22564/37500).

### Log excerpts (redacted)

`tunnel_relay_task_run.log`:
- START 15:30:21.35 session= (empty under task)
- whoami durangamingpc\rhine
- cd_before/cd_after = repo root
- PY_OK / SCRIPT_OK / launching
- No END/rc (process still running — expected for lasting listener)

`tunnel_relay_task_capture.log`:
- `2026-09-03 15:30:22,327 relay relaying 10.90.90.1:6379 -> 127.0.0.1:6379 (max 64 concurrent)`
- Subsequent connection lines from `10.90.90.2` (client reconnect)

No OSError / WinError 10048 on this free-bind run.

## Restored manual?

**No.** Left task-owned listener running (PID **43152**).

## Verdict

**SUCCESS** — task owns Listen on `10.90.90.1:6379`; lasting Running tree SessionId 1; `relaying` line present.

### Mystery explained

Earlier "tree up, no Listen, LastTaskResult -1" / bind-held LastResult **1** were consistent with **port already held** (manual listener) causing bind failure under IgnoreNew / overlapping action, plus prior shared-log capture masking the real OSError. Free bind + separate capture shows healthy bind and lasting Listen under the Logon+Interactive task via `run_tunnel_relay_task.cmd`.

## Unchanged

- Did not change farm-status task.
- Did not switch principal back to S4U/Boot.
