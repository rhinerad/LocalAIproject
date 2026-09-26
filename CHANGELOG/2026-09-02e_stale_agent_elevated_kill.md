# 2026-09-02e — Stop-StaleAgent elevated leftover (port 8760)

## Root cause (confirmed)

`START_LOCAL_AGENT_GUI.ps1` failed because PID **23980** (`python.exe`, started 2026-09-01 9:03:47 PM ET) still owned `127.0.0.1:8760` and `/api/status` **timed out**.

Token check: `TokenIsElevated=1` for PID 23980 and parent PowerShell PID **5856**. This launcher run was `TokenIsElevated=0`. Unelevated `Stop-Process -Force` and `taskkill /T /F` both returned **Access is denied**. Parent 5856 is the leftover Administrator PowerShell that originally ran this launcher (`python server.py` is the last command, so that window kept the elevated child alive). No scheduled task. This is the repeatable trap: one elevated launch leaves an elevated python that a later normal double-click cannot replace, and the hung server is not reusable (`Test-AgentReady` false because status times out).

Running the *whole* launcher as Administrator would start a new elevated python and repeat the trap tomorrow.

## Fix

`Stop-StaleAgent` now, after unelevated Stop-Process/taskkill fail, requests a **one-shot** `taskkill /PID /T /F` with `-Verb RunAs` (UAC), then continues the launcher **unelevated** so the replacement server is not admin. Did not change `APP_REVISION`, `agent.py`, or `server.py`.

## Proof planned in the same session

One-shot elevated taskkill of 23980 (and parent 5856 if still up), then unelevated relaunch, then `GET http://127.0.0.1:8760/api/status`.

## Same-session outcome

Launcher patch landed in `START_LOCAL_AGENT_GUI.ps1` (`Stop-StalePid` one-shot `taskkill -Verb RunAs`). Two UAC prompts for `taskkill /PID 23980 /T /F` were cancelled (`The operation was canceled by the user`). PID 23980 and parent 5856 still Listen on 8760; `/api/status` still times out. Fresh unelevated launch is blocked until that elevated leftover is closed or a UAC Yes is given. Did not run the whole launcher as Administrator (that recreates the trap).

## Proof (same session, after the NativeCommandError wrap)

Unelevated `taskkill` stderr was a terminating `NativeCommandError` under `Continue = 'Stop'`, so the first patched launch never reached UAC. Wrapped that invoke in try/catch with EAP Continue. Next launch: UAC one-shot succeeded (`elevated taskkill released PID 23980`). Replacement `server.py` is PID 32316, parent unelevated launcher 26024, command line visible. `GET http://127.0.0.1:8760/` 200. `GET /api/status` 200 with `app_revision=2026-09-01-action-resolver-r76`.
