#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exemplar_curator
import exemplar_embeddings
import exemplar_lifecycle


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(exemplar_curator, "ROOT", root),
                        patch.object(exemplar_curator, "PENDING", root / "pending"),
                        patch.object(exemplar_curator, "APPROVED", root / "approved"),
                        patch.object(exemplar_curator, "REJECTED", root / "rejected"),
                        patch.object(exemplar_embeddings, "embed_record", return_value={"status": "embedded"}),
                        patch.object(exemplar_lifecycle, "ARCHIVE", root / "archive"),
                        patch.object(exemplar_lifecycle, "ATTRIBUTIONS", root / "attrs.json")]
        for item in self.patches:
            item.start()
        self.row = exemplar_curator.stage({"source_dataset": "Manual", "license": "Internal",
            "category": "video_prompt", "style_domain": "general", "title": "Example",
            "content": "A person walks through a rainy city, turns toward camera, then enters a warm shop."})
        exemplar_curator.review(self.row["id"], "approve")

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_attribution_updates_score_and_archives_stale_reversibly(self):
        for number in range(5):
            message = f"m{number}"
            exemplar_lifecycle.record_attribution(message, [self.row["id"]])
            exemplar_lifecycle.update_scores(message, "negative")
        health = exemplar_lifecycle.audit_health()
        self.assertEqual([self.row["id"]], health["needs_review"])
        result = exemplar_lifecycle.archive_stale_exemplars()
        self.assertEqual([self.row["id"]], result["archived"])
        self.assertTrue((exemplar_lifecycle.ARCHIVE / f"{self.row['id']}.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
