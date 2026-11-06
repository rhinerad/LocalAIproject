# 2026-09-05bk — Encrypted archival decision prep (no archive, no key)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bk**.

Task #60. Primer-style menu for the runbook gate in
`docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md` / TODO.md Backup hygiene. Pattern:
`docs/SDXL_LORA_TRAINING_PRIMER.md`.

## What shipped

`docs/design_notes/ENCRYPTED_ARCHIVAL_DECISION_PREP_2026-09-05.md`.

Measured this session (no Restic, no password, no copy):

- Disks: C: Lexar NVMe ~788 GB free; A: 16 TB Toshiba “RAD Disk” ~11 TB
  free. Project/media live on A:.
- No USB attached, no mapped NAS, no `restic`/`rclone` on PATH.
- OneDrive running (~0.75 GB, Personal Vault.lnk); DriveFS absent.
- No local 1Password/Bitwarden/KeePass path.
- GPU idle: 52 °C, 0 %, 59 MiB; 8188 down; Equal Shares owner PID 16900
  dead; farm `celery@Louises-MBP` ok.
- Candidate sizes: `outputs/equal_shares` 3.36 GB;
  `ComfyUI-Shared\output` 2.93 GB (`good audio` 0.01 GB / 16 files);
  Desktop Equal Shares packs 0.16 GB.

The note lays out destination pairs, custody approaches, include/exclude
roots, and a thermal/GPU/farm window. It does not pick any of them.

## What was not done

No `restic init`, no key, no `ARCHIVE_DECISION.md` in git, no media
moved, Equal Shares untouched.

## Files

- `docs/design_notes/ENCRYPTED_ARCHIVAL_DECISION_PREP_2026-09-05.md`
- `TODO.md`
