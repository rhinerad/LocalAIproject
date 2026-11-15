#!/usr/bin/env python3
"""Unit tests for gvd_watcher.py: shared finished-clip vocabulary, --force
scoping, the shared GPU lock, "unknown" PID liveness, and the per-clip timeout
that must fire even while the child is silent.  No GPU / ComfyUI / nvidia-smi."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "local_agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gpu_lock  # noqa: E402
import gvd_watcher as w  # noqa: E402
import batch_run_backrooms_gvd as batch  # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.video = self.tmp / "ok.mp4"
        self.video.write_bytes(b"\0" * 20_000)
        self.patches = [
            patch.object(w, "LOG_DIR", self.tmp / "logs"),
            patch.object(w, "AUDIT_LOG", self.tmp / "logs" / "audit.log"),
            patch.object(w, "PID_FILE", self.tmp / "logs" / "gvd_watcher.pid"),
            patch.object(w, "PROGRESS_PATH", self.tmp / "progress.json"),
            patch.object(w, "LOCK_PATH", self.tmp / "runner.lock"),
            patch.object(w, "OWNER_PATH", self.tmp / "owner.json"),
            patch.object(w, "sample_vram", return_value={}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self._td.cleanup()

    def progress(self, **clips):
        return {"clips": clips}


class VocabularyTests(_Tmp):
    def test_watcher_uses_the_batch_already_done(self):
        self.assertIs(w.already_done, batch.already_done)

    def test_selected_clip_counts_as_done(self):
        for entry in (
            {"status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video)},
            {"status": "qa_pending", "pipeline_state": "SELECTED", "video_path": str(self.video)},
            {"status": "selected", "video_path": str(self.video)},
            {"status": "done", "video_path": str(self.video)},
            {"ok": True, "video_path": str(self.video)},
        ):
            with self.subTest(entry=entry):
                self.assertTrue(w.already_done(entry))

    def test_failed_running_and_missing_video_are_not_done(self):
        for entry in (
            None,
            {},
            {"status": "error", "video_path": str(self.video)},
            {"status": "running", "video_path": str(self.video)},
            {"status": "selected", "video_path": str(self.tmp / "missing.mp4")},
        ):
            with self.subTest(entry=entry):
                self.assertFalse(w.already_done(entry))


class PlanTests(_Tmp):
    def test_force_rerun_failed_only_forces_failed_clips(self):
        progress = self.progress(
            C001={"status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video)},
            C002={"status": "error", "error": "boom"},
            C003={"status": "running"},
            C004={"status": "qa_failed", "pipeline_state": "QA_FAILED", "video_path": str(self.video)},
        )
        clips = ["C001", "C002", "C003", "C004", "C005"]
        plan = w.build_plan(progress, clips, force_all=False, force_rerun_failed=True)
        self.assertEqual(plan, [("C002", True), ("C003", False), ("C004", True), ("C005", False)])

    def test_default_never_forces_and_skips_done(self):
        progress = self.progress(
            C001={"status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video)},
            C002={"status": "error"},
        )
        plan = w.build_plan(progress, ["C001", "C002", "C003"], force_all=False, force_rerun_failed=False)
        self.assertEqual(plan, [("C002", False), ("C003", False)])

    def test_force_all_forces_everything_including_selected(self):
        progress = self.progress(
            C001={"status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video)},
        )
        plan = w.build_plan(progress, ["C001", "C002"], force_all=True, force_rerun_failed=False)
        self.assertEqual(plan, [("C001", True), ("C002", True)])

    def test_main_refuses_force_all_without_confirmation(self):
        with patch.object(w, "acquire_pid_lock", side_effect=AssertionError("must not lock")), \
                patch.object(w, "run_clip", side_effect=AssertionError("must not run")), \
                patch.dict(sys.modules, {"gvd_pipeline_rules": types.SimpleNamespace(
                    write_rules_lock=lambda: self.tmp / "rules.json")}):
            rc = w.main(["--force-all", "--clip", "C001"])
        self.assertEqual(rc, 2)
        log = (self.tmp / "logs" / "audit.log").read_text(encoding="utf-8")
        self.assertIn("force_all_requested", log)

    def test_main_force_all_with_confirmation_warns_and_proceeds(self):
        calls = []

        def fake_run(cid, *, python, silent, force, timeout_s):
            calls.append((cid, force))
            return 0, "", 0.1

        with patch.object(w, "run_clip", side_effect=fake_run), \
                patch.object(w, "post_clip_sanitize", lambda: None), \
                patch.dict(sys.modules, {"gvd_pipeline_rules": types.SimpleNamespace(
                    write_rules_lock=lambda: self.tmp / "rules.json")}):
            with patch("sys.stderr") as err:
                w.main(["--force-all", "--yes-overwrite-selected", "--clip", "C001"])
        self.assertEqual(calls, [("C001", True)])
        printed = "".join(str(c.args[0]) for c in err.write.call_args_list)
        self.assertIn("RE-RENDERS EVERY CLIP", printed)


class PidLivenessAndLockTests(_Tmp):
    def test_pid_alive_returns_unknown_when_probe_fails(self):
        with patch.object(gpu_lock, "pid_alive", return_value=None):
            self.assertEqual(w._pid_alive(4242), "unknown")
        with patch.object(gpu_lock, "pid_alive", return_value=True):
            self.assertIs(w._pid_alive(4242), True)
        with patch.object(gpu_lock, "pid_alive", return_value=False):
            self.assertIs(w._pid_alive(4242), False)
        self.assertIs(w._pid_alive(0), False)

    def test_unknown_liveness_does_not_steal_the_lock(self):
        (self.tmp / "owner.json").write_text(json.dumps({"pid": 4242, "holder": "other"}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                w.acquire_pid_lock()
        self.assertIn("liveness=unknown", str(ctx.exception))
        self.assertEqual(json.loads((self.tmp / "owner.json").read_text())["pid"], 4242)

    def test_lock_is_the_shared_gpu_lock_and_is_released(self):
        w.acquire_pid_lock()
        try:
            owner = json.loads((self.tmp / "owner.json").read_text())
            self.assertEqual(owner["pid"], os.getpid())
            self.assertEqual(owner["holder"], "gvd_watcher")
            with self.assertRaises(gpu_lock.GpuLockHeld):
                gpu_lock.GpuLock("mbr", lock_path=self.tmp / "runner.lock", owner_path=self.tmp / "owner.json").acquire()
            self.assertEqual((self.tmp / "logs" / "gvd_watcher.pid").read_text().strip(), str(os.getpid()))
        finally:
            w.release_pid_lock()
        self.assertEqual(json.loads((self.tmp / "owner.json").read_text())["pid"], 0)
        self.assertFalse((self.tmp / "logs" / "gvd_watcher.pid").exists())

    def test_stale_dead_owner_is_replaced(self):
        (self.tmp / "owner.json").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=False):
            w.acquire_pid_lock()
        try:
            self.assertEqual(json.loads((self.tmp / "owner.json").read_text())["pid"], os.getpid())
        finally:
            w.release_pid_lock()


class RunClipTimeoutTests(_Tmp):
    def _script(self, body: str) -> Path:
        p = self.tmp / "fake_batch.py"
        p.write_text(body, encoding="utf-8")
        return p

    def test_timeout_fires_while_child_is_silent(self):
        script = self._script("import time\nwhile True:\n    time.sleep(0.2)\n")
        with patch.object(w, "BATCH_SCRIPT", script):
            t0 = time.monotonic()
            rc, blob, elapsed = w.run_clip("C001", python=Path(sys.executable), timeout_s=1.5, poll_s=0.2)
        self.assertLess(time.monotonic() - t0, 15.0, "timeout must not wait for child output")
        self.assertNotEqual(rc, 0)
        self.assertIn("TIMEOUT", blob)
        self.assertGreaterEqual(elapsed, 1.5)
        log = (self.tmp / "logs" / "audit.log").read_text(encoding="utf-8")
        self.assertIn("clip_timeout", log)

    def test_normal_child_output_is_captured_and_rc_passes_through(self):
        script = self._script(
            "import sys\nprint('line one'); print('line two'); sys.exit(0 if sys.argv[-1]=='C001' else 7)\n"
        )
        with patch.object(w, "BATCH_SCRIPT", script), patch("sys.stdout"):
            rc, blob, _ = w.run_clip("C001", python=Path(sys.executable), timeout_s=30, poll_s=0.1)
            rc2, _, _ = w.run_clip("C002", python=Path(sys.executable), timeout_s=30, poll_s=0.1)
        self.assertEqual(rc, 0)
        self.assertEqual(rc2, 7)
        self.assertIn("line one\n", blob)
        self.assertIn("line two\n", blob)


class KeepaliveVocabularyTests(unittest.TestCase):
    def test_keepalive_counts_selected_and_uses_env_root(self):
        text = (ROOT / "gvd_watcher_keepalive.ps1").read_text(encoding="utf-8")
        self.assertIn("pipeline_state -eq 'SELECTED'", text)
        self.assertIn("status -eq 'selected'", text)
        self.assertIn("status -eq 'done'", text)
        self.assertIn("$env:GVD_ROOT", text)
        self.assertNotIn("COMFYUI_STORY_HANDOFF_2026-08-09'", text.split("\n")[3])


if __name__ == "__main__":
    unittest.main()
