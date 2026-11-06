from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_approved_calibration_pairs import validate


def row(number: int) -> dict[str, object]:
    return {
        "pair_id": f"pa-{number:03d}",
        "harmful": f"Approved contrastive harmful prompt number {number} for calibration.",
        "harmless": f"Approved matched harmless prompt number {number} for calibration.",
        "category": "contrastive_refusal",
        "source": "operator_authored",
        "approval_id": "operator-approval-20260830",
        "operator_approved": True,
        "schema_version": "projected-abliteration-v1",
    }


class ApprovedCalibrationTests(unittest.TestCase):
    def write(self, rows: list[dict[str, object]]) -> Path:
        temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with temp:
            for item in rows:
                temp.write(json.dumps(item) + "\n")
        return Path(temp.name)

    def test_accepts_32_approved_pairs(self):
        path = self.write([row(index) for index in range(1, 33)])
        self.assertEqual(validate(path)["pairs"], 32)

    def test_rejects_unapproved_or_duplicate_pairs(self):
        rows = [row(index) for index in range(1, 33)]
        rows[0]["operator_approved"] = False
        with self.assertRaises(ValueError):
            validate(self.write(rows))

    def test_streaming_full_run_imports_the_approval_gate(self):
        source = (Path(__file__).resolve().parent / "abliterate_turbosparse_v2.py").read_text(encoding="utf-8")
        self.assertIn("validate_approved_pairs(pairs_path)", source)
        rows = [row(index) for index in range(1, 33)]
        rows[-1]["pair_id"] = "pa-001"
        with self.assertRaises(ValueError):
            validate(self.write(rows))


if __name__ == "__main__":
    unittest.main()
