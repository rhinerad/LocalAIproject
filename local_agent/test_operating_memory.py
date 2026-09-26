#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import operating_memory


class OperatingMemoryTests(unittest.TestCase):
    def test_project_block_is_included_only_when_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operating.md"
            path.write_text("## General policy\nGeneral.\n\n## Project policy\nProject only.", encoding="utf8")
            self.assertIn("General.", operating_memory.render(path, include_project=False))
            self.assertNotIn("Project only.", operating_memory.render(path, include_project=False))
            self.assertIn("Project only.", operating_memory.render(path, include_project=True))

    def test_legacy_unsectioned_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operating.md"
            path.write_text("Existing policy.", encoding="utf8")
            self.assertEqual("Existing policy.", operating_memory.render(path, include_project=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
