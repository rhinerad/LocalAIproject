"""Tests for deterministic loop evidence verifiers."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import loop_verifiers


class LoopVerifierTests(unittest.TestCase):
    def test_file_hash_returns_only_compact_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            path.write_text("safe content", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            report = loop_verifiers.verify("file_sha256", {"path": path, "expected_sha256": digest})
        self.assertTrue(report["passed"])
        self.assertNotIn("path", report)

    def test_json_shape_and_result_predicate_are_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "data.json"
            path.write_text(json.dumps({"id": 1, "status": "ok"}), encoding="utf-8")
            report = loop_verifiers.verify("json_required_keys", {"path": path, "required_keys": ["id", "status"]})
        self.assertTrue(report["passed"])
        self.assertTrue(loop_verifiers.verify("result_predicate", {
            "result": {"returncode": 0}, "field": "returncode", "equals": 0})["passed"])
        self.assertFalse(loop_verifiers.verify("result_predicate", {
            "result": {"returncode": 1}, "field": "returncode", "equals": 0})["passed"])

    def test_invalid_verifier_is_refused(self):
        with self.assertRaises(loop_verifiers.VerificationError):
            loop_verifiers.verify("shell", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
