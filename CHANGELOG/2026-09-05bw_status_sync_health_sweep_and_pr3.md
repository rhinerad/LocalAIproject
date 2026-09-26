# 2026-09-05bw — Status sync: health sweep found minor leftovers, Android PR 3 shipped

## Scope

Operator-facing tracking entry for two reports (health sweep / `bv`).
No new production work from this entry.

## Health sweep (Yellow, Task #65) — not fully clean, correctly reported not fixed

GPU idle (67 MiB), no ComfyUI, workstation Ollama normal, farm healthy
(`qwythos_evaluate` registered, Redis 39h up, hub intact), Mac keep_alive
confirmed still 30m via live `launchctl` env (the empty `ollama ps` is
the 30-minute timer having elapsed since the last warm load ~85 minutes
ago, not the setting failing — correctly distinguished).

Three real leftovers, correctly reported rather than silently touched:

1. The edge overlay + gateway (WireGuard `edge-phone`, gateway pid 46176
   on both listener ports) are still up from today's Pixel work — expected
   to still be open given that work is still in progress, not a leak.
2. `watch_edge_gateway_listeners.ps1` (a session watcher, not a farm
   service) still running — harmless, worth killing once the Pixel work
   actually concludes.
3. The Mac's live Celery worker doesn't have `judge_transcript_semantic`
   registered yet, because it wasn't kickstarted after today's deploy.
   `qwythos_evaluate` is fine. This is deploy lag, not a bug — and low
   urgency since the semantic judge defaults off anyway.

## Android companion PR 3 shipped (Orange)

`MANAGE_EXTERNAL_STORAGE` deleted from the buildozer spec's permission
list, and the static test now walks all overlay source files
(`.py`/`.spec`/`.xml`/`.java`/`.kt`/`.gradle`) failing the build if any
of the forbidden tokens appear — all-files storage, `pm install`/
`installPackage`, privileged `INSTALL_PACKAGES`, `BIND_DEVICE_ADMIN`, and
`REQUEST_INSTALL_PACKAGES` (correctly still forbidden until PR 6). 6/6
tests, no Android toolchain invoked. PR 3b (the pyjnius SAF spike)
correctly remains unauthorized — A13 (toolchain download) has not been
given.

## Status

Task #65 closed (reported, not auto-fixed, per instruction). No urgent
action needed on any of the three leftovers — items 1 and 3 are
naturally resolved once the Pixel work wraps and the Mac worker is next
restarted respectively; item 2 is a one-line cleanup whenever convenient.
