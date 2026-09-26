#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import chromadb
from chromadb.config import Settings

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exemplar_embeddings


class ExemplarEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.client = chromadb.EphemeralClient(Settings(anonymized_telemetry=False))
        self.embed_patch = patch.object(exemplar_embeddings.oll, "embed", return_value=[[1.0, 0.0, 0.0]])
        self.busy = patch.object(exemplar_embeddings.router, "chat_busy", return_value=False)
        self.client_patch = patch.object(exemplar_embeddings, "_client", return_value=self.client)
        self.embed_mock = self.embed_patch.start(); self.busy.start(); self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop(); self.busy.stop(); self.embed_patch.stop()

    @staticmethod
    def record(status="approved"):
        return {"id": "stage_video_prompt_001", "status": status, "category": "video_prompt",
                "content": "A woman crosses a quiet studio and pauses at a sunlit window.",
                "source_dataset": "Manual", "license": "Internal", "style_domain": "general",
                "title": "Studio action", "content_fingerprint": "abc"}

    def test_approved_item_is_cpu_embedded_and_is_semantically_findable(self):
        result = exemplar_embeddings.embed_record(self.record())
        self.assertEqual("embedded", result["status"])
        self.assertEqual(3, result["dimensions"])  # Small mocked vector; production nomic is 768-D.
        found = exemplar_embeddings.semantic_duplicate("video_prompt", self.record()["content"])
        self.assertTrue(found["duplicate"])
        retrieved = exemplar_embeddings.retrieve("describe a video prompt", ["video_prompt"])
        self.assertEqual([self.record()["id"]], [item["id"] for item in retrieved])
        self.embed_mock.assert_any_call(self.record()["content"], model="nomic-embed-text:latest",
                                        host=exemplar_embeddings.router.CPU_HOST)

    def test_unapproved_item_is_refused(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            exemplar_embeddings.embed_record(self.record("pending"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
