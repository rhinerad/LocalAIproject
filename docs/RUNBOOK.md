# Worker-farm troubleshooting runbook

Date: 2026-09-03. Operator checklist from the 2026-09-02 evening through
~2:55 AM ET debug. **Docs-only.** This does not change farm code, plists,
or LaunchAgents.

Use this when the farm "looks broken": missing workers, green health that
still fails jobs, a tunnel that says Connected but Redis/SSH are dead, or
a daemon that exits with nothing useful in the terminal.

Tonight's full incident notes (addresses, exact log lines, what restored
the datapath) live in `docs/FARM_HEALTH_RUNBOOK.md`. Current routing
picture: `docs/ARCHITECTURE.md`. Do not treat the 10-node plans as live.

Mac WireGuard/Celery **reboot persistence is not confirmed.** Do not
reboot the Mac unless Rhine explicitly says to. Workstation farm Redis
on Ubuntu-24.04 Docker CE **is** reboot-verified (`2026-09-03bh` /
`2026-09-04a`).

Work from the repository root on the workstation unless a block says Mac.

---

## Redis engine (workstation)

**Live path:** Ubuntu-24.04 Docker CE `local-agent-phase1-redis` via
`\local-agent-wsl-docker-boot`. User-env `FARM_REDIS_ENGINE=wsl`.
Windows `127.0.0.1:6379` is `wslrelay`. Do not start Docker Desktop and
do not wait for **Engine running** as the primary recovery.

`START_PHASE1_BROKER.ps1` / `doctor.py` still treat unset
`FARM_REDIS_ENGINE` as `desktop`. That is **Desktop rollback only, not
the live default.** Rollback: `FARM_REDIS_ENGINE=desktop` (or unset the
user env), start Docker Desktop, wait until it shows **Engine running**.

If Redis looks down: `wsl -l -v` (Ubuntu-24.04 Running),
`wsl -d Ubuntu-24.04 -- docker info`, then
`docker inspect local-agent-phase1-redis` in that distro. Docker Desktop
stopped/`com.docker.backend` owning 6379 is a regression, not health.

---

## 0. Is this the workstation, or the farm?

When *this* machine's path to the Mac drops, do **not** treat that as a
farm regression.

1. Retry the same check once. A single timeout is not a diagnosis.
2. Bypass the tunnel. LAN SSH to the Mac still works when `10.90.90.0/28`
   is dead:
   ```
   ssh -i A:\Users\rhine\.ssh\workstation_to_mac -o IdentitiesOnly=yes rhineduran@louises-macbook-pro.local
   ```
   (LAN IP tonight: `192.168.50.8`.)
3. From that Mac shell, ping/TCP the hub yourself (`10.90.90.1:6379`).
4. Only if LAN SSH also fails is the Mac actually down. Otherwise keep
   going — the farm process may be fine and the tunnel/path is the bug.

Trap: the workstation's own connection flaking looks identical to "Redis
is down" or "no workers" in `farm_health`.

---

## 1. Connectivity is not task availability

`farm_health` answers "can I talk to a worker?" It does **not** answer
"will summarize/embed run?" The agent hot path reads `farm_status.json`
(`farm_offload.farm_reachable()` / `should_route()`) and skips Celery when
the snapshot is missing, stale (>90s), or not `status=="ok"`. Live CLI
`inspect` is still a diagnostic — do not trust a stale snapshot as "up"
for operator debugging, but the hot path treats stale as down.

