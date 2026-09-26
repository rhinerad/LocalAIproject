#!/usr/bin/env python3
"""Regression checks for chat-to-job render preparation (stdlib only)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chat_render_jobs
import store


def _prompt() -> str:
    return """subject_definitions:
  <Subject 1> example subject
summary:
  short scene
retention_analysis:
  <Image 0> character reference, <Image 1> setting reference
detailed_description:
  [Shot 1] The subject moves once.
overall_soundscape:
  room tone
non_diegetic_music:
  N/A
"""


class ChatRenderJobTests(unittest.TestCase):
    def test_prepares_latest_valid_prompts_without_touching_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            uploads = root / "uploads"
            uploads.mkdir()
            character = uploads / "character.png"
            setting = uploads / "setting.png"
            character.write_bytes(b"character")
            setting.write_bytes(b"setting")
            videos = root / "chunks"
            videos.mkdir()
            for name in ("chunk_2.mp4", "chunk_10.mp4", "chunk_1.mp4"):
                (videos / name).write_bytes(b"video")

            with patch.object(store, "DIR", root / "chats"):
                conv = store.create("render this")
                store.append(conv["id"], "user",
                             f"local path: {character}\nlocal path: {setting}\n"
                             f"chunks: {videos}")
                store.append(conv["id"], "assistant",
                             f"```\n{_prompt()}```\n```\n{_prompt()}```\n"
                             "```\nsubject_definitions:\n  unfinished\n```")
                prepared = chat_render_jobs.prepare_from_chat(
                    conv["id"], jobs=root / "jobs")

            job = Path(prepared["job_folder"])
            self.assertEqual(2, prepared["prompt_count"])
            self.assertEqual(1, len(prepared["provenance"]["skipped_incomplete_or_invalid_prompts"]))
            self.assertEqual(["0001.txt", "0002.txt"],
                             sorted(p.name for p in (job / "prompts").glob("*.txt")))
            self.assertEqual(["0001.mp4", "0002.mp4"],
                             sorted(p.name for p in (job / "video_refs").glob("*.mp4")))
            self.assertTrue(character.is_file())
            self.assertTrue(setting.is_file())
            self.assertEqual(b"character", character.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
