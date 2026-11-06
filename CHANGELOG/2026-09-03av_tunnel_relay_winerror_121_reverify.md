# 2026-09-03av — WinError 121 re-verify: Mac software reboot, not the relay

All times America/New_York (UTC-4) unless labeled UTC. Read-only root-cause.
No relay restart, no task XML change, no Mac reboot, no secrets printed.

Id from `python scripts/next_changelog_id.py` immediately before write:
**2026-09-03av**. Parallel session already filed `2026-09-03as` with the same
verdict; this pass independently re-read both machines at **21:18–21:22** and
checks recurrence after that write.

## Verdict

The 18:56 WinError 121 is **Louises-MBP software-initiated shutdown/reboot**,
not a DuranGamingPC Wi-Fi/NIC/sleep event, not a router log, and not a
`\local-agent-tunnel-relay` crash or logon-trigger misfire.

Mac `last`: `shutdown ~` **18:55**, `reboot ~` **18:55**. pmset:
`2026-09-03 18:56:07 ShutdownCause SMC shutdown cause: 5: Software initiated
shutdown`, then `Sleep/Wakes since boot at 18:56:36 :0`. Celery LaunchDaemon
banner **18:56:57**. Windows overlapped-recv on already-closed
`_ProactorSocketTransport` timed out as **WinError 121** at **18:56:03**.
The relay process, Listen socket, and Task Scheduler job stayed up. Mac
reopened `10.90.90.1:6379` from **18:56:53**.

## 18:56 timeline

| Time ET | Source | What |
| --- | --- | --- |
| 18:33:11 | schtasks / `2026-09-03am` | Logon trigger started `\local-agent-tunnel-relay` |
| 18:36:51 | `tunnel_relay.log` | `relaying 10.90.90.1:6379 -> 127.0.0.1:6379` |
| 18:37:34 | `tunnel_relay.log` | First Mac TCP (`10.90.90.2` 55585+) |
| 18:55:13 | farm_status `22:55:13Z` | workers **yes**, broker reachable |
| 18:55 | Mac `last` | `shutdown ~` then `reboot ~` |
| 18:55:45 | farm_status `22:55:45Z` | workers **no**; broker **still reachable** |
| 18:56:03.149 / .630 | `tunnel_relay.log` | two `OSError: [WinError 121]` in `_pump` / `reader.read` |
| 18:56:07 | pmset | ShutdownCause **5** (software) |
| 18:56:36 | pmset | new boot stamp (0 sleep/wakes this cycle) |
| 18:56:53–58 | `tunnel_relay.log` | Mac reconnect (`49170`, then `49187+`) |
| 18:56:57 | `~/worker_farm/worker.stdout.log` | celery@Louises-MBP banner |
| 18:57:26 | farm_status `22:57:26Z` | workers **yes** again |

`farm_status_daemon.log` timestamps are UTC. Relay `logging` timestamps are local ET.

## Ruled out on DuranGamingPC (18:40–19:10)

Queried live at 21:18:

- **Kernel-Power sleep/wake:** none in the window. Only Kernel-General 16
  (hive access-history clear) at 18:43:43.
- **WLAN-AutoConfig / Wired-AutoConfig / NDIS / Tcpip:** no events.
- **Security 4800/4801/4624/4634/4647:** none 18:50–19:00.
- **Task Scheduler Operational:** **0** events 18:40–19:10. Task stayed
  Running; that cycle's Last Run was still 18:33:11.
- Only System hit 18:50–19:00: DCOM 10016 at 18:54:54 (unrelated COM
  activation).

Broker never went unreachable through the blip. Listen on `10.90.90.1:6379`
did not drop.

## What 121 is in this relay

Stack is always `handle` → `_pump` → `StreamReader.read` →
`ProactorEventLoop._loop_reading` → `ov.getresult()` →
`OSError: [WinError 121]`. Transport already
`<_ProactorSocketTransport closed>`.

`_pump` only swallows `ConnectionResetError` and `BrokenPipeError`, so
ERROR_SEM_TIMEOUT logs as `Unhandled exception in client_connected_cb`.
That is a dead-client log line, not a listen/bind failure (contrast
WinError 10048). Optional later: treat 121 like reset/pipe. Not done here.

## Recurrence — not noise, but not "every reboot"

All **logged** 121 clusters in `runtime/tunnel_relay.log` today:

| 121 local | Mac evidence | Reconnect | farm_status |
| --- | --- | --- | --- |
| 03:49:51 / 03:50:00 | pmset **Low Power Sleep** 03:49:05, `TCPKeepAlive=inactive`, Batt 32%; wake from Hibernate 13:33:14 | next Mac TCP **13:34:56** | workers drop 07:49Z; outage until afternoon wake |
| 14:41:32 / .33 / .58 | `shutdown`+`reboot` **14:41** (`2026-09-03r`, `kern.boottime` 14:41:30); ShutdownCause 5 at 14:41:39 | 14:46:18 TCP / 14:45:56 celery | 18:41Z no → 18:46Z yes |
| **18:56:03** (this ticket) | `shutdown`+`reboot` **18:55**; ShutdownCause 5 at **18:56:07** | 18:56:53 TCP / 18:56:57 celery | 22:55:45Z no → 22:57:26Z yes |
| 20:08:44 / 20:09:07 | `reboot` **20:08** (`kern.boottime` **20:08:41**); ShutdownCause 5 at 20:08:49 | 20:09:38 TCP / 20:09:43 celery | 00:08:47Z no → 00:09:50Z yes |

Counterexamples (Mac reboot, workers drop, **no** 121 in the relay log):

- **15:43** reboot / celery banner 15:43:52 / workers no 19:43:13Z, yes 19:44:17Z
- **15:53** reboot / celery banner 15:54:08 / workers no 19:53Z

Celery-only restart at **15:26:25** (Warm shutdown, no reboot) produced
`connection closed` then new TCP — also **no** 121. So 121 is the
Winsock-unfriendly peer-gone case (reboot that leaves overlapped recv, or
sleep with TCPKeepAlive off), not a counter on every Mac restart.

Overnight 03:49 is the sleep case: ~10h recovery because the Mac was in
Low Power Sleep / Hibernate. Reboot 121s recover in ~1 minute because
LaunchDaemons bring WG (`utun0` `10.90.90.2`, PersistentKeepalive 25) and
Celery back.

## Current cycle (after 20:08) — has not recurred

Live at 21:18–21:22:

- Mac `kern.boottime` still **20:08:41**; uptime 1h12; `last` shows no reboot
  after 20:08.
- `\local-agent-tunnel-relay` Running, Last Run **21:05:17** (Windows logon
  cycle, Last Result 267009 still-running). Capture START 21:05:20.
- `tunnel_relay_task_capture.log`: `relaying` 21:08:15, Mac sockets 21:08:49
  (`49763`–`49771`). **WinError 121 count = 0**.
- Listen + 9 Established `10.90.90.2` → PID 4204, creation 21:08:49.
- hub adapter Up. ping `10.90.90.2` replies. farm_status workers **yes**
  continuously since 00:09:50Z (latest sample 01:20:11Z).

121 has not fired again on this Mac boot or this relay task cycle. It will
fire again the next time the Mac sleeps with TCPKeepAlive off or reboots
while those sockets are live and Winsock's overlapped recv times out.

## Not done

No code change. No task XML change. No Mac reboot. Relay left running.
