# 2026-09-05aq — Live Ollama LaunchDaemon `OLLAMA_KEEP_ALIVE=30m` verified

Date: 2026-09-05 15:12–15:19 EDT. Host: Louises-MBP (`10.90.90.2`).
Id from `python scripts/next_changelog_id.py --date 2026-09-05`:
**2026-09-05aq**. Follow-up to `2026-09-05o` (request keep_alive) and
`2026-09-05al` (plist copied, bootstrap failed, Ollama down).

## Live job (after second sudo bootstrap)

`sudo /tmp/mac_sudo_bootstrap_ollama.sh` at **15:12:27 EDT** loaded
the already-copied plist. `BOOTSTRAP_OK`. pid 51090
`/usr/local/bin/ollama serve`. HTTP `{"version":"0.33.2"}`.

On-disk `/Library/LaunchDaemons/com.local-agent.ollama.plist`
(`-rw-r--r-- root wheel`):

```
EnvironmentVariables = {
  HOME => /Users/rhineduran
  LOGNAME => rhineduran
  OLLAMA_HOST => 127.0.0.1:11434
  OLLAMA_KEEP_ALIVE => 30m
  OLLAMA_MODELS => /Users/rhineduran/.ollama/models
  PATH => /usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
  USER => rhineduran
}
KeepAlive => 1
Label => com.local-agent.ollama
ProgramArguments => /usr/local/bin/ollama serve
RunAtLoad => 1
UserName => rhineduran
```

`launchctl print system/com.local-agent.ollama` live environment
includes **`OLLAMA_KEEP_ALIVE => 30m`**. `ps eww` on `ollama serve`:
`OLLAMA_HOST`, **`OLLAMA_KEEP_ALIVE=30m`**, `OLLAMA_MODELS`.

Inspect dump:
`artifacts/benchmarks/2026-09-05aq_ollama_launchctl_inspect.txt`.

## Timing (same POST shape as 2026-09-05o, keep_alive omitted)

Two back-to-back `POST /api/chat` to `127.0.0.1:11434`,
`richardyoung/qwythos-9b-abliterated:latest`, `num_predict=8`,
`num_ctx=8192`, `num_gpu=0`. **No `keep_alive` in the JSON** so the
daemon env is what applies (2026-09-05o put `"keep_alive":"30m"` in
the request, which would mask a 5m daemon default).

| Call | wall | `load_duration` | notes |
|---|---|---|---|
| first | **23.946 s** | **19.967 s** | cold (`/api/ps` empty before) |
| second, immediate | **2.526 s** | **0.004 s** | warm |
| `/usr/local/bin/ollama ps` after pair | — | — | Qwythos 6.2 GB, **UNTIL 29 minutes from now** |
| after 330 s idle | — | — | still loaded, **UNTIL 24 minutes from now** |
| third (5m30s later) | **2.156 s** | **0.052 s** | still warm; **UNTIL 29 minutes** again |

2026-09-05o (request keep_alive, 5m daemon default): first **45.300 s**
/ 40.882 s load, second **3.188 s** / 0.058 s, UNTIL 29 min from the
request field. A 5m daemon default would have evicted before the third
call here; it did not.

Raw: `artifacts/benchmarks/2026-09-05aq_qwythos_daemon_keepalive_measure.txt`.
Celery was not kickstarted. `farm_health --json` after the measure:
`ok`, `qwythos_evaluate` still registered on `celery@Louises-MBP`.

No workstation code change.
