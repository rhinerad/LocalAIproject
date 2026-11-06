#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

apk = Path("/root/saf-pyjnius-spike/bin/safspike-0.0.1-arm64-v8a-debug.apk")
print("apk", apk, "exists", apk.is_file(), "bytes", apk.stat().st_size if apk.is_file() else 0)
if apk.is_file():
    h = hashlib.sha256(apk.read_bytes()).hexdigest()
    print("sha256", h)
    out = subprocess.check_output(["unzip", "-l", str(apk)], text=True, errors="replace")
    sos = [ln for ln in out.splitlines() if ".so" in ln]
    print("so_count", len(sos))
    for ln in sos[:30]:
        print(ln)
base = Path("/root/saf-pyjnius-spike/.buildozer/android/platform/build-arm64-v8a/dists/safspike")
for mf in [
    base / "src/main/AndroidManifest.xml",
    base / "AndroidManifest.xml",
    base / "build/intermediates/merged_manifest/debug/processDebugMainManifest/AndroidManifest.xml",
]:
    print("manifest", mf, "exists", mf.is_file())
    if not mf.is_file():
        continue
    text = mf.read_text(encoding="utf-8", errors="replace")
    print("bytes", len(text))
    print(text)
    break
