#!/usr/bin/env python3
"""Grep spike sources + generated manifests for PR 3 forbidden tokens.

Does not scan the SDK/NDK trees (AOSP sources contain those strings).
"""
from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN = (
    "MANAGE_EXTERNAL_STORAGE",
    "REQUEST_INSTALL_PACKAGES",
    "android.permission.INSTALL_PACKAGES",
    "BIND_DEVICE_ADMIN",
    "pm install",
    "installPackage",
)
HERE = Path(__file__).resolve().parent
SCAN_SUFFIXES = {".py", ".spec", ".xml", ".java", ".kt", ".kts", ".gradle"}


def scan(root: Path) -> list[str]:
    hits: list[str] = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(p in {".git", "android-sdk", "android-ndk-r25b",
                     "python-for-android"} and p.startswith("android-n")
               for p in path.parts):
            continue
        if "android-sdk" in path.parts or "android-ndk-r25b" in path.parts:
            continue
        if "python-for-android" in path.parts and path.suffix != ".xml":
            # p4a checkout is upstream; we only care about generated manifests
            if path.name != "AndroidManifest.xml":
                continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.as_posix()
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{rel}: {token}")
    return hits


def main() -> int:
    roots = [HERE]
    artifacts = HERE / "artifacts"
    if artifacts.is_dir():
        roots.append(artifacts)
    work = Path("/root/saf-pyjnius-spike")
    if work.is_dir():
        roots.append(work / "bin")
        roots.append(work / ".buildozer" / "android" / "platform")
    hits: list[str] = []
    for root in roots:
        hits.extend(scan(root))
    # Dedup
    hits = list(dict.fromkeys(hits))
    if hits:
        print("FORBIDDEN HITS:")
        print("\n".join(hits))
        return 1
    print("no forbidden tokens in spike source / generated manifests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
