# 2026-09-05di — Companion PR 3b spike APK (compile only; persist unverified)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05di**.

Follows `2026-09-05ct` (pyjnius `setuptools.build_meta` failure). **NDK 28c was not
required.** Companion `buildozer.spec` still pins **NDK r25b**. No Pixel install.

## Root cause (not isolation flags)

p4a `PyProjectRecipe.build_arch` **copies hostpython into
`python3/android-build/python3`**, then runs `python -m build` with that copy.

That x86-64 binary then searches the **aarch64** target module dir, so
`import math` fails. `setuptools.build_meta` never loads; the isolated venv
error is a symptom. Diagnosed:

- `android-build/python3` + `PYTHONPATH=destroot`: `No module named 'math'`
- `native-build/python3` + same `PYTHONPATH`: `import setuptools.build_meta` **OK**

`--no-isolation` on the overlay recipe did nothing until the interpreter was
the native-build hostpython. Then `--no-isolation` needed **`wheel`** installed
in destroot, and Kivy 2.3.0 needed **Cython==0.29.37** (not 3.1.8).

## What shipped

- Overlay `vendor_sideband/recipes/pyjnius/__init__.py`: run `python -m build`
  via `real_hostpython_location`; install `wheel`; pin `Cython==0.29.37`
- Spike `p4a.source_dir` (injected into **[app]**) to a patched p4a tree so
  the `android` / `kivy` recipes use the same interpreter (git reset no longer
  wipes it)
- Isolated debug APK (WSL, not in git):
  `/root/saf-pyjnius-spike/bin/safspike-0.0.1-arm64-v8a-debug.apk`
  - package `local.equalshares.safspike` (not the companion)
  - 19 963 842 bytes
  - SHA-256 `4ed173b9a23ef08421ab0f5772f3b87ff7a246ff9b416e7386b473893c74e6cc`
  - native libs all `lib/arm64-v8a/`
  - dist manifest has **no** all-files / install / device-admin permissions

`adb devices` was empty. `adb_install.py` not invoked.

## Not proven

Persistable SAF grants **across process restarts**. That still needs an
operator-run on a grantable `Documents/…` tree. Open question 6 stays open
until that run.

## Tests

```text
python -m unittest test_sideband_tier_b test_saf_pyjnius_spike -q
```

**10/10 OK** (`test_sideband_tier_b` **6/6**). APP_REVISION unchanged. No
`outputs/equal_shares/`. Companion NDK pin unchanged.
