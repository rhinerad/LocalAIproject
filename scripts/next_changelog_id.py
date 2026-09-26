#!/usr/bin/env python3
"""Print and claim the next unused CHANGELOG id for today.

Usage (from the handoff tree root):

  python scripts/next_changelog_id.py

Prints a single token such as 2026-09-02w — the YYYY-MM-DDx prefix to use
in YYYY-MM-DDx_description.md. Run this before naming a changelog entry;
do not guess the letter.

Calling this script claims the id: it takes an exclusive lock and creates a
durable claim file under CHANGELOG/.id_claims/ so concurrent callers never
receive the same letter.

Optional: python scripts/next_changelog_id.py --date 2026-09-02
Optional: python scripts/next_changelog_id.py --changelog-dir PATH
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_DIR = REPO_ROOT / "CHANGELOG"
_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})([a-z]+)_")
_CLAIM_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})([a-z]+)$")
_LOCK_NAME = ".next_changelog_id.lock"
_CLAIMS_DIRNAME = ".id_claims"


def _claims_dir(changelog_dir: Path) -> Path:
    return changelog_dir / _CLAIMS_DIRNAME


def used_letters(changelog_dir: Path, day: str) -> set[str]:
    """Letters already taken by CHANGELOG entries or durable id claims."""
    used: set[str] = set()
    if not changelog_dir.is_dir():
        return used
    for path in changelog_dir.iterdir():
        if not path.is_file():
            continue
        match = _NAME_RE.match(path.name)
        if match and match.group(1) == day:
            used.add(match.group(2))
    claims = _claims_dir(changelog_dir)
    if claims.is_dir():
        for path in claims.iterdir():
            if not path.is_file():
                continue
            match = _CLAIM_RE.match(path.name)
            if match and match.group(1) == day:
                used.add(match.group(2))
    return used


def _letter_to_index(letter: str) -> int:
    """Excel-style base-26: a=1 .. z=26, aa=27, ..."""
    n = 0
    for ch in letter:
        if ch < "a" or ch > "z":
            raise ValueError(f"invalid letter {letter!r}")
        n = n * 26 + (ord(ch) - ord("a") + 1)
    return n


def _index_to_letter(n: int) -> str:
    if n < 1:
        raise ValueError("letter index must be >= 1")
    chars: list[str] = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("a") + rem))
    return "".join(reversed(chars))


def next_letter(used: set[str]) -> str:
    """Next Excel-style letter after the highest used (gaps are not filled).

    Progression: a…z, aa, ab, … zz. Duplicate claims for the same letter
    still advance past that letter.
    """
    valid = {item for item in used if item and item.isalpha() and item.islower()}
    if not valid:
        return "a"
    highest = max(_letter_to_index(item) for item in valid)
    # Exhaustion guard roughly matching prior zz ceiling for two-letter ids;
    # allow growth beyond zz via the same base-26 scheme.
    return _index_to_letter(highest + 1)


def _lock_exclusive(fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _unlock(fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _try_create_claim(claim_path: Path) -> bool:
    """Atomically create claim_path. Return True on success, False if exists."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(claim_path), flags)
    except FileExistsError:
        return False
    except OSError as exc:
        # Windows may raise OSError with errno EEXIST
        if getattr(exc, "errno", None) in (getattr(os, "EEXIST", 17), 17):
            return False
        raise
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return True


def allocate_next_id(day: str | None = None, changelog_dir: Path | None = None) -> str:
    """Lock, pick next letter, durable-claim it, unlock; return YYYY-MM-DDx."""
    day = day or date.today().isoformat()
    folder = changelog_dir or CHANGELOG_DIR
    folder.mkdir(parents=True, exist_ok=True)
    claims = _claims_dir(folder)
    claims.mkdir(parents=True, exist_ok=True)

    lock_path = folder / _LOCK_NAME
    # Binary mode required for msvcrt.locking; ensure >=1 byte to lock.
    with open(lock_path, "a+b") as fh:
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        _lock_exclusive(fh)
        try:
            while True:
                letter = next_letter(used_letters(folder, day))
                claim_path = claims / f"{day}{letter}"
                if _try_create_claim(claim_path):
                    return f"{day}{letter}"
                # Claim already present: recompute under the same lock.
        finally:
            _unlock(fh)


def next_id(day: str | None = None, changelog_dir: Path | None = None) -> str:
    """Allocate (claim) and return the next CHANGELOG id."""
    return allocate_next_id(day=day, changelog_dir=changelog_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claim and print the next unused CHANGELOG YYYY-MM-DDx id.")
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD (default: local today)")
    parser.add_argument("--changelog-dir", default=None,
                        help="override CHANGELOG/ path")
    args = parser.parse_args()
    if args.date:
        datetime.strptime(args.date, "%Y-%m-%d")
    folder = Path(args.changelog_dir) if args.changelog_dir else CHANGELOG_DIR
    print(allocate_next_id(args.date, folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
