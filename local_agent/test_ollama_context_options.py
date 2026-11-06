#!/usr/bin/env python3
"""Keep the CPU client's context window tied to routing policy."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ollama_client
import router


class OllamaContextOptionsTests(unittest.TestCase):
    def test_cpu_context_window_uses_router_policy(self) -> None:
        self.assertEqual(
            ollama_client.DEFAULT_OPTIONS["num_ctx"],
            router.CPU_OPTIONS["num_ctx"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
