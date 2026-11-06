# 2026-09-05ar — Mac Ollama keep_alive=30m: bootstrap fixed, proven live

## Scope

🟡 lane. Closes out the incident from `2026-09-05am`
(bootstrap failure, Ollama down). No code change — verification only.

## What's confirmed

Second sudo (`mac_sudo_bootstrap_ollama.sh`) succeeded: daemon reloaded
(pid 51090), live `launchctl print` and the on-disk plist both show
`OLLAMA_KEEP_ALIVE => 30m`, HTTP confirms the daemon answers
(`{"version":"0.33.2"}`).

Stronger proof than the original 2026-09-05o test: a 5-minute-30-second
idle gap was deliberately held between the second and third calls — long
enough that the old 5-minute daemon default would have evicted the model
— and Qwythos was still resident (`ollama ps` showed "UNTIL 24 minutes,"
consistent with the 30-minute timer measured from the original load, not
a fresh cold load). Third call: 2.156s wall, 0.052s `load_duration`,
still warm.

## Status

Both the original Task #43 goal (avoid repeated cold loads) and the
overnight Task #47 goal (Mac worker healthy again) are now fully closed
with live evidence, not just a plist edit that might not have taken
effect. Farm (`farm_health`, `qwythos_evaluate` registered) was already
confirmed healthy in `2026-09-05aa` and is unaffected by this Ollama-only
incident.
