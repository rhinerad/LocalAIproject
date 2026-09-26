# 2026-09-05o — Mac Qwythos `OLLAMA_KEEP_ALIVE` / request keep_alive 30m

Date: 2026-09-05. Hosts: DuranGamingPC (workstation) and Louises-MBP
(Mac farm worker, `10.90.90.2`). Id from
`python scripts/next_changelog_id.py`: **2026-09-05o**.

Qwythos-9B is the fast-tier farm tool-calling model. Every farm call
observed this session was a 60+ s cold load. 2026-09-04k already
measured `try_qwythos_on_farm` at **62.423 s** and `/usr/local/bin/ollama
ps` empty immediately after the turn.

## Live daemon setting (before)

SSH `rhineduran@10.90.90.2` at 08:07 and 10:16 EDT. LaunchDaemon
`system/com.local-agent.ollama` (`/Library/LaunchDaemons/com.local-agent.ollama.plist`):

| Source | `OLLAMA_KEEP_ALIVE` |
|---|---|
| on-disk plist `EnvironmentVariables` | **absent** (only `OLLAMA_HOST`, `OLLAMA_MODELS`, `HOME`/`USER`/`PATH`) |
| live `launchctl print` environment | **absent** |
| `ps eww` on `ollama serve` | `OLLAMA_HOST`, `OLLAMA_MODELS` only |

Unset means Ollama's own default (**5m**), not the GPU-tier CPU server's
`OLLAMA_KEEP_ALIVE=30m` (`START_LOCAL_AGENT_GUI.ps1` `$CpuOnly`).
`/api/ps` before the timed calls: empty.

`sudo -n` is unavailable on Louises-MBP (uid 503 is in `admin` but has
no passwordless sudo), so the system plist was **not** rewritten in
place. A 30m copy is staged at
`local_agent/worker_farm/macos/com.local-agent.ollama.plist` (and
`A:\Users\rhine\tmp-launchd\com.local-agent.ollama.plist`) for an
interactive sudo later:

```
sudo cp .../macos/com.local-agent.ollama.plist /Library/LaunchDaemons/com.local-agent.ollama.plist
sudo launchctl bootout system/com.local-agent.ollama
sudo launchctl bootstrap system /Library/LaunchDaemons/com.local-agent.ollama.plist
```

## What shipped without sudo (live on the worker)

Mac `~/worker_farm/local_agent/worker_farm/tasks.py` now sends
`keep_alive=_QWYTHOS_KEEP_ALIVE` (**`"30m"`**), matching the CPU-tier
convention. Mac `ollama_client.chat` already copies `keep_alive` into
the `/api/chat` payload when set (embed still uses `"0"`). Workstation
tree matches. Celery was `kickstart -k`'d; it came `ready` at 10:16:40
EDT then dropped off inspect again (WireGuard/SSH window is brief).

Tests (farm venv, repo root):

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_qwythos_keep_alive -v
  test_constant_is_30m ... ok
  test_evaluate_passes_keep_alive_30m ... ok
```

## Before / after timing (live, Mac `127.0.0.1:11434`)

Same process `qwythos_evaluate` uses. Two back-to-back
`POST /api/chat` with `keep_alive=30m`,
`richardyoung/qwythos-9b-abliterated:latest`, `num_predict=8`.
10:16 EDT 2026-09-05.

| Call | wall | `load_duration` | notes |
|---|---|---|---|
| first | **45.300 s** | **40.882 s** | cold load |
| second, immediate | **3.188 s** | **0.058 s** | warm |
| `/usr/local/bin/ollama ps` after | — | — | Qwythos 6.2 GB, **UNTIL 29 minutes from now** |

Raw: `artifacts/benchmarks/2026-09-05o_qwythos_keepalive_measure.txt`,
inspect: `artifacts/benchmarks/2026-09-05o_qwythos_keepalive_inspect.txt`.

Workstation `try_qwythos_on_farm` two-call was **not** a farm receipt:
`farm_status.json` flapped `ok` (14:17:56Z, `celery@Louises-MBP`) to
`no_workers` (14:18:27Z) inside the 90s snapshot window, so
`farm_offload` skipped Celery in 0.0 s. The Mac Ollama pair above is
the keep-alive proof; Celery is the same `127.0.0.1:11434` plus queue
overhead when the tunnel holds.

Prior farm cold (unchanged as the "before" farm-path number):
2026-09-04k `try_qwythos_on_farm` **62.423 s**, `ollama ps` empty
after the turn.

## Files

- `local_agent/worker_farm/tasks.py` (`_QWYTHOS_KEEP_ALIVE = "30m"`)
- `local_agent/worker_farm/test_qwythos_keep_alive.py`
- `local_agent/worker_farm/macos/com.local-agent.ollama.plist` (30m; not yet the live LaunchDaemon)
- `artifacts/benchmarks/2026-09-05_qwythos_keepalive_live.py` (farm two-call helper)
