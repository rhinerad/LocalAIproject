#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import artifacts


class ArtifactTests(unittest.TestCase):
    def test_small_text_stays_in_context(self):
        self.assertEqual(artifacts.prune_large_text("tool", "small", limit=10), "small")

    def test_large_text_becomes_pointer_with_complete_local_artifact(self):
        with tempfile.TemporaryDirectory() as td, patch.object(artifacts, "ARTIFACT_DIR", Path(td)):
            original = "x" * 2501
            pointer = artifacts.prune_large_text("tool:read_file", original)
            self.assertIn("artifact_id=artifact_", pointer)
            self.assertLess(len(pointer), 2400)
            row = json.loads(next(Path(td).glob("*.json")).read_text(encoding="utf8"))
            self.assertEqual(row["content"], original)
            self.assertEqual(row["kind"], "tool:read_file")

    def test_same_text_reuses_fingerprint_artifact(self):
        with tempfile.TemporaryDirectory() as td, patch.object(artifacts, "ARTIFACT_DIR", Path(td)):
            first = artifacts.store("tool", "same")
            second = artifacts.store("different-kind", "same")
            self.assertEqual(first, second)
            self.assertEqual(len(list(Path(td).glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
