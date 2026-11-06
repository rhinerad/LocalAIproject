# Farm health runbook

Date: 2026-09-03. Diagnostic sequence from 2026-09-02 evening through ~2:55 AM ET.
Mac WireGuard/Celery **reboot persistence is not confirmed.** Workstation farm
Redis on Ubuntu-24.04 Docker CE **is** reboot-verified (`2026-09-03bh` /
`2026-09-04a`).

## Farm Redis engine (live vs rollback)

**Live on DuranGamingPC** (cut over `2026-09-03bg`, delayed-login proof
`2026-09-03bh`, post-logon reconfirm `2026-09-04a`): Ubuntu-24.04 Docker CE
container `local-agent-phase1-redis`, started at boot by
`\local-agent-wsl-docker-boot`. Windows `127.0.0.1:6379` is `wslrelay`.
User-env `FARM_REDIS_ENGINE=wsl` is the effective default on this machine.

`START_PHASE1_BROKER.ps1` / `doctor.py` still treat **unset** as `desktop`.
That unset-default is **Desktop rollback only, not the live default.** Do
**not** wait for Docker Desktop **Engine running** unless you are
deliberately rolling back. Desktop AutoStart and HKCU Run Docker Desktop
are off.

Mac workers still reach the broker at `10.90.90.1:6379` via tunnel-relay
(logon), not Windows loopback. `farm_health` TCP to `FARM_BROKER_URL` is
that hub address.

## Trap

Interface-up ≠ datapath. Windows hub and Mac `utun5` / `10.90.90.2` can both look Connected while Redis / SSH / ICMP over `10.90.90.0/28` are dead.

The farm **dashboard** default URL is `http://127.0.0.1:8765/` (loopback). It is not on `192.168.50.x` unless `FARM_DASHBOARD_HOST` is set. See `local_agent/worker_farm/README.md`.

Hot path: `farm_offload.farm_reachable()` reads `farm_status.json` with the same overall-healthy rule as the dashboard (`status=="ok"`, not older than 90s). Live `farm_health` CLI is still a diagnostic — the agent does not call Celery `inspect` on a turn. A stale or non-ok snapshot means run locally, no 25–30s wait.

## Redis secondary ACL after restart

Do **not** re-run `Add-Phase1SecondaryWorkerCredential.ps1` after a Redis container bounce. That script mints a new password every time and will break the Mac's stored `mac_worker` credential. Keep `local_agent/worker_farm/.env.mac_worker.generated` on the workstation.

`local-agent-phase1-redis` already restores secondary ACL users on every start (including `docker restart`) via `redis-with-acl-restore.sh`. Manual restore without rotation: `Restore-Phase1SecondaryWorkerCredentials.ps1`. Default `requirepass` is unchanged. Evidence: `CHANGELOG/2026-09-03l_secondary_redis_acl_restore_on_restart.md`.

## 1. Health check (workstation, farm venv, repo root)

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health --json
```

TCP to `FARM_BROKER_URL` host:port (hub `10.90.90.1:6379`, not `127.0.0.1`), then Celery `inspect.ping()`. Does not submit summarize/embed jobs. Status is connectivity-only: `ok` / `no_workers` / `unreachable` / `unconfigured`. Exit 0 only when `ok`.

Tonight ~6:42–6:48 PM when it looked unhealthy:

```
broker reachable: yes  workers responding: no  latency_ms: 1479.6  error: broker reachable, no worker answered ping
registered-task status: no_workers  workers: (none)  registered: (none)  missing_expected: ...connectivity_probe, ...judge_transcript, ...summarize_conversation, ...embed_chunks
```

Windows hub was up. Cached `farm_status.json` last healthy 4:45:56 PM ET — do not trust a stale snapshot.

## 2. Registered-task check (same CLI, added tonight)

Do not trust ping-only. `inspect.registered()` expected: `connectivity_probe`, `judge_transcript`, `summarize_conversation`, `embed_chunks`. Registration is a **separate** line (`ok` vs `missing_tasks`); `check_farm_health` status stays connectivity-only.

If ping is `ok` but summarize/embed missing: wrong worker process or old LaunchAgent (`com.local-agent.celery-worker` at stale `Documents/worker_farm`), even if "healthy."

Tonight the Mac Celery was running on LAN `192.168.50.8` with those queues subscribed and those tasks in stdout, but could not reach Redis at `10.90.90.1:6379` — so the workstation saw `no_workers` / empty registered.

Live (slow, not the fast suite):

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v
```

Skipped all 3 at 6:42 PM (`no_workers`); after datapath fix: 3/3 OK in 43.8s.

## 3. WireGuard interface vs datapath

Addresses: Mac `10.90.90.2` `utun5`, hub `10.90.90.1`, Windows service `WireGuardTunnel$hub` UDP 51820, Mac conf `/Users/rhineduran/wireguard/wg0.conf` Endpoint `192.168.50.208:51820` AllowedIPs `10.90.90.1/32`. Tunnel-only; no public ports.

