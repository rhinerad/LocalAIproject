#!/usr/bin/env python3
"""Workspace choice must be durable and override only context scope."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import store


class WorkspaceProfileTests(unittest.TestCase):
    def test_general_profile_blocks_specialist_context_even_for_named_history(self):
        history = [{"role": "user", "content": "Check Equal Shares clip 00A"}]
        self.assertFalse(agent.workspace_includes_project("general", history))

    def test_equal_shares_profile_enables_specialist_context_for_generic_followup(self):
        history = [{"role": "user", "content": "What should I do next?"}]
        self.assertTrue(agent.workspace_includes_project("equal_shares", history))

    def test_workspace_is_saved_separately_and_cannot_switch_active_chat(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, "DIR", Path(tmp)):
            conv = store.create("hello", model="test-model", workspace="general")
            loaded = store.load(conv["id"])
            self.assertEqual("general", loaded["workspace"])
            self.assertEqual("test-model", loaded["model"])
            self.assertFalse(store.set_workspace(conv["id"], "equal_shares"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
