"""Fixtures for read-only workspace inspection; no real project state is used."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import workspace_inspector


class WorkspaceInspectorTests(unittest.TestCase):
    def test_code_repository_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / ".git").mkdir(); (root / "pyproject.toml").write_text("[project]", encoding="utf-8")
            report = workspace_inspector.inspect(root)
        self.assertEqual("code_repository", report["detected_project_type"])

    def test_dataset_lora_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "adapter_config.json").write_text("{}", encoding="utf-8")
            report = workspace_inspector.inspect(root)
        self.assertEqual("dataset_or_lora", report["detected_project_type"])

    def test_general_comfyui_fixture_does_not_become_equal_shares(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "custom_nodes").mkdir(); (root / "user").mkdir()
            report = workspace_inspector.inspect(root)
        self.assertEqual("comfyui_project", report["detected_project_type"])
        self.assertNotEqual("equal_shares", report["detected_project_type"])

    def test_equal_shares_requires_distinctive_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / "docs" / "GOLDEN_REFERENCE").mkdir(parents=True); (root / "outputs" / "equal_shares").mkdir(parents=True)
            (root / "docs" / "GOLDEN_REFERENCE" / "PROVEN_FACTS.md").write_text("facts", encoding="utf-8")
            report = workspace_inspector.inspect(root)
        self.assertEqual("equal_shares", report["detected_project_type"])
        self.assertEqual("unambiguous", report["detection_confidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
