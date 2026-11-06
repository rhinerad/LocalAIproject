#!/usr/bin/env python3
"""Regression tests for evidence-only radio metrics."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radio_metrics


class RadioMetricsTests(unittest.TestCase):
    def _jsonl(self, path: Path, rows: list[dict]) -> None:
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_queue_is_not_claimed_as_delivery_without_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            audit = Path(td) / "audit.jsonl"
            self._jsonl(audit, [{"event": "queued", "job_id": "job", "counter": 0, "at": 100.0}])
            out = radio_metrics.report(audit)
        self.assertEqual(out["delivery_status"], "not_measured_without_phone_receipts")
        self.assertEqual(out["unique_lxmf_queue_events"], 1)

    def test_closed_receipt_set_calculates_loss_conservatively(self):
        with tempfile.TemporaryDirectory() as td:
            audit, receipts = Path(td) / "audit.jsonl", Path(td) / "receipts.jsonl"
            self._jsonl(audit, [
                {"event": "queued", "job_id": "job", "counter": 0, "at": 100.0},
                {"event": "queued", "job_id": "job", "counter": 1, "at": 130.0},
            ])
            self._jsonl(receipts, [{"job_id": "job", "counter": 0, "received_at": 105.0}])
            out = radio_metrics.report(audit, receipts, close_at=200.0)
        self.assertEqual(out["delivery_status"], "measured_from_operator_receipts")
        self.assertEqual(out["expected_before_close"], 2)
        self.assertEqual(out["receipt_confirmed"], 1)
        self.assertEqual(out["observed_loss_percent"], 50.0)
        self.assertEqual(out["latency_seconds"]["median"], 5.0)
