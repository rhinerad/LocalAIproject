# 2026-09-03w - tunnel-relay task diagnose + capture-logging fix

All times America/New_York (UTC-4). No reboot. Did not kill/stop the live Listen holder on 10.90.90.1:6379.

Id from `python scripts/next_changelog_id.py` -> `2026-09-03w`.

## Intent

Diagnose `\local-agent-tunnel-relay` LastTaskResult -1 / 4294967295. Improve task stdout/stderr capture. Keep live listener untouched.

## Facts (ordered checks)

### Paths / cwd / env

- Task WorkingDirectory = repo root; Execute = `cmd.exe`; Arguments were absolute venv python + absolute `tunnel_relay.py` + `--bind-ip 10.90.90.1` + `>> runtime\tunnel_relay.log 2>&1`.
- Interactive Test-Path: venv python, relay script, WorkingDirectory, log path all True.
- `tunnel_relay.py` remains stdlib-only CLI (`argparse`/`asyncio`/`ipaddress`/`logging`/`sys`); `--bind-ip` required; no `.env` / dotenv / relative-path dependence beyond optional cwd (not required for this script).
- Live Listen tree CommandLine matches the old task action shape (same cmd wrapper / venv / script / `--bind-ip` / log redirect). Per `2026-09-03s`, that tree is the **manual restore**, not a Scheduler-tracked Running instance.
- Farm-status uses the same WorkingDirectory + venv python pattern (`-m local_agent.worker_farm.farm_status_daemon`); that module path **does** need repo cwd. Relay does not.

### Session

- Live listener: PID **41248** (system Python312), SessionId **1**; parent venv python **37072**; grandparent cmd **36712** (SessionId **1**). Explorer also SessionId **1**.
- Farm-status tree also SessionId **1** (cmd **15684** / venv **22564** / python312 **37500**).
- Task Principal: UserId `rhine`, LogonType **Interactive**, RunLevel Limited, Hidden true, MultipleInstances **IgnoreNew**, RestartOnFailure 999x/PT1M.
- After `/Run`, marker log `session=%SESSIONNAME%` is empty under the task; interactive wrapper run shows `session=Console`. Not Session 0.

### Bind-held `/Run` (listener kept)

- Before: Listen owner **41248** only.
- After action update + `/Run` at **15:23:44**: LastTaskResult **1**, State Ready; Listen stayed **41248**.
- Marker: PY_OK, SCRIPT_OK, END **rc=1**.
- Capture log: `OSError: [Errno 10048] ... bind on address ('10.90.90.1', 6379)`.
- `type capture >> tunnel_relay.log` did **not** grow `tunnel_relay.log` (size stayed 14922, mtime 15:00:56) while the live listener cmd still holds that file open for append.

### Log-capture bug (confirmed)

- Redirecting a second python into the **same** `tunnel_relay.log` already held open by the live listener's `cmd >> log` produced **no new bytes** and previously reported a false **rc=0** / LastTaskResult **0** (15:21:59 run).
- Redirecting to a **separate** capture file surfaces the real 10048 and exit code 1.
- Prior log search: no historical `10048` lines; only `relaying` at 03:27:16 and 15:00:25 / 15:00:45, plus unrelated WinError 121 on client pumps.

### Durable change

- Added `local_agent/worker_farm/runtime/run_tunnel_relay_task.cmd` (runtime; marker + separate capture).
- Updated `\local-agent-tunnel-relay` Action only (principal/triggers/settings unchanged):
  - Execute: `C:\Windows\System32\cmd.exe`
  - Arguments: `/c "...\runtime\run_tunnel_relay_task.cmd"`
  - WorkingDirectory: repo root
- New always-on files:
  - `runtime\tunnel_relay_task_run.log` (START/END, whoami, paths, rc, SESSIONNAME)
  - `runtime\tunnel_relay_task_capture.log` (python stdout/stderr for the task attempt)

## Still open

- Free-bind end-to-end proof still required (prior `2026-09-03s` free-bind claim: process tree up, no Listen, no new `relaying` line, LastTaskResult -1 after stop). Do **not** free the bind in this pass; Rhine must approve stopping the manual listener first.
- Task Scheduler Operational event query returned no useful filtered hits in this pass.
- Historical LastTaskResult **4294967295** not reproduced under bind-held with new capture (got **1** = python OSError exit).

## Listener after this pass

- Untouched: Listen `10.90.90.1:6379` still PID **41248**, SessionId **1**.