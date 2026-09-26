#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prompt_prefix


class PromptPrefixTests(unittest.TestCase):
    def setUp(self):
        prompt_prefix.render_static_prefix.cache_clear()
        prompt_prefix.render_memory_prefix.cache_clear()

    def test_static_prefix_is_byte_stable_and_cached(self):
        first = prompt_prefix.render_static_prefix("rules", " operating", " learned")
        second = prompt_prefix.render_static_prefix("rules", " operating", " learned")
        self.assertEqual(first, "rules operating learned")
        self.assertEqual(first, second)
        self.assertEqual(prompt_prefix.render_static_prefix.cache_info().hits, 1)

    def test_memory_section_has_stable_empty_and_nonempty_forms(self):
        self.assertEqual(prompt_prefix.render_memory_prefix(""), "")
        self.assertEqual(prompt_prefix.render_memory_prefix("[hardware]\n- local"),
                         "\n\n# What I know about this operator\n\n[hardware]\n- local")


if __name__ == "__main__":
    unittest.main(verbosity=2)
