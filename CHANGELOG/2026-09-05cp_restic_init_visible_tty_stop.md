# 2026-09-05cp — Restic installed and repo inited on D:; backup stopped for a visible TTY

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cp**.

Task #60/#62 execution. **No repository password is recorded here.**

## Preflight (measured immediately before init)

| Check | Value |
|---|---|
| GPU | RTX 5080 **32 °C, 0 % util, 67 MiB / 16303 MiB** (later recheck 31 °C) |
| 8188 | **down** (no listeners) |
| Equal Shares owner PID 16900 | **DEAD** (stale JSON from 2026-08-10) |
| batch / image-render owners | `pid: 0` released |
| `chat_busy.json` | **absent** |
| Equal Shares pass | still paused (AGENTS.md) |
| D: | mounted, Disk **2**, Seagate Portable, UniqueId **`3E543346485A464B`**, exFAT, ~1198 GB free |

Preflight **passed**. No GPU job, no Comfy start, Equal Shares tree read-only.

## What ran

1. Wrote local-only `ARCHIVE_DECISION.md` with the five operator fields.
   Handoff tree has **no `.git`**; added `.gitignore` listing
   `ARCHIVE_DECISION.md` so it stays out if git is ever inited.
2. Installed **Restic 0.19.1** (`winget install restic.restic`) from the
   official GitHub zip. Binary:
   `AppData\Local\Microsoft\WinGet\Packages\restic.restic_Microsoft.Winget.Source_8wekyb3d8bbwe\restic_0.19.1_windows_amd64.exe`
3. Created dedicated empty folder **`D:\restic-local-agent-evidence`**
   (not `D:\Backups`).
4. `restic init --repo D:\restic-local-agent-evidence` **succeeded**
   (config + `keys/` present, **0 snapshots**). Password went to restic’s
   prompt only.

## What did not run

Backup, restore drill, and SHA-256 compare. A `cmd.exe` helper was left
sitting on `pause` after init; that console had **MainWindowHandle = 0**
and was not usable from this agent session. Killing it did **not** delete
the repo. No `prune`/`forget`.

## Stop for the operator

Leave **D: plugged in**. In a **visible** Windows Terminal / cmd you can
type into, using the password from init:

```bat
set RESTIC=%LOCALAPPDATA%\Microsoft\WinGet\Packages\restic.restic_Microsoft.Winget.Source_8wekyb3d8bbwe\restic_0.19.1_windows_amd64.exe
set REPO=D:\restic-local-agent-evidence
set ROOT=A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
"%RESTIC%" backup --repo "%REPO%" --exclude-caches -- "%ROOT%\outputs\equal_shares" "%ROOT%\outputs\stories" "%ROOT%\docs\GOLDEN_REFERENCE" "A:\Users\rhine\Desktop\EQUAL_SHARES_FIRST_APPEARANCE" "A:\Users\rhine\Desktop\EQUAL_SHARES_GENERATION_LIST" "A:\Users\rhine\Desktop\EQUAL_SHARES_VOICE_AUDITIONS"
mkdir %TEMP%\restic-restore-drill
"%RESTIC%" restore latest --repo "%REPO%" --target "%TEMP%\restic-restore-drill" --include "*GOLDEN_REFERENCE*" --include "*audio_pass_manifest.json"
```

Then compare SHA-256 of the four `docs\GOLDEN_REFERENCE\` files and
`outputs\equal_shares\audio_pass_manifest.json` against the copies under
`%TEMP%\restic-restore-drill`. If they match: **unplug D: and store it
elsewhere.** Do not `forget`/`prune`.

## Files

- `ARCHIVE_DECISION.md` (local-only)
- `.gitignore`
- `TODO.md`
