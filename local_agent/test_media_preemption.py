#!/usr/bin/env python3
"""Offline checks for cooperative render pre-emption of queued media work."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import media_queue as mq
import media_tools
import media_watcher


class MediaPreemptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.root = Path(self.temp) / "queue"
        self.queue_root = patch.object(mq, "QUEUE_ROOT", self.root)
        self.queue_root.start()

    def tearDown(self):
        self.queue_root.stop()
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_preempted_video_action_returns_to_pending_with_audit(self):
        queued = mq.enqueue("video_action", {"video_path": "video.mp4"}, priority="interactive")
        job = mq.claim_next(kind="video_action")
        self.assertEqual(queued["id"], job["id"])
        with patch.object(media_watcher.media_tools, "extract_video_actions",
                          side_effect=media_tools.MediaPreempted("pre-empted by render")):
            media_watcher._run_video_action_job(job)
        pending = self.root / "pending" / f"{job['id']}.json"
        self.assertTrue(pending.is_file())
        self.assertFalse((self.root / "processing" / pending.name).exists())
        saved = json.loads(pending.read_text(encoding="utf-8"))
        self.assertEqual("interactive", saved["priority"])
        self.assertEqual("pre-empted by render", saved["preemptions"][-1]["reason"])

    def test_render_callback_raises_before_next_frame_or_batch(self):
        with self.assertRaises(media_tools.MediaPreempted):
            media_tools._raise_if_preempted({"__preempt_check": lambda: True})
        media_tools._raise_if_preempted({"__preempt_check": lambda: False})


if __name__ == "__main__":
    unittest.main()
