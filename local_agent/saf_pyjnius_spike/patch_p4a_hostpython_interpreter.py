#!/usr/bin/env python3
"""Point p4a PyProjectRecipe at native-build hostpython.

Root cause of setuptools.build_meta BackendUnavailable: p4a copies
hostpython into python3/android-build/ so `python -m build` runs an
x86-64 interpreter whose module path is the aarch64 target build dir.
`import math` fails, so setuptools never loads. native-build/python3
imports setuptools.build_meta with PYTHONPATH=destroot site-packages.
"""
from __future__ import annotations

import sys
from pathlib import Path

OLD_CMD = "            sh.Command(self.ctx.python_recipe.python_exe), *build_args, _env=env"
NEW_CMD = "            sh.Command(self.real_hostpython_location), *build_args, _env=env"
OLD_ARGS = "    extra_build_args = []"
NEW_ARGS = "    extra_build_args = ['--no-isolation']"


def main() -> int:
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    changed = False
    if OLD_CMD in text:
        text = text.replace(OLD_CMD, NEW_CMD, 1)
        changed = True
        print("patched interpreter", path)
    elif NEW_CMD in text:
        print("interpreter already patched", path)
    else:
        print("interpreter needle missing", path)
        return 1
    if OLD_ARGS in text:
        text = text.replace(OLD_ARGS, NEW_ARGS, 1)
        changed = True
        print("patched extra_build_args", path)
    if changed:
        path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
