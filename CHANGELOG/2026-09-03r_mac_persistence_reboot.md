# 2026-09-03r — Louises-MBP persistence reboot (WG-off, tunnel-auto, ollama-auto)

Live reboot verification of Louises-MBP on the afternoon of 2026-09-03 ET.
Did **not** sudo. Did **not** `launchctl kickstart` ollama, celery, or WireGuard.
Did **not** launch WireGuard.app. Did **not** run `wg-quick` by hand.

Letter `q` was already taken (`2026-09-03q_ethernet_profile_private_dashboard.md`).
`scripts/next_changelog_id.py` returned `2026-09-03r`.

All times America/New_York (UTC-4) unless labeled.

## Watch / boot

Watch from DuranGamingPC started **14:46:51 ET**. By then the Mac was already
back: `kern.boottime` = **Thu Sep 3 14:41:30 2026**, `uptime` ~12–13 min.
Tunnel `10.90.90.2` and LAN `192.168.50.8` both replied for the whole watch
window (no drop observed after watch start). This is still the new boot —
wall clock and boot time match this afternoon, not a leftover session.

SSH after return: `rhineduran@10.90.90.2`, key `A:\Users\rhine\.ssh\workstation_to_mac`,
`IdentitiesOnly` / `BatchMode` / `StrictHostKeyChecking=yes` / `ConnectTimeout=10`.
uid=503.

## Persistence table

| Check | Verdict | Evidence |
| --- | --- | --- |
| 1. WireGuard.app / LoginItemHelper stay off | **PASS** | See below. BTM uncheck held. |
| 2. Daemon tunnel auto (`10.90.90.2` on utun) | **PASS** | utun0 up without us running wg-quick. |
| 3. Ollama LaunchAgent auto | **PASS** | Already running; curl `Ollama is running`. No kickstart. |
| 4. Celery reconnect (extra) | **PASS** | LaunchAgent up; `farm_health --json` workers_responding + summarize/embed. |

All three required persistence checks held, so this changelog is written.

## 1. WireGuard stays off — BTM uncheck held

`ps aux | grep -i wireguard` / `pgrep -fl wireguard` after the new boot:

- `root` `wireguard-go utun` (pid 377, 2:42 PM) — expected daemon dataplane
- `root` `bash .../wg-quick up /Users/rhineduran/wireguard/wg0.conf` (pids 354, 396, 2:42 PM) — expected `com.local-agent.wireguard-wg0`
- **no** `WireGuardLoginItemHelper`
- **no** `WireGuard.app`

`launchctl print-disabled gui/503 | grep -i wireguard`:

- `"com.wireguard.macos.login-item-helper" => disabled`
- `"com.wireguard.macos" => disabled`

`launchctl print gui/503/com.wireguard.macos.login-item-helper`:
`Could not find service "com.wireguard.macos.login-item-helper" in domain for user gui: 503`
(expected: not loaded).

`/usr/bin/log show` since `2026-09-03 14:41:30` for WireGuard / BTM:

- `registerLaunchItem` for **`com.local-agent.wireguard-wg0`** as a legacy daemon,
  `disposition=[enabled, allowed, visible, notified]` — that is the **daemon**
  tunnel, expected.
- **No** `registerLaunchItem` for `WireGuardLoginItemHelper` / GUI login item
  with `disposition enabled`.
- `--process WireGuardLoginItemHelper` since boot: empty.
- containermanagerd ENOENT for
  `~/Library/Group Containers/com.wireguard.macos.login-item-helper/...metadata.plist`
  (and `com.wireguard.macos`) — scanner noise, not a helper launch / BTM re-enable.

**Wrong layer:** `loginctl`/`launchctl disable` on the GUI helper is not what
keeps WireGuard.app off across reboot. BTM (Login Items checkbox / Background
Items) is the layer that actually held. `print-disabled` still shows the GUI
labels disabled, but that is not a substitute for the BTM uncheck. The helper
did not silently re-register as enabled on this boot.

## 2. Daemon tunnel auto (RunAtLoad)

- `ifconfig`: **utun0** `inet 10.90.90.2 --> 10.90.90.2`
- `launchctl list`: `com.local-agent.wireguard-wg0` pid **354** (same wg-quick
  parent). Started ~14:42 ET, ~1 min after `kern.boottime` 14:41:30. We never
  ran `wg-quick`.
- Windows ping `10.90.90.2` after SSH: replies (e.g. 1 ms; later 88–105 ms
  during a DuranGamingPC agent blip, still 0% loss).
- Mac `nc -z -G 3 10.90.90.1 6379`: succeeded (optional Redis TCP over the tunnel).

## 3. Ollama auto (LaunchAgent, no kickstart)

`launchctl list com.local-agent.ollama` already had **PID 2869**,
`LastExitStatus=0`, `OnDemand=false`, program
`/Users/rhineduran/worker_farm/start_ollama.sh`.
Plist: `~/Library/LaunchAgents/com.local-agent.ollama.plist`.

`curl -sS --max-time 5 http://127.0.0.1:11434/` → `Ollama is running`.

No `launchctl kickstart`.

## 4. Celery (extra)

LaunchAgent `com.local-agent.celery-worker` already running: PID **2868**,
`LastExitStatus=0`, KeepAlive+RunAtLoad, queues
`probe,judge,summarize,embed`. Hostname `Louises-MBP`.
`worker.stdout.log` this boot: banner **2026-09-03 14:45:56**,
`Connected` / `celery@Louises-MBP ready.` at **14:46:18 ET**.
Broker `redis://mac_worker@10.90.90.1:6379/0`. Registered tasks include
`summarize_conversation` and `embed_chunks`.

DuranGamingPC
`local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health --json`
from repo root:

- First call **14:57:41 ET**: `broker_reachable=true` but
  `workers_responding=false`, `status=no_workers`, ~68s ping timeout.
  Coincided with a DuranGamingPC Cursor-agent disconnect; **not** treated as
  a kickstart-worthy Mac failure. Celery log already said ready at 14:46:18.
- Retry **15:03:22 ET**: **ok**, `workers_responding=true`, latency ~5.5s,
  worker `celery@Louises-MBP`, `missing_expected_tasks=[]`,
  `summarize_conversation` and `embed_chunks` registered.

No celery kickstart.

## Files / commands (observe-only)

- Mac LaunchDaemon: `/Library/LaunchDaemons/com.local-agent.wireguard-wg0.plist`
- Mac LaunchAgents: `com.local-agent.ollama.plist`, `com.local-agent.celery-worker.plist`
- This note: `CHANGELOG/2026-09-03r_mac_persistence_reboot.md`
