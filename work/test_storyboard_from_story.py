#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storyboard_from_story as board


def sample_plan() -> dict:
    return {
        "characters": [{"id": "ava", "description": "adult woman with dark curls", "identity_source": "none"}],
        "shots": [{"id": "01", "scene": "arrival", "characters": ["ava"],
                   "setting": "quiet train station", "lighting": "cool dawn", "action": "walks to platform",
                   "camera": "wide establishing shot", "prompt": "cinematic wide shot of Ava at a dawn station"}],
    }


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "stories"

    def tearDown(self):
        self.temp.cleanup()

    def test_initialise_writes_pending_non_gpu_state(self):
        state = board.initialise("arrival", sample_plan(), root=self.root)
        self.assertEqual("none", state["gpu_action"])
        self.assertTrue(Path(state["plan_path"]).is_file())
        with self.assertRaisesRegex(board.StoryboardError, "pending approval"):
            board.frame_plan("arrival", root=self.root)

    def test_approval_requires_sheets_then_explicit_confirmation(self):
        board.initialise("arrival", sample_plan(), root=self.root)
        with self.assertRaisesRegex(board.StoryboardError, "missing sheet"):
            board.approve_reference_overview("arrival", operator_confirmed=True, root=self.root)
        board.record_reference_sheets("arrival", {"ava": "ava-sheet.png"}, root=self.root)
        with self.assertRaisesRegex(board.StoryboardError, "explicit operator"):
            board.approve_reference_overview("arrival", operator_confirmed=False, root=self.root)
        board.approve_reference_overview("arrival", operator_confirmed=True, root=self.root)
        frames = board.frame_plan("arrival", root=self.root)
        self.assertTrue(frames["frames_released"])
        self.assertEqual("ava-sheet.png", frames["shots"][0]["reference_sheets"]["ava"])

    def test_unknown_character_in_shot_is_refused(self):
        bad = sample_plan()
        bad["shots"][0]["characters"] = ["nobody"]
        with self.assertRaisesRegex(board.StoryboardError, "unknown character"):
            board.validate_plan(bad)

    def test_path_escape_story_name_is_refused(self):
        with self.assertRaisesRegex(board.StoryboardError, "letters or numbers"):
            board.initialise("..", sample_plan(), root=self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
