# 2026-09-05am — Mac Ollama daemon down mid-swap, needs a second sudo

## Scope

🟡 lane. Tracking entry for an in-progress incident, follows
`2026-09-05al_ollama_plist_sudo_bootstrap_failed.md`. Operator action
required, not a code change.

## What happened

First sudo (`mac_sudo_swap_apply.sh`) succeeded and wrote the 30m
`OLLAMA_KEEP_ALIVE` into the on-disk plist correctly — confirmed via a
direct read of `/Library/LaunchDaemons/com.local-agent.ollama.plist` at
15:04 EDT. But the script died before `SUDO_SWAP_DONE`: `bootout`
succeeded (unloading the running daemon) but the subsequent `bootstrap`
failed (`5: Input/output error`), leaving **no Ollama daemon loaded at
all**. `launchctl print system/com.local-agent.ollama` returns "Could
not find service"; `127.0.0.1:11434` is connection-refused.

## Current impact

Ollama is fully down on the Mac. Qwythos (and any other Mac-hosted
model) is unreachable until the daemon is reloaded. This does not affect
Celery/farm health directly (those were already confirmed healthy and
separate), but the Qwythos keep_alive timing test from 2026-09-05o
cannot run until this is fixed.

## What's needed

A second interactive sudo, already staged and waiting:
`sudo /tmp/mac_sudo_bootstrap_ollama.sh` in a new Terminal window on
Louises-MBP (ttys003). This reloads the already-correct 30m plist via
`bootstrap` + `kickstart`. Needs the operator's console password, same
as before.

## Next, once it loads

Confirm `launchctl` shows the live environment includes
`OLLAMA_KEEP_ALIVE=30m`, re-run the 2026-09-05o two-call timing test,
and this time also prove a >5 minute dwell without eviction (stronger
proof than the original test, which only showed the "until 29 minutes"
`ollama ps` line).
