#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BUILD = Path("/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/build/other_builds")
PY = str(BUILD / "python3/arm64-v8a__ndk_target_24/python3/android-build/python3")
SITE = str(BUILD / "hostpython3/desktop/hostpython3/native-build/root/usr/local/lib/python3.11/site-packages")
HOSTLIB = str(BUILD / "hostpython3/desktop/hostpython3/Lib")


def run(title: str, code: str, extra: dict | None = None) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = SITE
    if extra:
        env.update(extra)
    print(f"\n=== {title} ===")
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=env)
    print("rc", r.returncode)
    print((r.stdout + r.stderr)[-2500:])


run("sys.path", "import sys; print('\\n'.join(sys.path))")
run("distutils", "import distutils; print(distutils.__file__)")
run("build_meta full", "import setuptools.build_meta as m; print('ok', m.__file__)")
run(
    "build_meta SETUPTOOLS_USE_DISTUTILS=stdlib",
    "import setuptools.build_meta as m; print('ok', m.__file__)",
    {"SETUPTOOLS_USE_DISTUTILS": "stdlib"},
)
run(
    "path with Lib",
    "import setuptools.build_meta as m; print('ok', m.__file__)",
    extra=None,
)
# PYTHONPATH site+Lib
print("\n=== PYTHONPATH site+Lib ===")
env = os.environ.copy()
env["PYTHONPATH"] = SITE + ":" + HOSTLIB
r = subprocess.run(
    [PY, "-c", "import setuptools.build_meta as m; import setuptools; print('ok', setuptools.__version__, m.__file__)"],
    capture_output=True, text=True, env=env,
)
print("rc", r.returncode)
print((r.stdout + r.stderr)[-2500:])
