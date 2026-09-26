#!/usr/bin/env python3
"""Native-build hostpython vs android-build copy: which can import math/setuptools."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BUILD = Path("/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/build/other_builds")
HOST = str(BUILD / "hostpython3/desktop/hostpython3/native-build/python3")
COPY = str(BUILD / "python3/arm64-v8a__ndk_target_24/python3/android-build/python3")
SITE = str(BUILD / "hostpython3/desktop/hostpython3/native-build/root/usr/local/lib/python3.11/site-packages")
code = (
    "import math, sys; import setuptools.build_meta as m; "
    "print('math', math); print('exe', sys.executable); "
    "print('setuptools', m.__file__)"
)
env = os.environ.copy()
env["PYTHONPATH"] = SITE
for label, exe in (("native-build hostpython", HOST), ("android-build copy", COPY)):
    print(f"\n=== {label} ===")
    r = subprocess.run([exe, "-c", code], capture_output=True, text=True, env=env)
    print("rc", r.returncode)
    print((r.stdout + r.stderr)[-1500:])
