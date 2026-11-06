#!/usr/bin/env python3
"""Unit tests for master_batch_runner.py state handling: evidence-preserving
mark_clip (previous_selected, uncapped attempts), the shared atomic writer, the
TimeoutExpired path (FAILED_RENDER + ComfyUI /interrupt + continue), the shared
GPU lock around the clip loop, and the COMFY_SHARED_INPUT env.  No GPU/ComfyUI."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "local_agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gpu_lock  # noqa: E402
import master_batch_runner as mbr  # noqa: E402
from local_agent import atomic_io  # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()


class MarkClipEvidenceTests(_Tmp):
    def _mark(self, clip, status, *, pipeline_state=None, video=None, attempt_id=None):
        path = self.tmp / "C001.json"
        mbr.mark_clip(
            path, clip, status=status, started_at="t0", finished_at="t1", command=["x"],
            returncode=0 if status in mbr.SELECTED_STATUSES else 1,
            start_ref=None, start_note="", last_ref=None, last_note="", previous_video=None,
            video_path=video, stdout="", stderr="", pipeline_state=pipeline_state, attempt_id=attempt_id,
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_failed_rerun_preserves_previous_selected(self):
        video = self.tmp / "C001.mp4"
        clip = self._mark({"id": "C001"}, "selected", pipeline_state="SELECTED", video=video, attempt_id="a1")
        self.assertEqual(clip["master_batch"]["pipeline_state"], "SELECTED")
        clip = self._mark(clip, "failed", pipeline_state="FAILED", video=None, attempt_id="a2")
        mb = clip["master_batch"]
        self.assertEqual(mb["status"], "failed")
        self.assertEqual(mb["previous_selected"]["video_path"], str(video))
        self.assertEqual(mb["previous_selected"]["attempt_id"], "a1")
        # a further failure still carries the original selected evidence
        clip = self._mark(clip, "failed", pipeline_state="FAILED", video=None, attempt_id="a3")
        self.assertEqual(clip["master_batch"]["previous_selected"]["attempt_id"], "a1")
        # a new SELECTED supersedes it (and the record is dropped from the live state)
        clip = self._mark(clip, "selected", pipeline_state="SELECTED", video=video, attempt_id="a4")
        self.assertNotIn("previous_selected", clip["master_batch"])

    def test_attempts_are_not_capped(self):
        clip = {"id": "C001"}
        for i in range(8):
            clip = self._mark(clip, "failed", pipeline_state="FAILED", attempt_id=f"a{i}")
        attempts = clip["master_batch"]["attempts"]
        self.assertEqual(len(attempts), 8)
        self.assertEqual([a["attempt_id"] for a in attempts], [f"a{i}" for i in range(8)])

    def test_uses_shared_atomic_writer(self):
        self.assertIs(mbr.atomic_write_json, atomic_io.atomic_write_json)
        path = self.tmp / "p.json"
        mbr.atomic_write_json(path, {"a": 1})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
        self.assertFalse(list(self.tmp.glob("*.tmp*")))


class TimeoutTests(_Tmp):
    def test_timeout_records_failed_render_interrupts_comfy_and_continues(self):
        args = types.SimpleNamespace(timeout=1.0, qa_loop=False)
        states = []
        with patch.object(mbr.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired(cmd=["gen"], timeout=1.0, output="partial", stderr=None)), \
                patch.object(mbr, "comfy_interrupt", return_value=True) as interrupt, \
                patch.object(mbr, "_HAS_STORE", True), \
                patch.object(mbr, "set_attempt_state", lambda db, aid, state: states.append((aid, state))):
            proc, video = mbr.run_generator(["gen"], args=args, clip_id="C001", db=object(), attempt_id="a1")
        self.assertEqual(proc.returncode, mbr.TIMEOUT_RETURNCODE)
        self.assertIsNone(video)
        self.assertEqual(states, [("a1", "FAILED_RENDER")])
        interrupt.assert_called_once()
        self.assertIn("TimeoutExpired", proc.stderr)
        self.assertEqual(proc.stdout, "partial")

    def test_timeout_without_store_still_interrupts(self):
        args = types.SimpleNamespace(timeout=1.0, qa_loop=False)
        with patch.object(mbr.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired(cmd=["gen"], timeout=1.0)), \
                patch.object(mbr, "comfy_interrupt", return_value=False) as interrupt:
            proc, _ = mbr.run_generator(["gen"], args=args, clip_id="C001", db=None, attempt_id=None)
        self.assertEqual(proc.returncode, mbr.TIMEOUT_RETURNCODE)
        interrupt.assert_called_once()

    def test_normal_completion_passes_through(self):
        args = types.SimpleNamespace(timeout=1.0, qa_loop=False)
        done = subprocess.CompletedProcess(["gen"], 0, stdout="Done. Clip at:\n out.mp4\n", stderr="")
        with patch.object(mbr.subprocess, "run", return_value=done):
            proc, video = mbr.run_generator(["gen"], args=args, clip_id="C001")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(video.name, "out.mp4")

    def test_comfy_interrupt_posts_to_interrupt(self):
        opened = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        def fake_urlopen(req, timeout=0):
            opened["url"] = req.full_url
            opened["method"] = req.get_method()
            return _Resp()

        with patch.object(mbr.urllib.request, "urlopen", fake_urlopen):
            self.assertTrue(mbr.comfy_interrupt("http://fake:8188"))
        self.assertEqual(opened, {"url": "http://fake:8188/interrupt", "method": "POST"})
        with patch.object(mbr.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertFalse(mbr.comfy_interrupt("http://fake:8188"))


class GpuLockInMainTests(_Tmp):
    def _task(self):
        task = self.tmp / "task"
        (task / "clips").mkdir(parents=True)
        (task / "progress.json").write_text(json.dumps({"clip_ids": ["C001"]}), encoding="utf-8")
        gen = self.tmp / "gen.py"
        gen.write_text("print('x')\n", encoding="utf-8")
        return task, gen

    def _main(self, *extra):
        task, gen = self._task()
        argv = ["--task-dir", str(task), "--generator", str(gen), "--style-profile", "generic", *extra]
        with patch.object(mbr, "LOCK_PATH", self.tmp / "runner.lock"), \
                patch.object(mbr, "OWNER_PATH", self.tmp / "owner.json"), \
                patch.object(mbr, "open_production_store", return_value=None), \
                patch.object(mbr, "run_clip", return_value=True) as run_clip:
            rc = mbr.main(argv)
        return rc, run_clip

    def test_main_holds_shared_lock_during_clips_and_releases(self):
        seen = {}

        def spy_run_clip(**kw):
            seen["held_during"] = gpu_lock.is_held_by_other(
                lock_path=self.tmp / "runner.lock", owner_path=self.tmp / "owner.json")
            seen["owner"] = json.loads((self.tmp / "owner.json").read_text())
            return True

        task, gen = self._task()
        argv = ["--task-dir", str(task), "--generator", str(gen), "--style-profile", "generic"]
        with patch.object(mbr, "LOCK_PATH", self.tmp / "runner.lock"), \
                patch.object(mbr, "OWNER_PATH", self.tmp / "owner.json"), \
                patch.object(mbr, "open_production_store", return_value=None), \
                patch.object(mbr, "run_clip", side_effect=spy_run_clip):
            self.assertEqual(mbr.main(argv), 0)
        self.assertEqual(seen["owner"]["holder"], "master_batch_runner")
        self.assertEqual(seen["owner"]["pid"], os.getpid())
        self.assertFalse(seen["held_during"], "our own lock is not 'other'")
        self.assertEqual(json.loads((self.tmp / "owner.json").read_text())["pid"], 0, "released after the loop")

    def test_main_refuses_when_another_runner_holds_the_lock(self):
        other = gpu_lock.GpuLock("gvd_watcher", lock_path=self.tmp / "runner.lock", owner_path=self.tmp / "owner.json")
        other.acquire()
        try:
            rc, run_clip = self._main()
        finally:
            other.release()
        self.assertEqual(rc, 3)
        run_clip.assert_not_called()

    def test_dry_run_skips_the_lock(self):
        other = gpu_lock.GpuLock("gvd_watcher", lock_path=self.tmp / "runner.lock", owner_path=self.tmp / "owner.json")
        other.acquire()
        try:
            rc, run_clip = self._main("--dry-run")
        finally:
            other.release()
        self.assertEqual(rc, 0)
        run_clip.assert_called_once()


class PortabilityTests(unittest.TestCase):
    def test_comfy_shared_input_env(self):
        with patch.dict(os.environ, {"COMFY_SHARED_INPUT": "/srv/comfy/input"}):
            mod = importlib.reload(mbr)
            try:
                self.assertEqual(mod.COMFY_SHARED_INPUT, Path("/srv/comfy/input"))
            finally:
                os.environ.pop("COMFY_SHARED_INPUT", None)
                importlib.reload(mbr)
        self.assertEqual(str(mbr.COMFY_SHARED_INPUT), r"A:\Users\rhine\ComfyUI-Shared\input")
        src = (ROOT / "master_batch_runner.py").read_text(encoding="utf-8")
        self.assertEqual(src.count(r"A:\Users\rhine"), 1, "only the env default may carry the literal")


if __name__ == "__main__":
    unittest.main()
