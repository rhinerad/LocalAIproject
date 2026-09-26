# PR 3b — pyjnius SAF spike (not the companion)

Isolated python-for-android app `local.equalshares.safspike`. It exists to
answer: can pyjnius launch `ACTION_OPEN_DOCUMENT_TREE` and call
`takePersistableUriPermission` (read-only) under the same p4a pin as the
Sideband overlay?

This is **not** a daily-driver APK. Do **not** `adb install` it to the
operator Pixel. The refuse-by-default ledger in `adb_install.py` remains
the only install path for the real companion, and this package id is not
that companion.

## What a live run would prove

On a grantable tree (`Documents/…`, not Download / volume root):

1. Tap **Grant a folder**.
2. System picker; `RESULT_OK` → `takePersistableUriPermission` with READ.
3. Force-stop / restart the process.
4. `on_start` dumps `ContentResolver.getPersistedUriPermissions()`.

Until that device run happens, persistence-across-restarts is **unverified**.
**2026-09-05di:** isolated debug APK compiled on WSL
(`safspike-0.0.1-arm64-v8a-debug.apk`, package `local.equalshares.safspike`).
Not installed on the Pixel. Persist-across-restarts still unverified.

## Build (WSL, ext4)

```bash
# from this directory, copied onto ext4 (not /mnt/a)
buildozer android debug
```

Uses overlay pins: `android.api=33`, `android.ndk=25b`,
`p4a.commit=1fc0269438c365e07ea456793c300e3e18773939`.
