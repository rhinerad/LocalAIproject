#!/usr/bin/env python3
"""Confirm PYTHONPATH destroot vs prefix /usr/local is the build_meta root cause."""
from __future__ import annotations

import subprocess
from pathlib import Path

BUILD = Path("/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/build/other_builds")
PY = BUILD / "python3/arm64-v8a__ndk_target_24/python3/android-build/python3"
SITE = BUILD / "hostpython3/desktop/hostpython3/native-build/root/usr/local/lib/python3.11/site-packages"
code = "import setuptools.build_meta as m; import setuptools; print('ok', setuptools.__file__, m.__file__)"


def run(env: dict | None) -> None:
    print("env", {k: env[k] for k in env or {} if k.startswith("PYTHON")})
    r = subprocess.run([str(PY), "-c", code], capture_output=True, text=True, env=env)
    print("rc", r.returncode)
    print((r.stdout or r.stderr)[:1500])


def main() -> None:
    import os
    base = os.environ.copy()
    print("=== no PYTHONPATH ===")
    run(base)
    print("=== PYTHONPATH=destroot site-packages ===")
    env = base.copy()
    env["PYTHONPATH"] = str(SITE)
    run(env)
    print("=== --no-isolation import path used by python -m build ===")
    r = subprocess.run(
        [str(PY), "-m", "build", "--help"],
        capture_output=True, text=True, env=env,
    )
    print("build --help rc", r.returncode, (r.stdout or r.stderr).splitlines()[:3])


if __name__ == "__main__":
    main()
