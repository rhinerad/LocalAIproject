# 2026-09-05bs — Status sync: archive decision menu ready, ADB wrapper shipped

## Scope

Operator-facing tracking entry. No new production work from this entry.

## Archive decision prep (Purple)

Real measurements taken on this actual machine today, not generic
advice: no Restic installed, no USB attached, no NAS mapped, A: has
~11TB free / C: has ~788GB free. Correctly identified that a folder on
A: (the same drive the source files live on) doesn't count as a real
second copy — drive/enclosure death takes both. Real destination pairs
that would count: USB (kept offline) + C:, USB (stored elsewhere) +
cloud, or C: + cloud. Recovery-secret custody options laid out with what
each does and doesn't protect against; runbook's own minimum is a
password manager plus an offline copy, restored from a device that
isn't this PC. Source-root scoping gives a concrete ~6-7GB first-pass
estimate (Equal Shares + selected Shared evidence, not models), with a
narrow proposed first restore drill (golden graphs + good audio + one
manifest) rather than hashing gigabytes on the first test. Execution
window preflight reuses the existing thermal/render-owner checks rather
than inventing new ones.

This is a real decision menu, not a recommendation — Purple correctly
did not pick for the operator. Nothing was archived, no key was
created. The runbook's own gate holds: an untracked `ARCHIVE_DECISION.md`
with five picked fields is required before Restic gets installed.

## Android companion PR 2 shipped (Orange)

`local_agent/adb_install.py` — refuse-by-default against
`adb_trusted_devices.json`. Requires **all four** of serial, exact
`ro.build.fingerprint`, freshly-hashed APK SHA-256, and an unrevoked
explicit approval row to match before installing — refuses on missing/
empty ledger, unauthorized device, multiple device rows, or any single
mismatch. Also requires `adb devices` to show exactly one device
matching the target serial (protects against installing to the wrong
phone if multiple are connected). JSONL audit log records outcome/hash/
serial, never APK bytes. 20/20 new tests plus the original 9/9
`apk_review` tests still passing (no regression). All testing used a
fake adb runner — no real daemon was shelled, no real install happened.
PR 3 (delete `MANAGE_EXTERNAL_STORAGE` from the buildozer spec + extend
static greps) is next per the plan; still no Android compile.

## Status

Waiting on the operator's actual archive decision (destination pair +
custody approach) before Purple can proceed further. Orange continues
to PR 3.
