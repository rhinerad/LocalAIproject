#!/usr/bin/env python3
"""Tests for the GUI context-ceiling feature (UPGRADE 08, Feature 1).

Run:  python local_agent/test_ctx_ceiling.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import server


def _check(description: str, got, want) -> bool:
    if got == want:
        print(f"  ok  {description}")
        return True
    print(f"  FAIL {description}: got {got!r}, want {want!r}")
    return False


def test_apply_ctx_ceiling() -> int:
    failures = 0

    # ceiling caps: 16384 over adaptive 20480 -> 16384
    if not _check("ceiling caps 20480 to 16384",
                  agent._apply_ctx_ceiling(20480, 16384), 16384):
        failures += 1

    # ceiling never raises: 32768 over adaptive 20480 -> 20480 unchanged
    if not _check("ceiling 32768 does not raise 20480",
                  agent._apply_ctx_ceiling(20480, 32768), 20480):
        failures += 1

    # Auto / None passes through
    if not _check("None ceiling is pass-through",
                  agent._apply_ctx_ceiling(20480, None), 20480):
        failures += 1

    # ceiling at exact boundary
    if not _check("ceiling equals adaptive -> adaptive unchanged",
                  agent._apply_ctx_ceiling(8192, 8192), 8192):
        failures += 1

    # small adaptive, large ceiling -> adaptive unchanged
    if not _check("small adaptive below ceiling is unchanged",
                  agent._apply_ctx_ceiling(4096, 32768), 4096):
        failures += 1

    return failures


def test_parse_ctx_ceiling() -> int:
    failures = 0

    if not _check("16384 parses to 16384",
                  server._parse_ctx_ceiling("16384"), 16384):
        failures += 1

    if not _check("None (Auto) -> None",
                  server._parse_ctx_ceiling(None), None):
        failures += 1

    if not _check("empty string -> None",
                  server._parse_ctx_ceiling(""), None):
        failures += 1

    if not _check("bogus string -> None",
                  server._parse_ctx_ceiling("banana"), None):
        failures += 1

    if not _check("below 4096 -> None",
                  server._parse_ctx_ceiling(2048), None):
        failures += 1

    if not _check("above 32768 -> None",
                  server._parse_ctx_ceiling(65536), None):
        failures += 1

    if not _check("boundary 4096 is valid",
                  server._parse_ctx_ceiling(4096), 4096):
        failures += 1

    if not _check("boundary 32768 is valid",
                  server._parse_ctx_ceiling(32768), 32768):
        failures += 1

    return failures


def main() -> int:
    total = 0
    print("test_apply_ctx_ceiling")
    total += test_apply_ctx_ceiling()
    print("test_parse_ctx_ceiling")
    total += test_parse_ctx_ceiling()
    if total:
        print(f"\n{total} failure(s)")
    else:
        print("\nAll OK")
    return total


if __name__ == "__main__":
    raise SystemExit(main())
