# 2026-09-05az — Sealed historical-chat export: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05az**.

Design note only — no real export, no `chats/` read, no `age` install, no
`APP_REVISION`.

Doc: `docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md`.

## Finding

The operator bar (export unreadable even to local disk/admin) is **not**
met by anything already called encryption in this tree:

- Farm `EncryptedArtifactStore` is AES-256-GCM with
  `FARM_ENCRYPTION_KEY_B64` in `worker_farm/.env` (`farm_core.py`). The
  `distill_export` worker decrypts with that key on this machine.
- PowerInfer `vault.encrypt_private` wraps the key in DPAPI
  (`tools/powerinfer/vault.py`); admin can unwrap it.
- BitLocker / a key beside the file fail the same way.

The synthetic job `distill_5090ec5b50892412f0c1a04a` (`--sample` only)
still does not authorize private transcripts (`TODO.md`,
`RUN_PHASE1_SAMPLE.ps1`). `submit_distillation.py --sample` writes a
plaintext `NamedTemporaryFile` then unlinks it — acceptable for the
public fixture, forbidden for a real snapshot.

A sealed export is public-key (recommended: **age**) to a recipient whose
private key never lives on DuranGamingPC. Ciphertext only on disk; no
plaintext tempfile; opaque filename; no `plaintext_sha256` sidecar. Farm
distill cannot use this keying and still process text here.

This note does **not** authorize a real export. v1 of a synthetic-only
seal helper is optional after E1; reading `local_agent/chats/` stays
blocked on the existing source-selection TODO plus E8.

No production code changed.
