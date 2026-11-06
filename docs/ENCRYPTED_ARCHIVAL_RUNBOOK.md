# Encrypted archival runbook — raw media, evidence, and large artifacts

## Decision and status

The normal source backup ZIP is intentionally **not** an evidence archive. The
approved design for large/private material is a versioned, client-side encrypted
`restic` repository. No archive has been created, moved, deleted, uploaded, or
scheduled by this runbook. A first execution needs an operator-chosen destination
and an operator-managed recovery secret.

Restic is the selected archive format because it encrypts and authenticates all
repository data before storage. Its published design uses AES-256 encryption and
Poly1305-AES authentication. See the [official design documentation](https://github.com/restic/restic/blob/master/doc/design.rst).

## Scope

Include only after an explicit review of the selected roots:

- original and approved raw media;
- final renders and embedded-prompt evidence;
- immutable manifests, checksums, and review artifacts;
- large local-agent encrypted artifacts where retention is required;
- model conversion profiles, activation logs, and accepted validation manifests.

Never include by default:

- live `.env` files, API keys, password files, phone identity keys, Redis
  credentials, or unreviewed authentication tokens;
- transient model caches, virtual environments, Docker layers, or replaceable
  build outputs;
- the source-and-documentation ZIP itself (it remains a separate backup class).

## Destination and key-management gate

Before the first archive, record in a local-only `ARCHIVE_DECISION.md` (never
commit it):

1. the primary destination — a dedicated external encrypted drive **or** a
   private cloud/object-store repository;
2. a separate second destination or offline copy;
3. the exact approved source roots and exclusions;
4. the recovery-secret custody plan: a long unique repository password held in
   a password manager plus an offline recovery copy controlled by the operator;
5. the restore contact/device and a scheduled restore-test date.

Do not place the password in a command line, source file, chat transcript, or
the repository. Use a user-readable password prompt for manual runs, or an
operator-created password file stored outside the repository with restrictive
permissions for an approved scheduled task.

## First archive procedure — operator-run only

1. Install a current Restic release from its official project only after the
   operator approves the download.
2. Create an empty archive destination; do not reuse an unrelated backup.
3. Generate and review a dry-run manifest containing only labels, relative
   paths, byte counts, modification times, and SHA-256 values. Keep that
   manifest inside the encrypted repository or an encrypted local vault.
4. Initialize the repository and make the first backup with source roots passed
   explicitly. Never use a broad drive root or an unreviewed wildcard.
5. Run repository integrity verification after the backup and restore a small,
   non-sensitive file to a fresh temporary directory. Compare its SHA-256 to
   the manifest.
6. Record snapshot ID, source-root labels, byte count, verification time, and
   restore-test result in a local encrypted archive log.

## Retention and maintenance

- Keep daily snapshots for 14 days, weekly snapshots for 8 weeks, and monthly
  snapshots for 12 months until the operator approves a different policy.
- Do not run pruning, `forget`, deletion, key rotation, or repository repair
  automatically. Each can make recovery harder when evidence is involved.
- Perform a read-only integrity check monthly and a real small-file restore
  test quarterly.
- Review capacity before every large media archive; lack of space is a stop
  condition, never permission to delete evidence.
- On a source-file checksum mismatch, quarantine the archive attempt and
  record the mismatch; do not overwrite either copy.

## Recovery drill acceptance

The archival system is accepted only when all are true:

- the repository rejects an incorrect password or altered data;
- a sample restore matches its recorded SHA-256;
- the operator can locate the recovery secret without relying on this
  workstation alone;
- the second destination is independently reachable; and
- no secrets or raw media names were written to the public source repository.

## Explicit non-goals

This runbook does not upload data to Google Drive, start a backup, encrypt an
existing folder in place, delete a source, or change Equal Shares evidence. It
also does not replace the worker-farm AES-256-GCM artifact store.
