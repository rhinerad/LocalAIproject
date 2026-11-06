#!/usr/bin/env python3
"""Diagnose why setuptools.build_meta is unavailable in the pyjnius build Python."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORK = Path("/root/saf-pyjnius-spike")
BUILD = WORK / ".buildozer/android/platform/build-arm64-v8a/build/other_builds"
ANDROID_PY = BUILD / "python3/arm64-v8a__ndk_target_24/python3/android-build/python3"
HOST_PY = BUILD / "hostpython3/desktop/hostpython3/native-build/python3"
HOST_SITE = BUILD / "hostpython3/desktop/hostpython3/native-build/root/usr/local/lib/python3.11/site-packages"
P4A_RECIPE = WORK / ".buildozer/android/platform/python-for-android/pythonforandroid/recipe.py"


def probe(label: str, exe: Path) -> None:
    print(f"\n=== {label} ===")
    print("exists", exe.exists(), "path", exe)
    if not exe.exists():
        return
    print("is_symlink", exe.is_symlink())
    if exe.is_symlink():
        print("target", exe.resolve())
    try:
        out = subprocess.check_output(["file", str(exe)], text=True, stderr=subprocess.STDOUT)
        print("file", out.strip())
    except Exception as exc:
        print("file-err", exc)
    code = r"""
import sys, os
print('executable', sys.executable)
print('prefix', sys.prefix)
print('exec_prefix', sys.exec_prefix)
print('version', sys.version.replace('\n',' '))
print('platform', sys.platform)
print('path0', sys.path[0] if sys.path else None)
print('path_site', [p for p in sys.path if 'site-packages' in p])
for name in ('setuptools', 'setuptools.build_meta', 'wheel', 'build', 'Cython'):
    try:
        mod = __import__(name)
        print('OK', name, getattr(mod, '__file__', None), getattr(mod, '__version__', '?'))
    except Exception as e:
        print('FAIL', name, type(e).__name__, e)
"""
    try:
        r = subprocess.run([str(exe), "-c", code], capture_output=True, text=True, timeout=30)
        print("rc", r.returncode)
        sys.stdout.write(r.stdout)
        if r.stderr:
            print("stderr", r.stderr[:2000])
    except Exception as exc:
        print("run-err", exc)


def main() -> None:
    print("cwd", os.getcwd())
    probe("android-build/python3 (what p4a RAN)", ANDROID_PY)
    probe("hostpython3 native-build/python3", HOST_PY)
    print("\n=== host site-packages listing (setuptools*) ===")
    if HOST_SITE.is_dir():
        for p in sorted(HOST_SITE.iterdir()):
            if "setuptools" in p.name.lower() or p.name in {"wheel", "build"}:
                print(p.name)
        st = HOST_SITE / "setuptools"
        print("setuptools dir exists", st.is_dir())
        meta = HOST_SITE / "setuptools" / "build_meta.py"
        print("build_meta.py", meta.exists(), meta)
    else:
        print("missing", HOST_SITE)
    print("\n=== p4a extra_build_args ===")
    if P4A_RECIPE.is_file():
        for i, line in enumerate(P4A_RECIPE.read_text(encoding="utf-8").splitlines(), 1):
            if "extra_build_args" in line:
                print(f"{i}:{line}")
    recipes = WORK / "recipes/pyjnius/__init__.py"
    print("\n=== local pyjnius recipe extra_build_args ===")
    if recipes.is_file():
        for i, line in enumerate(recipes.read_text(encoding="utf-8").splitlines(), 1):
            if "extra_build_args" in line or "isolation" in line:
                print(f"{i}:{line}")


if __name__ == "__main__":
    main()
