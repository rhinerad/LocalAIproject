#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from public_release_audit import audit


class PublicReleaseAuditTests(unittest.TestCase):
    def test_reports_rules_without_echoing_sensitive_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "example.py").write_text(
                'path = "C:\\\\Users\\\\private\\\\file.txt"\napi_key = "never-echo-this"\n',
                encoding="utf-8",
            )
            findings = audit(root)

        rules = {finding.rule for finding in findings}
        self.assertIn("absolute_windows_path", rules)
        self.assertIn("api_key_assignment", rules)
        self.assertNotIn("never-echo-this", str(findings))

    def test_ignores_private_runtime_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root / "runtime"
            private.mkdir()
            (private / "state.json").write_text('api_key="not-scanned"', encoding="utf-8")
            (root / "safe.md").write_text("Synthetic public example.", encoding="utf-8")
            self.assertEqual(audit(root), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
