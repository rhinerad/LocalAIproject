# 2026-08-29 — Source backup snapshot policy

## What changed

- Added `work/New-LocalAgentSourceBackup.ps1`, a repeatable ZIP builder for
  source code and documentation. It safely skips unreadable filesystem entries
  instead of failing or attempting to alter them, and records the skipped count
  in its archive manifest. The first local dry run identified bundled Sideband,
  ADB, and generated-index binaries as out of scope; the builder now excludes
  those third-party/generated trees and nested ZIPs as intended.
- Added `docs/SOURCE_BACKUP_POLICY.md` and a tracked backup-hygiene section in
  `TODO.md`.

## Safety boundary

The backup excludes `.env`, paired identities, runtime stores/uploads,
virtual environments, model weights, media, generated outputs, logs, artifacts,
and archive evidence. It writes a scope manifest and SHA-256 so a cloud copy can
be checked. This protects source continuity without moving private runtime data
or pretending the ZIP is a complete evidence/media archive.

## Deliberate non-changes

- No source file, model, render, queue, ComfyUI process, or local-agent service
  was altered or started.
- No raw media/evidence/runtime archive was copied by this backup workflow.
