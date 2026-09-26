#!/usr/bin/env python3
"""Record Buildozer/SDK/NDK paths, versions, and sizes (PR 3b)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
PLATFORM = HOME / ".buildozer" / "android" / "platform"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _du(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def snapshot() -> dict:
    ndk = PLATFORM / "android-ndk-r25b"
    sdk = PLATFORM / "android-sdk"
    row = {
        "at": time.time(),
        "home": str(HOME),
        "platform": str(PLATFORM),
        "exists": {
            "platform": PLATFORM.is_dir(),
            "sdk": sdk.is_dir(),
            "ndk": ndk.is_dir(),
        },
        "versions": {
            "cmdline_tools": _read(sdk / "cmdline-tools" / "latest" / "source.properties")
            or _read(sdk / "tools" / "source.properties"),
            "build_tools_37": _read(sdk / "build-tools" / "37.0.0" / "source.properties"),
            "platform_33": _read(sdk / "platforms" / "android-33" / "source.properties"),
            "platform_tools": _read(sdk / "platform-tools" / "source.properties"),
            "ndk_r25b": _read(ndk / "source.properties"),
        },
        "bytes": {
            "dot_buildozer": _du(HOME / ".buildozer"),
            "sdk": _du(sdk),
            "ndk_r25b": _du(ndk),
            "ndk_zip": _du(PLATFORM / "android-ndk-r25b-linux.zip"),
            "apache_ant": _du(PLATFORM / "apache-ant-1.9.4"),
            "p4a": _du(PLATFORM / "python-for-android"),
        },
        "listing": sorted(p.name for p in PLATFORM.iterdir()) if PLATFORM.is_dir() else [],
    }
    return row


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
