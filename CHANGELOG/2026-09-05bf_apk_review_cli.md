# 2026-09-05bf — Workstation APK review CLI (companion PR 1)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05bf**.

**PR 0:** operator accepted A1–A14 (and K1–K10 recommended defaults) in
`docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md`.

**PR 1:** workstation APK review CLI. Does **not** compile an APK, does
not `adb install`, does not send rows to the phone, does not edit
production `agent.py`.

## What shipped

`local_agent/apk_review.py` (stdlib: `zipfile` / `hashlib` / `struct`):

- SHA-256 of the whole file
- APK Signature Scheme v2/v3 first-cert SHA-256 + best-effort CN
- Binary `AndroidManifest.xml` → package id, version, `uses-permission` list
- **Fail closed** (`decision=reject`, exit 1): `MANAGE_EXTERNAL_STORAGE`,
  privileged `INSTALL_PACKAGES`, `BIND_DEVICE_ADMIN` /
  `DEVICE_ADMIN_ENABLED`, `QUERY_ALL_PACKAGES`, unsigned, missing/unparsed
  manifest, package id ≠ `local.equalshares.sidebandagent`
- **Flag** (`decision=flag`, exit 2): `REQUEST_INSTALL_PACKAGES` (PR 6 only)
- **Accept** (exit 0) otherwise
- Appends one row to `runtime/lxmf/apk_review.jsonl` (no APK bytes)

```text
python local_agent/apk_review.py path/to.apk
python local_agent/apk_review.py path/to.apk --no-jsonl
```

## Tests

```text
python -m unittest test_apk_review -q
```

9/9 OK. Synthetic APKs only (encoded AXML + inserted v2 block). No SDK.

## Files

- `local_agent/apk_review.py` (new)
- `local_agent/test_apk_review.py` (new)
- `docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md` (PR 0 status)
- `TODO.md`

## Scope

No Android compile. No ADB wrapper (PR 2). No `buildozer.spec` edit (PR 3).
No production-agent edit. APP_REVISION unchanged. No `outputs/equal_shares/`.
