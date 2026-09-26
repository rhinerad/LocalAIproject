# 2026-09-03aj — Windows-side farm .env ACL lockdown (chmod 600 equivalent)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Mac farm `.env` was world-readable (broker URL inside); Bot 9 tightened that copy to `600`. This is the same check on the Windows hub. Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-03aj** (letters through `ai` already on disk).

No secret values are recorded here — key names only.

## Which files actually hold broker URL / credentials

Inspected key names (values redacted) under `local_agent/worker_farm/`:

| File | Holds live secrets? | Keys |
| --- | --- | --- |
| `.env` | **yes** — hub Redis password, broker/result URLs, AES key | `REDIS_PASSWORD`, `FARM_BROKER_URL`, `FARM_RESULT_BACKEND`, `FARM_ROOT`, `FARM_ENCRYPTION_KEY_B64`, `FARM_QUEUES`, `FARM_CONCURRENCY` |
| `.env.mac_worker.generated` | **yes** — Mac worker broker/result URLs (password in the URL) | `FARM_BROKER_URL`, `FARM_RESULT_BACKEND`, `FARM_QUEUES`, `FARM_CONCURRENCY`, `EQUAL_SHARES_CPU_HOST`, `FARM_SUMMARIZE_MODEL` |
| `runtime/redis-acl/.env.mac_worker.generated` | **yes** — same Mac worker fragment as above | same keys |
| `.env.example` | **no** — placeholders (`replace-with-...`) | same key names as `.env` |

No other `.env*` files under `worker_farm/`. WSL `ls` of the same paths is the NTFS files via drvfs (`-rwxrwxrwx` is the metadata-less mount view, not a second copy). No `EqualSharesLocalAgent\worker_farm` AppData copy.

`.env` is what `_farm_submit_wait._load_env_file`, `doctor.py`, `farm_health.py`, and the Phase 1 PowerShell scripts read. The two `.env.mac_worker.generated` files are the gitignored Mac-worker credential fragments (changelog 2026-09-03o).

Did **not** change `.env.example`. Did **not** touch `wireguard/hub-private.key` (out of this check's `.env` scope).

## Before (same issue class as Mac 644)

All three live files inherited the parent `worker_farm/` DACL. `icacls` showed `(I)` ACEs including:

- `DURANGAMINGPC\rhine:(I)(F)`
- `DuranGamingPC\tiffa:(I)(F)` — second interactive local admin
- `BUILTIN\Administrators:(I)(F)` — would keep `tiffa` in even after dropping her explicit ACE (`tiffa` is in Administrators; see 2026-09-03y)
- `DuranGamingPC\CodexSandboxUsers:(I)(M)`
- ten unresolvable `S-1-5-21-…` SIDs with `(I)(M)` or `(I)(M,DC)` (stale sandbox identities)
- `NT AUTHORITY\SYSTEM:(I)(F)`

Not Everyone/Users, but readable by another local user and sandbox identities. That is the Windows equivalent of the Mac world-readable `.env`.

## After (chmod 600 equivalent)

On each of the three live files:

```text
icacls <file> /inheritance:r
icacls <file> /grant:r "NT AUTHORITY\SYSTEM:(R,W)"
icacls <file> /grant:r "DURANGAMINGPC\rhine:(R,W)"
```

`/inheritance:r` removes inherited ACEs (does not copy them). Administrators was **not** re-granted, because that group still contains `tiffa`. SYSTEM is the Windows root analogue so Task Scheduler / SYSTEM can still read.

Post-check (`Get-Acl` + `icacls`):

- Owner: `DURANGAMINGPC\rhine`
- `AreAccessRulesProtected = True` (inheritance off)
- ACEs only: `DURANGAMINGPC\rhine:(R,W)` and `NT AUTHORITY\SYSTEM:(R,W)`
- `tiffa`, `Administrators`, `CodexSandboxUsers`, and the unresolvable SIDs are gone
- Owner can still read the same key names

`.env.example` still has the inherited wide DACL (placeholders only).

## Leftover

`worker_farm/` directory ACL is unchanged (still the wide inherited DACL). `Initialize-Phase1Secrets.ps1` and `Add-Phase1SecondaryWorkerCredential.ps1` write new `.env` / `.env.<user>.generated` files without setting an explicit ACL, so a future generate would re-inherit the parent. This entry only locked the three files that currently hold live secrets.
