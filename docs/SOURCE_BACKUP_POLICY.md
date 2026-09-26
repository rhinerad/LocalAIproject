# Source backup policy

`work/New-LocalAgentSourceBackup.ps1` creates a portable ZIP for cloud backup.
It includes source code and documentation, plus a `BACKUP_SCOPE.txt` manifest.

It deliberately excludes credentials, `.env`, paired identities, runtime state,
uploads, feedback/exemplar stores, virtual environments, models, media,
generated outputs, artifacts, logs, archival evidence, generated indexes, and
vendored third-party desktop/mobile binaries. The ZIP is therefore
safe for normal source-code backup but is **not** a complete project/evidence or
media backup.

Run it from the canonical repository root:

```powershell
.\work\New-LocalAgentSourceBackup.ps1
```

Verify the printed SHA-256 before uploading or restoring. Keep cloud backup
access private. A separate, explicit archival plan is required for raw media,
render evidence, and encrypted runtime artifacts.
