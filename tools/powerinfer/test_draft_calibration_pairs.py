from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validate_calibration_pairs import validate


def draft_row(number: int, approved: bool = False, approval_id=None) -> dict[str, object]:
    return {
        "pair_id": f"pa-{number:03d}",
        "harmful": f"Educational contrastive prompt number {number} for draft review.",
        "harmless": f"Matched educational prompt number {number} for draft review.",
        "category": "contrastive_refusal",
        "source": "operator_authored",
        "approval_id": approval_id,
        "operator_approved": approved,
        "schema_version": "projected-abliteration-v1",
    }


class DraftCalibrationTests(unittest.TestCase):
    def write(self, rows: list[dict[str, object]]) -> Path:
        temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with temp:
            for item in rows:
                temp.write(json.dumps(item) + "\n")
        return Path(temp.name)

    def test_draft_accepts_false_and_null(self):
        path = self.write([draft_row(index) for index in range(1, 9)])
        result = validate(path, minimum=8, draft=True)
        self.assertEqual(result["pairs"], 8)
        self.assertEqual(result["status"], "draft_unapproved")

    def test_draft_rejects_operator_approved_true(self):
        rows = [draft_row(index) for index in range(1, 9)]
        rows[0]["operator_approved"] = True
        with self.assertRaises(ValueError) as ctx:
            validate(self.write(rows), minimum=8, draft=True)
        self.assertIn("operator_approved true", str(ctx.exception))

    def test_draft_rejects_non_null_approval_id(self):
        rows = [draft_row(index) for index in range(1, 9)]
        rows[0]["approval_id"] = "operator-approval-20260908"
        with self.assertRaises(ValueError) as ctx:
            validate(self.write(rows), minimum=8, draft=True)
        self.assertIn("non-null approval_id", str(ctx.exception))

    def test_non_draft_mode_unchanged_for_structure_only(self):
        rows = [
            {"harmful": "alpha beta gamma", "harmless": "delta epsilon zeta"}
            for _ in range(8)
        ]
        self.assertEqual(validate(self.write(rows), minimum=8)["pairs"], 8)


if __name__ == "__main__":
    unittest.main()
