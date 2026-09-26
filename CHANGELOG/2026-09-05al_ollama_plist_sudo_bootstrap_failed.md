# 2026-09-05al — Ollama 30m plist copied; LaunchDaemon bootstrap failed

Date: 2026-09-05 ~15:04–15:07 EDT. Host: Louises-MBP. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05al**.

Follow-up to `2026-09-05o` (staged 30m plist) and `2026-09-05aa`
(interactive `sudo /tmp/mac_sudo_swap_apply.sh`).

## What the sudo did

Operator entered the password at **15:04:19 EDT**. Apply ran as root.
On-disk `/Library/LaunchDaemons/com.local-agent.ollama.plist` is now
the 30m copy (`-rw-r--r-- root wheel`, 1317 bytes):

```
OLLAMA_KEEP_ALIVE => "30m"
```

plus existing `OLLAMA_HOST`, `OLLAMA_MODELS`, `HOME`/`USER`/`LOGNAME`/`PATH`.
`KeepAlive` 1, `RunAtLoad` 1, `UserName` rhineduran.

Then the script `launchctl bootout`'d the old job (`|| true`) and
`launchctl bootstrap system` **failed**: `Bootstrap failed: 5: Input/output error`.
`set -e` stopped the script before `SUDO_SWAP_DONE`. No live job.

## Live state at 15:06–15:07 EDT (not healthy)

| Check | Result |
|---|---|
| on-disk plist `OLLAMA_KEEP_ALIVE` | **30m** |
| `launchctl print system/com.local-agent.ollama` | **not loaded** (`Could not find service`) |
| `ollama serve` process | **none** |
| `127.0.0.1:11434` | **connection refused** |
| `sudo -n` from SSH | unavailable (tty-local timestamp) |

The 2026-09-05o two-call Qwythos timing test was **not run** — there is
no server. Celery was not kickstarted.

Non-root `launchctl bootstrap system` from SSH also returned error 5.
A second GUI Terminal was opened at 15:07 (`ttys003`) with
`sudo /tmp/mac_sudo_bootstrap_ollama.sh` to `bootstrap` + `kickstart`
the already-copied plist. That reload succeeded at 15:12 EDT; live
verify is `CHANGELOG/2026-09-05aq_ollama_daemon_keepalive_30m_live.md`.

No workstation code change.
