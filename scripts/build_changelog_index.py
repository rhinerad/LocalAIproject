#!/usr/bin/env python3
"""Regenerate CHANGELOG/README.md from the entry files.

Usage (from the repository root):

  python scripts/build_changelog_index.py

Newest first. The title is the first Markdown heading in each entry, or the
filename slug when there is none. Also lists CHANGELOG/astra_2026-09/, the
parallel set written by the Astra agent, under its own heading.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_DIR = REPO_ROOT / "CHANGELOG"
OUTPUT = CHANGELOG_DIR / "README.md"
_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})([a-z]*)_(.+)\.md$")


def _title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip() or path.stem
    return path.stem


def _entries(folder: Path, pattern: re.Pattern[str]) -> list[tuple[str, str, Path]]:
    found = []
    for p in folder.glob("*.md"):
        if p.name == "README.md":
            continue
        m = pattern.match(p.name)
        if not m:
            continue
        date, letter = m.group(1), m.group(2)
        found.append((date, letter, p))
    found.sort(key=lambda t: (t[0], len(t[1]), t[1]), reverse=True)
    return found


def main() -> None:
    lines = [
        "# CHANGELOG — every change to this project, in detail, no exceptions",
        "",
        "Filenames are `YYYY-MM-DD` + sequential letter + `_slug.md`. Run",
        "`python scripts/next_changelog_id.py` for the next free id and",
        "`python scripts/build_changelog_index.py` to regenerate this index.",
        "",
    ]
    main_entries = _entries(CHANGELOG_DIR, _NAME_RE)
    lines.append(f"## Entries ({len(main_entries)})")
    lines.append("")
    for date, letter, p in main_entries:
        lines.append(f"- `{date}{letter}` — [{_title(p)}]({p.name})")
    astra = CHANGELOG_DIR / "astra_2026-09"
    if astra.is_dir():
        astra_re = re.compile(r"^CHANGELOG_(\d{4}-\d{2}-\d{2})([a-z]*)_(.+)\.md$")
        extra = _entries(astra, astra_re)
        lines += ["", f"## Astra agent set, September 2026 ({len(extra)} entries plus evidence matrices)", "",
                  "Written in the Astra sandbox against copies of this tree; evidence paths in them",
                  "point at `live_jobs/`, which is local to the workstation.", ""]
        for date, letter, p in extra:
            lines.append(f"- `{date}{letter}` — [{_title(p)}](astra_2026-09/{p.name})")
        others = sorted(x.name for x in astra.iterdir() if not astra_re.match(x.name) and x.name != "README.md")
        if others:
            lines.append("")
            lines.append("Evidence and ledgers: " + ", ".join(f"[{n}](astra_2026-09/{n})" for n in others))
    lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}: {len(main_entries)} entries")


if __name__ == "__main__":
    main()
