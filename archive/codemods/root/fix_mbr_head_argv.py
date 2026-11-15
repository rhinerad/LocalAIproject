from pathlib import Path
import sys
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
block = (
    "try:\n"
    "    import native_voice_continuity as _nvc\n"
    "    _HAS_NATIVE_VOICE = True\n"
    "except Exception:\n"
    "    _HAS_NATIVE_VOICE = False\n\n"
)
idx = t.find("#!/usr/bin/env python3")
if idx > 0:
    t = t[idx:]
elif t.startswith(block):
    t = t[len(block):]
needle = "from __future__ import annotations\n"
if needle not in t:
    raise SystemExit("missing future import")
# remove all blocks then insert once after future
t = t.replace(block, "")
t = t.replace(needle, needle + "\n" + block, 1)
p.write_text(t, encoding="utf-8")
print("fixed", p)
print(p.read_text(encoding="utf-8")[:400])
