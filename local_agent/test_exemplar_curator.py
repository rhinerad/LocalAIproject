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

import exemplar_curator
import exemplar_embeddings
import exemplar_filter


class ExemplarCuratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(exemplar_curator, "ROOT", root),
                        patch.object(exemplar_curator, "PENDING", root / "pending"),
                        patch.object(exemplar_curator, "APPROVED", root / "approved"),
                        patch.object(exemplar_curator, "REJECTED", root / "rejected"),
                        patch.object(exemplar_embeddings, "embed_record", return_value={
                            "status": "embedded", "model": "nomic-embed-text:latest",
                            "collection": "exemplars_video_prompts", "dimensions": 768})]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    @staticmethod
    def candidate(**extra):
        item = {"source_dataset": "Manual", "license": "Internal", "category": "video_prompt",
                "style_domain": "general", "title": "Test prompt",
                "content": "A person walks through a rainy city, turns toward camera, then enters a warm shop.",
                "metadata": {"tags": ["motion"]}}
        item.update(extra)
        return item

    def test_rejects_bad_workflow_and_midjourney_prompt(self):
        self.assertFalse(exemplar_filter.check_candidate(
            self.candidate(content="short --ar 16:9"))["ok"])
        report = exemplar_filter.check_candidate(self.candidate(category="comfyui_workflow", content="{broken"))
        self.assertIn("workflow content is not valid JSON", report["errors"])

    def test_staging_requires_explicit_review_and_reject_is_not_active(self):
        row = exemplar_curator.stage(self.candidate())
        self.assertEqual("pending", row["status"])
        self.assertEqual(1, len(exemplar_curator.pending()))
        rejected = exemplar_curator.review(row["id"], "reject")
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual([], exemplar_curator.pending())
        self.assertTrue((exemplar_curator.REJECTED / f"{row['id']}.json").is_file())

    def test_edit_approve_rechecks_content_and_embeds_only_after_approval(self):
        row = exemplar_curator.stage(self.candidate())
        approved = exemplar_curator.review(row["id"], "edit_approve",
            content="A dancer steps across a quiet studio, pauses by the window, then bows to the audience.")
        self.assertEqual("approved", approved["status"])
        self.assertEqual("embedded", approved["embedding"]["status"])
        self.assertTrue((exemplar_curator.APPROVED / f"{row['id']}.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
