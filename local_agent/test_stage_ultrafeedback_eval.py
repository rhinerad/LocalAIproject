#!/usr/bin/env python3
"""No-network checks for the UltraFeedback evaluation staging adapter."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stage_ultrafeedback_eval as staging


class StagingTests(unittest.TestCase):
    def _rows(self):
        return [
            {"prompt": f"Explain a safe local-tool choice for task {n} in detail.",
             "chosen": f"Use the named allowed tool and verify its result for task {n}.",
             "rejected": f"Pretend the task {n} already happened without evidence."}
            for n in range(12)
        ]

    def test_deterministic_bounded_records(self):
        first = list(staging.records(self._rows(), count=5, seed=7))
        second = list(staging.records(self._rows(), count=5, seed=7))
        self.assertEqual([item["id"] for item in first], [item["id"] for item in second])
        self.assertEqual(5, len(first))
        self.assertTrue(all(item["status"] == "pending_review" for item in first))
        self.assertTrue(all(item["intended_use"] == "offline_evaluation_candidate_only" for item in first))

    def test_missing_preference_fields_are_rejected(self):
        self.assertEqual([], list(staging.records([{"prompt": "only a prompt"}], count=1, seed=1)))

    def test_write_never_overwrites_a_review_record(self):
        record = next(staging.records(self._rows(), count=1, seed=1))
        with tempfile.TemporaryDirectory() as td:
            pending = Path(td)
            self.assertEqual(1, staging.write_pending([record], pending))
            path = pending / f"{record['id']}.json"
            path.write_text('{"status":"reviewed"}', encoding="utf-8")
            self.assertEqual(0, staging.write_pending([record], pending))
            self.assertIn("reviewed", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