On the workstation, farm venv:

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health --json
```

That is TCP to `FARM_BROKER_URL` (hub `10.90.90.1:6379`, not
`127.0.0.1`) plus Celery `inspect.ping()`. Status is connectivity-only:
`ok` / `no_workers` / `unreachable` / `unconfigured`. Exit 0 only when
`ok`.

Then check **registered tasks** before trusting `ok`:

```
celery -A local_agent.worker_farm.celery_app inspect registered
```

(same farm venv, same broker). Expected: `connectivity_probe`,
`judge_transcript`, `summarize_conversation`, `embed_chunks`.

| Health ping | Registered | Meaning |
|---|---|---|
| not `ok` | (empty) | Datapath or worker process. Go to §2. |
| `ok` | missing summarize/embed | Wrong worker / stale LaunchAgent. Go to §5. |
| `ok` | all four present | Connectivity is fine. If jobs still fail, check Mac Ollama (`127.0.0.1:11434`) and live tests below. |

Live (slow, not the fast suite):

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v
```

Tonight ~6:42 PM: broker reachable, **no worker answered ping**,
registered empty — Windows hub was up; Mac Celery was running on LAN
but could not reach Redis over the tunnel.

---

## 2. Interface-up is not a datapath

Windows hub and Mac `utun5` / `10.90.90.2` can both say Connected while
Redis / SSH / ICMP over `10.90.90.0/28` are dead.

Addresses: Mac `10.90.90.2` on `utun5`, hub `10.90.90.1`, Windows
service `WireGuardTunnel$hub` UDP 51820, Mac conf
`/Users/rhineduran/wireguard/wg0.conf` Endpoint
`192.168.50.208:51820` AllowedIPs `10.90.90.1/32`. Tunnel-only.

Workstation:

```
ping 10.90.90.2
& "C:\Program Files\WireGuard\wg.exe" show
Get-Service *wire*
```

Then SSH over the tunnel, and if that fails, LAN (§0):

```
ssh -i A:\Users\rhine\.ssh\workstation_to_mac -o IdentitiesOnly=yes rhineduran@10.90.90.2
```

On the Mac:

```
ifconfig utun5
wg show
ping 10.90.90.1
```

Then TCP `10.90.90.1:6379` from the Mac. After tonight's fix, ICMP to
the hub can still fail (Windows firewall) while TCP/SSH/Celery work.
Do **not** treat ICMP-to-hub as health.

If the hub is up, LAN SSH works, and tunnel SSH/Redis do not: the Mac
side does not own the datapath. Go to §3.

---

## 3. Login item vs LaunchDaemon (who owns `utun5`?)

A GUI app login item and a system daemon can both try to own the same
WireGuard interface at boot. Disabling it as a "login item" in the UI
is **not** enough; disable the underlying launchd job.

Tonight: WireGuard.app login item **on**
(`gui/503/com.wireguard.macos.login-item-helper`). The Network
Extension owned `utun5` (`workstation_gateway`); handshake never
completed; conflicting routes (ifscoped default via `utun5` vs LAN
default on `en0`). Meanwhile LaunchDaemon
`com.local-agent.wireguard-wg0` was loaded and **not** running.

On the Mac:

```
launchctl list | grep -iE 'wg|wireguard|celery|worker'
launchctl print gui/503/com.wireguard.macos.login-item-helper
launchctl print-disabled gui/503 | grep -i wireguard
launchctl print system/com.local-agent.wireguard-wg0
```

Who owns `utun5`: app NE `workstation_gateway` vs `wireguard-go`.

Healthy: one owner = LaunchDaemon / `wireguard-go` as root; login-item
helper disabled; `workstation_gateway` Disconnected; no ifscoped
default on `utun5`; default via `en0`; `10.90.90.1/32` via `utun5`
only.

Do **not** install a second daemon `com.local-agent.wg-quick`. One
label: `com.local-agent.wireguard-wg0`.

What restored the datapath tonight (did **not** bounce the Windows
hub): disable the login-item helper; `scutil --nc stop workstation_gateway`;
quit WireGuard.app/NE (`utun5` gone); then kickstart
`system/com.local-agent.wireguard-wg0`. Details in
`docs/FARM_HEALTH_RUNBOOK.md`.

---

## 4. The plist on disk is not the loaded job

Editing or relinting a LaunchDaemon/LaunchAgent plist **does not**
change what launchd is running. Only `bootout`+`bootstrap` of that
same job (or a real reboot) does.

