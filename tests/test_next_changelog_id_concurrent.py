#!/usr/bin/env python3
"""Concurrent uniqueness test for scripts/next_changelog_id.py."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "next_changelog_id.py"
FIXED_DATE = "2099-06-15"
WORKER_COUNT = 24


def _run_once(changelog_dir: Path) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--date",
            FIXED_DATE,
            "--changelog-dir",
            str(changelog_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


class TestNextChangelogIdConcurrent(unittest.TestCase):
    def test_concurrent_allocations_are_unique(self) -> None:
        tmp = tempfile.mkdtemp(prefix="changelog_id_test_")
        changelog_dir = Path(tmp) / "CHANGELOG"
        changelog_dir.mkdir(parents=True, exist_ok=True)
        try:
            results: list[str] = []
            with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
                futures = [
                    pool.submit(_run_once, changelog_dir)
                    for _ in range(WORKER_COUNT)
                ]
                for fut in as_completed(futures):
                    results.append(fut.result())

            self.assertEqual(len(results), WORKER_COUNT)
            self.assertEqual(len(set(results)), WORKER_COUNT, results)

            # Contiguous Excel-style prefix starting at a for an empty dir.
            letters = sorted(
                (rid[len(FIXED_DATE) :] for rid in results),
                key=lambda s: (
                    len(s),
                    s,
                ),
            )
            # Prefer numeric Excel order via the script helpers when available.
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            import next_changelog_id as nci  # noqa: E402

            letters = sorted(
                (rid[len(FIXED_DATE) :] for rid in results),
                key=nci._letter_to_index,
            )
            expected = [nci._index_to_letter(i) for i in range(1, WORKER_COUNT + 1)]
            self.assertEqual(letters, expected)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
