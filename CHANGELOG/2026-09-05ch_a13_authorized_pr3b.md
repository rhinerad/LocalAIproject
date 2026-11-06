# 2026-09-05ch — A13 authorized: Android toolchain download for PR 3b

## Scope

Operator tracking entry, dispatches PR 3b.

## Operator decision

Operator authorized **A13** — Buildozer may download the Android
SDK/NDK toolchain (sizeable one-time download) so the trusted Android
companion work can proceed to PR 3b, the pyjnius SAF
(`ACTION_OPEN_DOCUMENT_TREE` + persistable grants) compile spike.

Context: PR 0-3 already shipped (sign-off, `apk_review.py`,
`adb_install.py`, and the static permission-gate test extension in
`2026-09-05bv`/`bw`). No Android toolchain has been invoked at any point
so far. This authorization covers only the toolchain download and the
PR 3b spike itself — it does not authorize producing or installing a
real APK on a device (that remains a later, separately gated step per
the companion's own PR plan).

## Status

Dispatching Orange to run PR 3b now.
