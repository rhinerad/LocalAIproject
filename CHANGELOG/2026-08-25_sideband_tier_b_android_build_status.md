# 2026-08-25 — Sideband Tier B Android build status

## What was attempted

The opt-in forked-Sideband Android debug build was resumed in its isolated WSL
toolchain. This work is limited to the companion-phone package; it did not
start ComfyUI, a render, a desktop model, or the Equal Shares pipeline.

## Progress

- The original host-Python recipe lacked the pip helper expected by the pinned
  python-for-android version. The staged build-only recipe was repaired with
  the upstream-compatible `pip`/`fix_pip_shebangs` helpers.
- NumPy then progressed through the dependency collection and into its Android
  recipe, proving the first repair was effective.

## Current blocker

The pinned python-for-android NumPy recipe selects the modern Meson build path.
Its isolated build environment still cannot import `mesonpy`, even after the
host environment has the package. No APK was produced.

This is a packaging compatibility issue, not a runtime or transport failure.
Do not claim Tier B is installable until a signed/debug APK exists and is
installed on a device. Tier A remains the working, paired LXMF path.

## Attempts recorded

- Confirmed `sideband/audioproc.py` imports NumPy, so NumPy cannot be removed
  from the package requirements.
- Added a staged NumPy-recipe overlay that exposes the host recipe's
  site-packages path in both host and compile environments.
- The overlay was loaded by the build, but the isolated PEP 517 environment
  still failed to import `mesonpy`. Repeating that same build will not provide
  new evidence.

## Next safe action

Make a versioned local NumPy recipe compatible with the pinned
python-for-android/Android-NDK combination, or move the build to a Sideband
source/toolchain revision whose NumPy recipe is known to work. Preserve the
current cache and do not reset the desktop agent or media pipeline.
