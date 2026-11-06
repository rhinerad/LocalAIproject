# 2026-09-03as — WinError 121 on tunnel-relay is Mac reboot, not a relay/task fault

All times America/New_York (UTC-4) unless labeled UTC. Read-only root-cause;
no relay restart, no task change, no Mac reboot, no secrets printed.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately
before write: **2026-09-03as**.

## Intent

After `\local-agent-tunnel-relay` logon self-start was proven
(`2026-09-03am`), two `OSError: [WinError 121] The semaphore timeout period
has expired` lines fired at **18:56:03**, then the Mac reconnected on its
own. Check DuranGamingPC + Louises-MBP around that moment: Wi-Fi blip,
sleep/wake, router hiccup, or the relay/task. Do not call it noise without
checking recurrence.

## Verdict

**Mac software shutdown/reboot at 18:55** tore down live TCP to
`10.90.90.1:6379` without a Winsock-friendly close. The still-running
Windows Proactor overlapped-recv timed out as **WinError 121**. The relay
process, Listen socket, and Task Scheduler job stayed up. Celery
LaunchDaemon came back at **18:56:57** and reopened the tunnel.

Not a DuranGamingPC Wi-Fi/NIC/sleep event, not a router log, not a
`\local-agent-tunnel-relay` crash or logon-trigger misfire.

## 18:56 timeline (correlated)

| Time ET | Source | What |
| --- | --- | --- |
| 18:33:11 | `2026-09-03am` / schtasks | Logon trigger started `\local-agent-tunnel-relay` |
| 18:36:51 | `tunnel_relay.log` | `relaying 10.90.90.1:6379 -> 127.0.0.1:6379` |
| 18:37:34 | `tunnel_relay.log` | First Mac connections (`10.90.90.2` 55585+) |
| 18:55 | Mac `last` | `shutdown ~` then `reboot ~` |
| 18:55:13 | farm_status (22:55:13Z) | workers **yes**, broker reachable |
| 18:55:45 | farm_status (22:55:45Z) | workers **no**, broker still reachable |
| 18:56:03.149 / .630 | `tunnel_relay.log` | two WinError 121 in `_pump` / `reader.read` |
| 18:56:36 | pmset (prior boot stamp) | `Sleep/Wakes since boot at 18:56:36` |
| 18:56:53–58 | `tunnel_relay.log` | Mac reconnect burst (`49170`, then `49187+`) |
| 18:56:57 | Mac `worker.stdout.log` | celery@Louises-MBP banner this boot |
| 18:57:26 | farm_status (22:57:26Z) | workers **yes** again (`RECOVERED` after 3) |

`farm_status_daemon.log` timestamps are UTC (`+00:00`). Relay /
Python `logging` timestamps are local ET.

## Ruled out on DuranGamingPC (18:50–19:00)

- **Kernel-Power sleep/wake:** none in the window. (Later Kernel-Power
  events at 18:30 / 19:50 / 20:23 are Windows sign-out/reboot cycles that
  match relay `END rc=1073807364`, not 18:56.)
- **WLAN-AutoConfig / Wired-AutoConfig / NDIS / Tcpip:** no events.
- **Security 4800/4801/4624/4634/4647:** none in 18:50–19:00.
- **Task Scheduler Operational:** 0 events 18:40–19:10. Task stayed
  **Running**, Last Run still 18:33:11 for that cycle.
- Only System hits nearby: DCOM 10016 at 18:54:54 (unrelated COM
  activation) and Windows Update service 7031 at 19:03:46.

Broker stayed reachable through the blip (`farm_status` never said
unreachable). Listen on `10.90.90.1:6379` did not drop.

## Mac evidence

- `last`: `shutdown ~` **18:55**, `reboot ~` **18:55**, console
  16:21–18:55 then new console 19:06.
- `pmset`: `ShutdownCause SMC shutdown cause: 5: Software initiated shutdown`
  at 20:08:49 for the *next* cycle (same class of reboot).
- Celery stdout kept across boots: warm shutdown, then banner
  **2026-09-03 18:56:57** (matches reconnect). Next banner
  **2026-09-03 20:09:43** after the 20:08 reboot.
- WireGuard conf `PersistentKeepalive = 25` (does not prevent a reboot from
  abandoning TCP). Current `kern.boottime` = 20:08:41 ET.

## It recurs — same 121 on every Mac reboot with live sockets

All four 121 clusters in `runtime/tunnel_relay.log` today:

| 121 local | Mac `last` | Reconnect | farm_status |
| --- | --- | --- | --- |
| 03:49:51 / 03:50:00 | *not* a reboot (console 03:04–14:41, 11h36m) | next Mac TCP 13:34:56 after overnight silence | workers drop 07:49Z; 1132-failure outage until 13:35 ET wake |
| 14:41:32 / .33 / .58 | `shutdown`+`reboot` **14:41** (`2026-09-03r` persistence reboot, `kern.boottime` 14:41:30) | 14:46:18 celery ready | workers drop 18:41Z, recover 18:46Z |
| **18:56:03** (this ticket) | `shutdown`+`reboot` **18:55** | 18:56:53 TCP / 18:56:57 celery | 22:55:45Z no → 22:57:26Z yes |
| 20:08:44 / 20:09:07 | `reboot` **20:08** (`kern.boottime` 20:08:41) | 20:09:38 TCP / 20:09:43 celery | 00:08:47Z no → 00:09:50Z yes |

Overnight 03:49 is the other peer-gone case (Mac sleep / Wi-Fi power-save
during a still-logged-in session), same Winsock timeout, much longer
recovery. The 18:56 and 20:08 events are **reboots**, ~1 minute recovery
because LaunchDaemons bring WG + Celery back.

Current relay cycle (task START 20:25:29 after the Windows reboot, Listen
PID 19824, Mac sockets from 20:28:50) has **no** 121 in
`tunnel_relay_task_capture.log` as of 20:48. Mac was already up; sockets
were fresh.

## What 121 actually is here

Stack is always:

`handle` → `_pump` → `StreamReader.read` → `ProactorEventLoop._loop_reading`
→ `ov.getresult()` → `OSError: [WinError 121]`.

Transport already `<_ProactorSocketTransport closed>`. `_pump` only
swallows `ConnectionResetError` and `BrokenPipeError`, so ERROR_SEM_TIMEOUT
logs as `Unhandled exception in client_connected_cb`. That is log noise on
a dead client, not a listen/bind failure (contrast WinError 10048).

Optional later: treat WinError 121 like reset/pipe in `_pump`. Not done in
this pass.

## Not done

No code change. No task XML change. No Mac reboot. Relay left running.
