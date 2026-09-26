# 2026-09-05bj — Sealed-export v1 helper (synthetic only)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bj**.

E1–E8 accepted per `docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md`.
Does **not** authorize a real historical export. `chats/` stays unread.
`submit_distillation` without `--sample` stays unauthorized.

## What changed

- New `local_agent/sealed_export.py`: encrypts
  `submit_distillation.SAMPLE` (the distill `--sample` fixture) to an age
  X25519 recipient. Ciphertext only, opaque `sealed_export_<12 hex>.age`.
  No `plaintext_sha256` sidecar. No `NamedTemporaryFile`.
- `assert_not_chat_source()` hard-refuses any path under
  `local_agent/chats/` before a read. `seal_from_path` / `--source` hit
  that lock, then still refuse v1 non-synthetic sealing.
- `atomic_write_bytes` for the ciphertext file (sibling `.tmp` is
  ciphertext, same pattern as farm envelopes).
- Workstation CLI has no decrypt command. Tests round-trip with
  `decrypt_age_for_tests`.

## Tests

From `local_agent/`:

```text
python -m unittest test_sealed_export -q
```

7/7 OK.

- Synthetic fixture matches `submit_distillation.SAMPLE` and decrypts.
- `local_agent/chats/must_not_be_read.json` raises
  `refused: path is under local_agent/chats/` and the file is not created.
- Live filesystem probe of dest + isolated process temp during
  `seal_synthetic`: zero files contained the plaintext canary.
- Grep lock: helper has no `NamedTemporaryFile` / `store.load` /
  `plaintext_sha256`; a deliberate bad copy is detected.

## Files

- `local_agent/sealed_export.py` (new)
- `local_agent/test_sealed_export.py` (new)
- `local_agent/atomic_io.py` (`atomic_write_bytes`)
- `TODO.md`
- `docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md` (status)

## Scope

No real `chats/` export. No farm `EncryptedArtifactStore` change. No
`age.exe` install. No `APP_REVISION`. GUI not started.
