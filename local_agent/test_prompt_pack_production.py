#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import managed_prompt_pack
import prompt_pack_production
import action_resolver


class FullProductionDetectTests(unittest.TestCase):
    def test_short_complete_ask(self):
        self.assertTrue(prompt_pack_production.wants_full_production(
            "complete images and videos"))
        self.assertTrue(prompt_pack_production.wants_full_production(
            "Generate all stills then videos please"))
        self.assertTrue(prompt_pack_production.wants_full_production(
            "full production"))

    def test_pack_body_alone_false(self):
        # Large pack body embeds "Generate the stills first" — must not unlock.
        body = "# Backrooms Sitcom Audition Prompt Pack\n" + ("x" * 5000)
        body += "\nGenerate the stills first and approve each handoff before animating.\n"
        self.assertFalse(prompt_pack_production.wants_full_production(body))

    def test_wrapper_on_pack(self):
        body = "complete images and videos\n\n# Backrooms Sitcom Audition Prompt Pack\n"
        body += "#### C001\n" + ("clip text " * 400)
        self.assertTrue(prompt_pack_production.wants_full_production(body))


class ActionPlanProductionTests(unittest.TestCase):
    def test_short_ask_routes_when_pack_ready(self):
        with mock.patch.object(managed_prompt_pack, "load_progress", return_value={
            "kind": "prompt_pack", "clip_count": 2, "next_index": 2, "clip_ids": ["C001", "C002"],
        }), mock.patch.object(managed_prompt_pack, "has_incomplete_export", return_value=False):
            plan = action_resolver.classify(
                "complete images and videos", history=[], cid="abcd1234efgh5678",
                pending_calibration_path_fn=lambda history, cid: None,
                specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.intent, "prompt_pack_production")
        self.assertEqual(plan.steps[-1][0], "run_prompt_pack_production")


class StillJobBuilderTests(unittest.TestCase):
    def test_two_frames_per_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp) / "cidtest01"
            clips = task / "clips"
            clips.mkdir(parents=True)
            out = task / "outputs"
            out.mkdir()
            for i, cid in enumerate(["C001", "C002"], 1):
                (clips / f"{cid}.json").write_text(json.dumps({
                    "id": cid,
                    "header": f"### {cid}",
                    "start_frame": f"start prompt {cid} " + ("word " * 20),
                    "last_frame": f"last prompt {cid} " + ("word " * 20),
                    "video_prompt": f"video prompt {cid} " + ("word " * 20),
                    "model_profile": "realvisxl",
                    "body": "body",
                }), encoding="utf-8")
            progress = {
                "version": 1,
                "kind": "prompt_pack",
                "conversation_id": "cidtest01",
                "source_sha256": "deadbeefcafebabe",
                "clip_ids": ["C001", "C002"],
                "clip_count": 2,
                "exported_ids": ["C001", "C002"],
                "next_index": 2,
                "clips_dir": str(clips),
                "output_dir": str(out),
                "allow_render": False,
                "status": "exported",
                "mode": "exported",
                "source_path": str(task / "source.md"),
                "progress_path": str(task / "progress.json"),
            }
            with mock.patch.object(managed_prompt_pack, "_task_dir", return_value=task), \
                 mock.patch.object(managed_prompt_pack, "load_progress", return_value=progress), \
                 mock.patch.object(managed_prompt_pack, "has_incomplete_export", return_value=False):
                jobs = prompt_pack_production.build_still_jobs("cidtest01")
            self.assertEqual(len(jobs), 4)
            self.assertEqual({j["frame"] for j in jobs}, {"start", "last"})
            self.assertEqual({j["denoise"] for j in jobs if j["frame"] == "start"}, {0.42})
            self.assertEqual({j["denoise"] for j in jobs if j["frame"] == "last"}, {0.52})
            c001_last = next(j for j in jobs if j["clip_id"] == "C001" and j["frame"] == "last")
            self.assertIn("ENDPOINT ACTION PRIORITY", c001_last["prompt"])


if __name__ == "__main__":
    unittest.main()
