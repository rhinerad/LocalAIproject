# 2026-09-05aa — Mac worker back: hung Celery recovered; Qwythos registered

Date: 2026-09-05 ~11:37 EDT. Hosts: DuranGamingPC and Louises-MBP
(`10.90.90.2` / LAN `192.168.50.8`). Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05aa**.

Follow-up to `2026-09-05f` (frozen/asleep overnight) and `2026-09-05o`
(request `keep_alive=30m` shipped; system plist still pending sudo).

## Checklist (order from 2026-09-05f)

### 1. SSH + `launchctl` / `ps` — reachable, process not dead

Both overlay and LAN SSH answered `SSH_OK` at 11:35 EDT.
`uptime`: 1 day 15:27 (asleep/frozen, not a clean shutdown). Console
user `rhineduran` since Sep 3 20:21.

`launchctl print system/com.local-agent.celery-worker`: `state=running`,
pid 35596 (`python -m local_agent.worker_farm.worker`), `runs=8`.

`ps` showed **four leftover Celery MainProcess workers** sharing
nodename `celery@Louises-MBP`, plus the live wrapper:

| pid | started | Redis ESTABLISHED to `10.90.90.1:6379` |
|---|---|---|
| 25840 | 3:38 PM (orphan, PPID 1) | 9 sockets |
| 34899 | 6:58 AM | 4 |
| 35081 | 8:07 AM | 4 |
| 35606 (child of 35596) | 10:17 AM | 9 |
| 35622 (prefork of 35606) | 10:17 AM | — |

stderr: `celery@Louises-MBP ready` at 10:17:48 after the morning
kickstart, then **11:18:15 broker lost / Broken pipe** and **no
reconnect** (`Connected to redis` never logged again). Mac `nc` to
`10.90.90.1:6379` succeeded at the re-check. Same hung-socket
signature as 2026-09-05f, now with a live sshd.

Ollama LaunchDaemon still running (`ollama serve` pid 35520). Live
`/Library/LaunchDaemons/com.local-agent.ollama.plist` still has **no**
`OLLAMA_KEEP_ALIVE` (default 5m). `ollama ps` showed Qwythos
**Stopping...** (~80 min after the 10:16 30m request keep-alive).

### 2. `farm_health --json` — missing task list (restart condition)

Farm venv, repo root, **before** restart:

```
status: no_workers
broker_reachable: true
workers_responding: false
registered_tasks: []
error: broker reachable, no worker answered ping
```

`local_agent.worker_farm.tasks.qwythos_evaluate` was **not** visible
to inspect (inspect never reached a worker). stdout banner from the
10:17 start still listed it locally.

### 3. Restart — yes, because step 2 failed

Did **not** restart reflexively on launchd-running. Restarted because
inspect was empty and the 10:17 worker had not recovered from the
11:18 broker drop. Also killed the three orphan MainProcess PIDs so
they would stop holding stale Redis clients.

```
kill 25840 34899 35081 35606 35622
launchctl kickstart -k system/com.local-agent.celery-worker
```

After (11:37:45 EDT): single tree pid 36469 → 36474 → 36477;
10 Redis sockets from 36474 only; log `celery@Louises-MBP ready.`

`farm_health --json` **after** (exit 0):

```
status: ok
workers_responding: true
workers: ["celery@Louises-MBP"]
missing_expected_tasks: []
registered_tasks includes local_agent.worker_farm.tasks.qwythos_evaluate
```

Full registered set: `connectivity_probe`, `distill_export`,
`embed_chunks`, `judge_transcript`, `qwythos_evaluate`,
`summarize_conversation`.

## Keep-alive plist sudo (in progress, not done)

`sudo -n` is still unavailable. A GUI Terminal window was opened on
Louises-MBP at 11:40 EDT:

```
sudo /tmp/mac_sudo_swap_apply.sh
```

pid 36901 `sudo` + 36900 `/tmp/mac_sudo_swap.command` on `ttys003`,
waiting for the console password. Staged source is
`local_agent/worker_farm/macos/com.local-agent.ollama.plist`
(`OLLAMA_KEEP_ALIVE=30m`). Live LaunchDaemon plist is **unchanged**
until that password is entered.

Workstation watcher timed out at 12:06 EDT (25 min) with the prompt
still live (`etime` 26:45, no `/tmp/mac_sudo_swap.out`). Re-focused
Terminal.app; watch resumed. Second watch timed out at 14:07 EDT
(~2.5 h `etime` on `ttys003` pids 36900/36901). Live plist still
lacks `OLLAMA_KEEP_ALIVE`. Farm `farm_health` still `ok` with
`qwythos_evaluate` registered. Sudo prompt left in place; not killed.

No code change. No GPU work.