Tonight: Windows hub UP, Mac VPN UI Connected on `utun5`, ICMP/SSH `10.90.90.2` from PC **dead**, Mac ping `10.90.90.1` **dead**, LAN SSH `192.168.50.8` / `louises-macbook-pro.local` **worked**.

Windows:

```
ping 10.90.90.2
& "C:\Program Files\WireGuard\wg.exe" show
Get-Service *wire*
```

Mac (tunnel first, then LAN; key `A:\Users\rhine\.ssh\workstation_to_mac`, user `rhineduran`):

```
ssh -i A:\Users\rhine\.ssh\workstation_to_mac -o IdentitiesOnly=yes rhineduran@10.90.90.2
ssh -i A:\Users\rhine\.ssh\workstation_to_mac -o IdentitiesOnly=yes rhineduran@louises-macbook-pro.local
ifconfig utun5
wg show
ping 10.90.90.1
```

Then TCP `10.90.90.1:6379` from the Mac. After tonight's fix: ICMP to `10.90.90.1` can still fail (Windows firewall) while TCP/SSH/Celery work — do **not** treat ICMP-to-hub as the health signal.

## 4. Login-item / LaunchDaemon conflicts

Tonight's root causes:

- WireGuard.app login item **on** (`gui/503/com.wireguard.macos.login-item-helper` enabled). App + Network Extension owned `utun5` (`workstation_gateway`). Handshake to `192.168.50.208:51820` never completed. Conflicting routes: NE ifscoped default via `utun5` vs LAN default on `en0`.
- LaunchDaemon `com.local-agent.wireguard-wg0` loaded, **not** running, last exit 1. `/usr/local/bin/wg-quick` shebang `env bash`; launchd PATH `/usr/bin:/bin:/usr/sbin:/sbin` → macOS bash 3.2; Homebrew `wg-quick` needs bash 4+. Log `/var/log/wireguard-wg0.log`: `wg-quick: Version mismatch: bash 3 detected, when bash 4+ required` (twice at 6:30 PM boot). Plist had `RunAtLoad`, no `KeepAlive`.
- Leftover (not the WG root cause): crash-looping LaunchAgent `com.local-agent.celery-worker`. Replaced in place with farm `.env` wrapper, queues `probe,judge,summarize,embed`, `ThrottleInterval` 10.
- Do **not** install a second daemon `com.local-agent.wg-quick`. One label: `com.local-agent.wireguard-wg0`.

```
launchctl list | grep -iE 'wg|wireguard|celery|worker'
launchctl print gui/503/com.wireguard.macos.login-item-helper
launchctl print-disabled gui/503 | grep -i wireguard
launchctl print system/com.local-agent.wireguard-wg0
plutil -p /Library/LaunchDaemons/com.local-agent.wireguard-wg0.plist
cat /var/log/wireguard-wg0.log
```

Who owns `utun5`: app NE `workstation_gateway` vs `wireguard-go`.

After a plist file patch, confirm the **loaded** job (`launchctl print`), not just the file. Watch ~2:55 AM ET: file patched (PATH includes `/usr/local/bin`, `KeepAlive SuccessfulExit false`, already-up guard) but loaded job still **old** (`program=/usr/local/bin/wg-quick`, PATH without `/usr/local/bin`, no `KeepAlive`, pid 8016, runs=3, last exit=1). launchd picks up `KeepAlive`/PATH only after `bootout`+`bootstrap` of that same job. Do not bounce the live tunnel until a planned reboot. Do not reboot unless Rhine explicitly says to.

Target plist: already-up guard then exec `/usr/local/bin/wg-quick`, Homebrew PATH baked in, `KeepAlive {SuccessfulExit: false}`. `KeepAlive` does not fix NAT-timeout/sleep silence.

## If you are in this hole again — what restored the datapath (~1:19 AM ET)

Did **not** bounce the Windows hub.

1. Disable login-item helper; `scutil --nc stop workstation_gateway`; quit WireGuard.app/NE (`utun5` gone).
2. `wg-quick` wrapper so launchd finds bash 5 (copy `/Users/rhineduran/wireguard/wg-quick-wrapper.sh`). Fragile if `brew upgrade wireguard-tools` restores the Homebrew symlink.
3. `launchctl kickstart system/com.local-agent.wireguard-wg0` (no sudo). Log: `wireguard-go` utun, Interface for `wg0` is `utun5`, route `10.90.90.1/32` via `utun5`.
4. Celery reconnected 1:20:33 AM ET `celery@Louises-MBP` ready.
5. First live embed failed `OllamaUnavailable` `127.0.0.1:11434`; started `ollama serve`; LaunchAgent recycled the worker.

After: one owner = LaunchDaemon/`wireguard-go` as root; login item disabled; `workstation_gateway` Disconnected; no ifscoped default on `utun5`; default via `en0`; `10.90.90.1/32` via `utun5` only.

Healthy pre-reboot: `farm_health` `ok`, registered tasks present, live summarize+embed pass, daemon owns `utun5`, login item disabled. **Reboot persistence is not confirmed.**
