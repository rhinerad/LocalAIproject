# 2026-09-03al — Secret-writing scripts apply the 2026-09-03aj ACL lockdown

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

2026-09-03aj locked the three live secret files once. The leftover: `Initialize-Phase1Secrets.ps1` and `Add-Phase1SecondaryWorkerCredential.ps1` wrote new `.env` / `.env.<user>.generated` files without an ACL, so they re-inherited the wide `worker_farm/` DACL. Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-03al** (letters through `ak` on disk, including three `aj` files).

No secret values are recorded here.

## What changed

Shared helper `local_agent/worker_farm/Lock-Phase1SecretFile.ps1` applies the same lockdown as aj:

```text
icacls <file> /inheritance:r
icacls <file> /grant:r "NT AUTHORITY\SYSTEM:(R,W)"
icacls <file> /grant:r "DURANGAMINGPC\rhine:(R,W)"
```

Administrators is still not granted (`tiffa` is in that group).

Called after every secret write:

- `Initialize-Phase1Secrets.ps1` — after writing `.env` (or `-EnvFile`)
- `Add-Phase1SecondaryWorkerCredential.ps1` — after writing `.env.<username>.generated`
- `Restore-Phase1SecondaryWorkerCredentials.ps1` — after `Copy-Item` into `runtime/redis-acl/` (this is Add-Phase1's second write; `-SyncOnly` from `START_PHASE1_BROKER.ps1` uses the same path)

## Directory ACL: not locked

`worker_farm/` is the source tree (Python, tests, dashboard, logs), owner `DuranGamingPC\CodexSandboxOffline`, inherited DACL still includes `CodexSandboxUsers`, `tiffa`, Administrators, and stale sandbox SIDs. Tightening the directory default ACL would break agent edits and anything else that creates files there. Secret writers lock each secret file instead.

## Verification

Both scripts gained `-LockdownProbe` (temp file, lock, assert, delete; does not touch live `.env` or Redis). Helper also has `-Probe`.

```text
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_phase1_secret_acl -v
```

4/4 OK (~1.2s): helper `-Probe`, `Initialize-Phase1Secrets.ps1 -LockdownProbe` (real generate-into-temp + lock; temp deleted), `Add-Phase1SecondaryWorkerCredential.ps1 -LockdownProbe` (dummy fragment + lock; no Redis), and a source check that each script locks after write/copy.

Live `.env` still `rhine:(R,W)` + `SYSTEM:(R,W)` after the probes. `Restore-Phase1SecondaryWorkerCredentials.ps1 -SyncOnly` restaged the existing `mac_worker` fragment (no password rotation) and left `runtime/redis-acl/.env.mac_worker.generated` with the same two ACEs.

Initialize's `RandomNumberGenerator.Fill` (PS 7 / newer .NET) was replaced with `Create(); GetBytes()` to match Add-Phase1 so the probe runs under Windows PowerShell 5.1. Same CSPRNG class; does not rotate the live credential.

## Manual re-check

```text
powershell -NoProfile -ExecutionPolicy Bypass -File local_agent\worker_farm\Initialize-Phase1Secrets.ps1 -LockdownProbe
powershell -NoProfile -ExecutionPolicy Bypass -File local_agent\worker_farm\Add-Phase1SecondaryWorkerCredential.ps1 -LockdownProbe
```

Both print `PASS:` and leave the live files alone.
