#!/usr/bin/env python3
"""Install a single Cython 0.29.37 into hostpython destroot (Kivy 2.3.0)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SITE = Path(
    "/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/"
    "build/other_builds/hostpython3/desktop/hostpython3/native-build/"
    "root/usr/local/lib/python3.11/site-packages"
)
HOST_PY = Path(
    "/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/"
    "build/other_builds/hostpython3/desktop/hostpython3/native-build/python3"
)


def main() -> int:
    if not SITE.is_dir() or not HOST_PY.is_file():
        print("hostpython destroot missing; skip")
        return 0
    for path in list(SITE.iterdir()):
        name = path.name.lower()
        if name in {"cython", "cython.py"} or name.startswith("cython-"):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print("removed", path.name)
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(SITE)
    cmd = [
        str(HOST_PY), "-m", "pip", "install",
        "Cython==0.29.37", "wheel", "setuptools",
        "--target", str(SITE), "--upgrade", "--force-reinstall",
        "--only-binary=:all:",
    ]
    print("run", cmd)
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    sys.exit(main())