`plutil -p` / a file diff is necessary and not sufficient.
`launchctl print` of the loaded job is the only real confirmation.

```
plutil -p /Library/LaunchDaemons/com.local-agent.wireguard-wg0.plist
launchctl print system/com.local-agent.wireguard-wg0
```

Compare `program`, `PATH`, `KeepAlive`, and the log path on the
**loaded** job to the file. Tonight ~2:55 AM ET the file already had
Homebrew PATH, `KeepAlive SuccessfulExit false`, and an already-up
guard — and the loaded job was still the old one
(`program=/usr/local/bin/wg-quick`, PATH without `/usr/local/bin`, no
`KeepAlive`, last exit 1).

Do not bounce the live tunnel "to pick up the plist" unless Rhine
asked. `kickstart` restarts the **currently loaded** program; it does
not reload keys from disk.

---

## 5. Launchd PATH vs bash 4+ (silent exit)

launchd's default PATH is `/usr/bin:/bin:/usr/sbin:/sbin`. `env bash`
on that PATH is macOS bash **3.2**, not Homebrew bash 4+. Homebrew
`wg-quick` (`/usr/local/bin/wg-quick`) requires bash 4+. Symptom: the
daemon exits immediately with **no useful error in the terminal**.
The log is the diagnosis.

```
cat /var/log/wireguard-wg0.log
```

Tonight, twice at 6:30 PM boot:

`wg-quick: Version mismatch: bash 3 detected, when bash 4+ required`

Confirm which bash a loaded job would get:

```
launchctl print system/com.local-agent.wireguard-wg0 | grep -A2 PATH
/bin/bash --version
/usr/local/bin/bash --version
head -1 /usr/local/bin/wg-quick
```

Fix is a wrapper (or a baked-in PATH) so the daemon never sees bash
3.2. Tonight's wrapper:
`/Users/rhineduran/wireguard/wg-quick-wrapper.sh`. Fragile if
`brew upgrade wireguard-tools` restores the Homebrew symlink.

Same class of bug applies to any `com.local-agent.*` script that
assumes bash 4+.

---

## 6. Orphaned automation (do not assume a clean slate)

Before adding a plist, list everything already loaded under this
project's labels. Tonight found **two** independently, both silently
broken:

1. `com.local-agent.wireguard-wg0` — loaded, not running, last exit 1
   (bash 3.2 trap, §5).
2. `com.local-agent.celery-worker` — leftover LaunchAgent crash-looping
   on a stale `Documents/worker_farm` tree. A ping-healthy worker on
   that job will still miss summarize/embed (§1).

```
launchctl list | grep -i 'local-agent'
ls /Library/LaunchDaemons/com.local-agent.*
ls ~/Library/LaunchAgents/com.local-agent.*
```

Replace in place; do not stack a second label for the same role.

Celery worker expected: farm `.env` wrapper, queues
`probe,judge,summarize,embed`. After a datapath fix, if ping is `ok`
but jobs fail with `OllamaUnavailable` / `127.0.0.1:11434`, start
`ollama serve` on the Mac — the worker will not pull models from the
workstation CPU port (`11435`).

---

## Stop conditions (healthy enough)

All of these, in this order:

1. LAN SSH works, so the Mac is up even if the tunnel is not.
2. `farm_health` is `ok` **and** registered tasks include probe, judge,
   summarize, embed.
3. Live summarize+embed pass (or you know Ollama on the Mac is the
   remaining miss).
4. `launchctl print` of `system/com.local-agent.wireguard-wg0` matches
   the plist you think is on disk (PATH, program, KeepAlive).
5. One owner of `utun5` (`wireguard-go` via the LaunchDaemon); WireGuard
   login-item helper disabled.
6. No extra `com.local-agent.*` jobs besides the daemon and the current
   Celery agent.

Until a reboot is tested, treat this as "works until next boot," not
"persistent."
