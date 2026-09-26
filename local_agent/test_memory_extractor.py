#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import memory_extractor


class MemoryExtractorTests(unittest.TestCase):
    def test_extracts_allowed_stable_fact_with_cpu_only_options(self):
        payload = {"facts": [{"category": "preferences", "fact": "Prefers concise status updates."}]}
        seen, remembered = {}, []
        def fake_chat(_messages, **kwargs):
            seen.update(kwargs)
            return json.dumps(payload), []
        with patch.object(memory_extractor, "_installed", return_value=True), \
             patch.object(memory_extractor.router, "chat_busy", return_value=False), \
             patch.object(memory_extractor.oll, "chat", fake_chat), \
             patch.object(memory_extractor.memory, "remember", side_effect=lambda f, c: remembered.append((f, c)) or "ok"):
            self.assertEqual(memory_extractor.extract_and_remember("I prefer concise updates", "Okay."), ["ok"])
        self.assertEqual(remembered, [("Prefers concise status updates.", "preferences")])
        self.assertEqual(seen["host"], memory_extractor.router.CPU_HOST)
        self.assertEqual(seen["keep_alive"], "0")
        self.assertEqual(seen["options"]["num_gpu"], 0)

    def test_rejects_sensitive_and_invalid_output(self):
        payload = {"facts": [{"category": "hardware", "fact": "C:\\Users\\private"},
                             {"category": "bad", "fact": "no"}]}
        with patch.object(memory_extractor, "_installed", return_value=True), \
             patch.object(memory_extractor.router, "chat_busy", return_value=False), \
             patch.object(memory_extractor.oll, "chat", return_value=(json.dumps(payload), [])), \
             patch.object(memory_extractor.memory, "remember") as remember:
            self.assertEqual(memory_extractor.extract_and_remember("x", "y"), [])
        remember.assert_not_called()

    def test_does_not_queue_when_the_exact_cpu_model_is_absent(self):
        with patch.object(memory_extractor, "_installed", return_value=False):
            self.assertFalse(memory_extractor.enqueue_turn("id", "question", "answer"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
