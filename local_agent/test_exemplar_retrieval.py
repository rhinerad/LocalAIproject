#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent


class ExemplarRetrievalTests(unittest.TestCase):
    def test_only_two_provenance_labelled_examples_are_injected(self):
        rows = [{"id": f"stage_video_prompt_{n}", "category": "video_prompt",
                 "content": "example " + ("x" * 2000),
                 "metadata": {"source_dataset": "Manual", "license": "Internal"},
                 "similarity": 0.99} for n in range(3)]
        messages, notes = [], []
        with patch.object(agent.exemplar_embeddings, "retrieve", return_value=rows):
            ids = agent._prefetch_approved_exemplars(messages, "make a video prompt",
                                                      lambda kind, text: notes.append((kind, text)))
        self.assertEqual(["stage_video_prompt_0", "stage_video_prompt_1"], ids)
        self.assertEqual(1, len(messages))
        block = messages[0]["content"]
        self.assertIn("source: Manual", block)
        self.assertIn("license: Internal", block)
        self.assertNotIn("stage_video_prompt_2", block)
        self.assertLessEqual(len(block), agent.MAX_EXEMPLAR_CONTEXT_CHARS + 500)

    def test_unrelated_question_does_not_request_embeddings(self):
        messages = []
        with patch.object(agent.exemplar_embeddings, "retrieve") as retrieve:
            ids = agent._prefetch_approved_exemplars(messages, "explain photosynthesis", lambda *_: None)
        self.assertEqual([], ids)
        retrieve.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
