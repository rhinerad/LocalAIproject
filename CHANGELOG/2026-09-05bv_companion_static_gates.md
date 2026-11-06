# 2026-09-05bv — Companion static permission gate (PR 3, no compile)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05bv**.

**PR 0–2** already landed (sign-off, `apk_review.py`, `adb_install.py`).

**PR 3:** source-only permission gate. Does **not** compile an APK, does not
download Buildozer/SDK/NDK, does not run the PR 3b pyjnius spike (that remains
**gated on A13**).

## What shipped

- Deleted `MANAGE_EXTERNAL_STORAGE` from
  `local_agent/vendor_sideband/sbapp/buildozer.spec` `android.permissions`.
- Extended `local_agent/test_sideband_tier_b.py` to walk overlay sources
  (`.py` / `.spec` / `.xml` / `.java` / `.kt` / `.gradle`) and fail if any of
  these tokens appear:
  - `MANAGE_EXTERNAL_STORAGE` (all-files)
  - `pm install` / `installPackage`
  - `REQUEST_INSTALL_PACKAGES` (forbidden until PR 6)
  - privileged `INSTALL_PACKAGES` and `BIND_DEVICE_ADMIN`
- Package-id coexistence test unchanged (`local.equalshares.sidebandagent`).

## Tests

```text
python -m unittest test_sideband_tier_b -q
```

6/6 OK. No Android toolchain invoked.

## Files

- `local_agent/vendor_sideband/sbapp/buildozer.spec`
- `local_agent/test_sideband_tier_b.py`
- `docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md`
- `TODO.md`

## Scope / next

**PR 3b is not authorized.** A13 (toolchain download) has not been given.
Do not run Buildozer, do not probe pyjnius SAF, do not produce an APK.
APP_REVISION unchanged. No `outputs/equal_shares/`.
