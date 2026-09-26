#!/usr/bin/env python3
"""Non-destructive privacy audit for a proposed public source tree.

This is a release gate, not a sanitizer and not a license determination. It
never alters files and never prints matched secret values. It reports only rule,
relative path, and line number.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".ps1", ".bat", ".cmd", ".ini"}
SKIP_PARTS = {".git", "__pycache__", "runtime", "uploads", "output", "outputs", "models", "vendor", "ble_runtime"}
RULES = {
    "absolute_windows_path": re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\(?:[^\r\n\"']+)", re.I),
    "absolute_unix_path": re.compile(r"(?<![A-Za-z0-9_])/(?:home|root|Users|opt|var|tmp)/[^\s\"']+"),
    "email_address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "api_key_assignment": re.compile(r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^\s'\"]+", re.I),
    "private_runtime_reference": re.compile(r"\b(?:paired_identities|runtime/|uploads/|output/|models/|COMFYUI_STORY_HANDOFF)\b", re.I),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        yield path


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_text_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            findings.append(Finding("unreadable_text_file", path.relative_to(root).as_posix(), 0))
            continue
        for number, line in enumerate(lines, 1):
            for name, pattern in RULES.items():
                if pattern.search(line):
                    findings.append(Finding(name, path.relative_to(root).as_posix(), number))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.rule))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="Candidate public tree")
    parser.add_argument("--json", action="store_true", help="Emit only rule/path/line metadata")
    args = parser.parse_args()
    if not args.dir.is_dir():
        parser.error(f"not a directory: {args.dir}")
    findings = audit(args.dir)
    payload = {"candidate": args.dir.name, "finding_count": len(findings),
               "findings": [asdict(finding) for finding in findings]}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{payload['finding_count']} issue(s) in candidate tree {args.dir.name!r}")
        for finding in findings:
            print(f"{finding.rule}: {finding.path}:{finding.line}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
