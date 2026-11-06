# 2026-09-05bp — ADB wrapper refuse-by-default (companion PR 2)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05bp**.

**PR 0:** operator accepted A1–A14 (and K1–K10) in
`docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md`.

**PR 1:** workstation APK review CLI (`2026-09-05bf`).

**PR 2:** ADB install wrapper against `adb_trusted_devices.json`. Does **not**
compile an APK, does not run live `adb install` in CI, does not edit
`buildozer.spec` or production `agent.py`.

## What shipped

`local_agent/adb_install.py` plus thin `local_agent/INSTALL_COMPANION_APK.ps1`
(calls the Python; sits next to `APPLY_SIDEBAND_PHONE_FIREWALL.ps1`):

- Ledger: `local_agent/runtime/lxmf/adb_trusted_devices.json` (`version: 1`)
- Exit **2** unless **all** of: serial row present, `approved_at` set,
  `revoked_at` null, APK SHA-256 matches `approved_apk_sha256`,
  `adb devices` is exactly one `device` matching that serial,
  `getprop ro.build.fingerprint` matches the row exactly
- Hash immediately before `adb install -r`; missing ledger / empty devices /
  unauthorized / multiple devices / fingerprint mismatch → refuse, no install
- JSONL `runtime/lxmf/adb_install.jsonl`: timestamp, serial, sha256, outcome —
  not the APK body
- `--dry-run` verifies and stops before `adb install`
- Not imported by `lxmf_agent.py`; not in the Android tree

```text
python local_agent/adb_install.py path/to.apk --serial SERIAL
python local_agent/adb_install.py path/to.apk --serial SERIAL --dry-run
```

## Tests

```text
python -m unittest test_adb_install -q
```

20/20 OK. Fake `adb` runner only. Matching rows use `--dry-run` or a fake
`install` that never shells the real daemon. `test_apk_review` still 9/9.

## Files

- `local_agent/adb_install.py` (new)
- `local_agent/test_adb_install.py` (new)
- `local_agent/INSTALL_COMPANION_APK.ps1` (new, thin)
- `docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md` (status)
- `TODO.md`

## Scope

No Android compile (PR 3b / A13). No `buildozer.spec` edit (PR 3). No live
`adb install`. APP_REVISION unchanged. No `outputs/equal_shares/`.

Next per plan: **PR 3** — delete `MANAGE_EXTERNAL_STORAGE` from
`vendor_sideband/sbapp/buildozer.spec` and extend `test_sideband_tier_b.py`
static greps. Still no compile.
