# 2026-09-05ct — Companion PR 3b pyjnius SAF spike (incomplete)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05ct**.

**A13 authorized** this session: Buildozer may download SDK/NDK. PR 0–3 already
shipped. This entry is PR 3b. **Do not call PR 3b done.**

## What shipped (source)

Isolated probe app `local.equalshares.safspike` (not the companion package):

- `local_agent/saf_pyjnius_spike/main.py` — `ACTION_OPEN_DOCUMENT_TREE`,
  read-only `takePersistableUriPermission`, dump of
  `getPersistedUriPermissions()` on start
- `local_agent/saf_pyjnius_spike/buildozer.spec` — api 33, ndk 25b, p4a
  `1fc0269438c365e07ea456793c300e3e18773939`, overlay `p4a.local_recipes`
- `local_agent/test_saf_pyjnius_spike.py`
- overlay `vendor_sideband/recipes/pyjnius/__init__.py`:
  `extra_build_args = ['--no-isolation']` (p4a isolated `python -m build`
  cannot import `setuptools.build_meta` on this hostpython)

No Pixel sideload. `adb devices` was empty. `adb_install.py` was not invoked.
APP_REVISION unchanged. No `outputs/equal_shares/`.

## Toolchain (WSL Ubuntu 24.04, `/root`)

Already on disk from 2026-08-25 (Buildozer did not re-download SDK/NDK):

| Piece | Version | Size |
|---|---|---|
| Android SDK | cmdline-tools 2.0; platform android-33 (API 33 / Android 13 rev 3); build-tools 37.0.0; platform-tools 37.0.1 | 457 MiB (`457347725` bytes) |
| NDK r25b | `Pkg.Revision = 25.1.8937393` | extract 2.75 GiB (`2949282436`); zip `android-ndk-r25b-linux.zip` 506 MiB (`530975885`) |
| Apache Ant | 1.9.4 | 41 MiB |
| `~/.buildozer` total | | 2.7 GiB |
| Buildozer | 1.5.0 (`/opt/sideband-build-venv`) | |
| Host Cython | 0.29.37 | |
| OpenJDK | 21.0.12+8-1-24.04 (jre was present; **jdk-headless pulled this session**) | |

Pulled this session:

- `openjdk-21-jdk-headless` 21.0.12+8-1~24.04 — **82.8 MB** archive (~98 MB installed with ccache)
- `ccache` 4.9.1-1 — 592 kB
- `libhiredis1.1.0` — 41.4 kB
- python-for-android git `1fc02694` + CPython 3.11.5 host/target trees, SDL2, kivy, pyjnius sources under `/root/saf-pyjnius-spike/.buildozer` — **1.9 GiB** (no APK in `bin/`)

p4a at this pin **recommends NDK 28c**; the overlay pin is still r25b.

## What the spike proved / did not prove

**Proved (host):** pyjnius source sequence is present; overlay + spike specs still
omit all-files / silent-install tokens; target CPython **3.11.5** and SDL2
`libmain.so` **did** link (`-lpython3.11`) after using overlay recipes (plain
p4a python 3.14.2 failed on NDK r25b: `python_shared` undefined,
`-print-multi-os-directory`).

**Did not prove:** persistable SAF grants across process restarts. There is
**no APK**. Buildozer `android debug` dies while building pyjnius 1.7.0:

```
python3 -m build --wheel
BackendUnavailable: Cannot import 'setuptools.build_meta'
```

isolated venv (`venv+pip`). `git reset --hard 1fc02694` on every Buildozer
run also wipes in-tree p4a `recipe.py` patches. No device run was possible
without an APK, and this task forbade Pixel install anyway.

Open question 6 (GET_CONTENT-only v1 if persistable trees are infeasible)
stays **open** — compile infeasibility is not the same as an on-device SAF
refusal, but PR 4 must not assume the spike passed.

## Tests

```text
python -m unittest test_sideband_tier_b test_saf_pyjnius_spike -q
```

**10/10 OK** (`test_sideband_tier_b` **6/6**). No APK, so no generated
companion manifest to re-grep; spike + overlay sources still clean.

## Files

- `local_agent/saf_pyjnius_spike/` (new)
- `local_agent/test_saf_pyjnius_spike.py` (new)
- `local_agent/vendor_sideband/recipes/pyjnius/__init__.py` (`--no-isolation`)
- `docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md` (status)
- `TODO.md`
