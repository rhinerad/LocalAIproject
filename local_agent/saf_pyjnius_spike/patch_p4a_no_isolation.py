#!/usr/bin/env python3
from pathlib import Path
import sys

p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
needle = "    extra_build_args = []"
repl = "    extra_build_args = ['--no-isolation']"
if repl in text:
    print("already patched", p)
    sys.exit(0)
if needle not in text:
    print("needle missing", p)
    sys.exit(1)
p.write_text(text.replace(needle, repl, 1), encoding="utf-8")
print("patched", p)
