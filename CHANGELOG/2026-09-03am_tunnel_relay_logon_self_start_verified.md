# 2026-09-03am — logon-trigger self-start verified after Sign out/in

All times America/New_York (UTC-4). Read-only verify; no `schtasks /Run`, no Start-ScheduledTask, no python start, no listener restore, no farm_status kill, no reboot. Secrets not printed.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03am**.

## Intent

Confirm `\local-agent-tunnel-relay` (LogonTrigger + InteractiveToken, same shape as `\local-agent-farm-status-daemon`) self-started after a real Sign out/in, owns Listen on `10.90.90.1:6379`, and that Mac `10.90.90.2` reconnected. Prior live path was a 15:30:21 `/Run` leftover (cmd 43960 → venv 18996 → python 43152).

## Type-2 cycle (leftovers gone)

| Leftover (must be gone) | Observed |
| --- | --- |
| Type-2 LogonId **338904** start 2026-09-01 20:30:59 | **GONE**. Live Type-2: **324566** and **322889**, both start **2026-09-03 18:33:10**, CloudAP |
| explorer **7720** start 2026-09-01 20:31:01 | **GONE**. Live explorer **7756** start **2026-09-03 18:33:11** (PPID 7704) |
| cmd **43960** / venv **18996** / python **43152** start 15:30:21 | **GONE** |

Claimed sign-out ~18:29. Prior `tunnel_relay.log` session ended `END rc=1073807364 Thu 09/03/2026 18:30:25.30` (session-close). New interactive logon **18:33:10**.

## Trigger fired (not a /Run)

| Field | Value |
| --- | --- |
| Task | `\local-agent-tunnel-relay` |
| Schedule Type | At logon time / Interactive only / Run As rhine |
| Status | **Running** |
| Last Run Time | **2026-09-03 18:33:11** (1s after new logon; not 15:30:21) |
| Last Result | **267009** (`0x41301` still running) |
| This session `/Run` | **none** |

`local_agent/worker_farm/runtime/tunnel_relay_task_run.log` (overwritten; only this START):

```text
START Thu 09/03/2026 18:33:15.90 session=
durangamingpc\rhine
cd_before=<repo root>
cd_after=<repo root>
PY_OK
SCRIPT_OK
launching
```

## Task owns Listen

Tree (all start 18:33:11–18:33:21):

- svchost **2720** (18:33:09)
- cmd **7008** (18:33:11) `C:\Windows\System32\cmd.exe /c "...\local_agent\worker_farm\runtime\run_tunnel_relay_task.cmd"`
- venv python **18892** (18:33:21) `local_agent/worker_farm/.venv/Scripts/python.exe -u .../relay/tunnel_relay.py --bind-ip 10.90.90.1`
- system Python312 **18912** (18:33:21) same script (Listen owner)

Listen `10.90.90.1:6379` OwningProcess **18912**. Not 43152.

## Mac reconnects

Established `10.90.90.1:6379` ↔ `10.90.90.2:*`: **19**, all OwningProcess **18912**.

`local_agent/worker_farm/runtime/tunnel_relay_task_capture.log`:

```text
---- task capture Thu 09/03/2026 18:33:19.25 ----
2026-09-03 18:36:51,914 relay relaying 10.90.90.1:6379 -> 127.0.0.1:6379 (max 64 concurrent)
2026-09-03 18:37:34,681 relay connection from ('10.90.90.2', 55585)
```

~3.5 min from python start (18:33:21) to first `relaying` (18:36:51). Hub adapter was Up at verify.

## Logs

- START + PY_OK + SCRIPT_OK + launching in `local_agent/worker_farm/runtime/tunnel_relay_task_run.log`
- `relaying` in `local_agent/worker_farm/runtime/tunnel_relay_task_capture.log`
- **No WinError 10048** in task_run / task_capture / `local_agent/worker_farm/runtime/tunnel_relay.log`
- **WinError 121** present in this cycle's capture at **18:56:03** (two `OSError: [WinError 121] The semaphore timeout period has expired`); Mac reconnected from **18:56:53** (`10.90.90.2` 49187+)

`local_agent/worker_farm/runtime/tunnel_relay.log` is a historical append (prior `relaying` 03:27 / 15:00 / 18:29; last END 18:30:25). Current cycle writes task_run + task_capture.

## Hub / farm_status / Docker (noted, not changed)

- Adapter `hub` **Up**; `10.90.90.1/28` on `hub`; ping 10.90.90.1 <1ms
- `\local-agent-farm-status-daemon` Running; Last Run Time **2026-09-03 18:33:11** (was 03:11:54). Tree: cmd **7112** (18:33:11) → venv **12364** (18:33:14) → python **2716** (18:33:17). Old 22564/37500 gone; 15684 is now a different process (PID reuse)
- Docker `127.0.0.1:6379` Listen OwningProcess **4548** `com.docker.backend.exe` (18:33:41) — untouched

## Accepted limitation

No pre-login / S4U / At-startup boot (same as farm-status). Relay starts at interactive logon for rhine, not before the desktop session exists.

## Verdict

**CLEAN CLOSE** — real Type-2 cycle; logon trigger self-start; task owns Listen; Mac reconnects; logs have START/PY_OK/relaying and no 10048.
