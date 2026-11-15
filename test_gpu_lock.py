#!/usr/bin/env python3
"""Unit tests for the shared GPU render lock (gpu_lock.py) and its adoption by
backrooms_watch.BackroomsWatch.  No GPU, no ComfyUI, no nvidia-smi."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "local_agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gpu_lock  # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.lock_path = self.tmp / "runner.lock"
        self.owner_path = self.tmp / "owner.json"

    def tearDown(self):
        self._td.cleanup()

    def lock(self, holder="t"):
        return gpu_lock.GpuLock(holder, lock_path=self.lock_path, owner_path=self.owner_path)


class GpuLockTests(_Tmp):
    def test_acquire_writes_owner_json_and_release_marks_released(self):
        lk = self.lock("unit")
        lk.acquire()
        try:
            owner = json.loads(self.owner_path.read_text(encoding="utf-8"))
            self.assertEqual(owner["pid"], os.getpid())
            self.assertEqual(owner["holder"], "unit")
            self.assertIn("started_at", owner)
            self.assertIn("started", owner)  # legacy BackroomsWatch key
            self.assertTrue(lk.held)
        finally:
            lk.release()
        released = json.loads(self.owner_path.read_text(encoding="utf-8"))
        self.assertEqual(released["pid"], 0)
        self.assertEqual(released["purpose"], "released")
        self.assertFalse(lk.held)
        self.assertFalse(list(self.tmp.glob("*.tmp.*")), "atomic temp files must not linger")

    def test_second_holder_is_refused_by_the_os_lock(self):
        first = self.lock("first")
        first.acquire()
        try:
            with self.assertRaises(gpu_lock.GpuLockHeld):
                self.lock("second").acquire()
        finally:
            first.release()
        # After release the lock is free again.
        second = self.lock("second")
        second.acquire()
        second.release()

    def test_stale_owner_with_dead_pid_is_replaced(self):
        self.owner_path.write_text(json.dumps({"pid": 4242, "holder": "dead"}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=False):
            lk = self.lock("new")
            lk.acquire()
            try:
                self.assertEqual(json.loads(self.owner_path.read_text())["pid"], os.getpid())
            finally:
                lk.release()

    def test_unknown_pid_liveness_never_steals_the_lock(self):
        self.owner_path.write_text(json.dumps({"pid": 4242, "holder": "maybe-alive"}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=None):
            with self.assertRaises(gpu_lock.GpuLockHeld) as ctx:
                self.lock("new").acquire()
            self.assertEqual(ctx.exception.owner.get("pid"), 4242)
        # the stale owner record is untouched and the OS lock was not kept
        self.assertEqual(json.loads(self.owner_path.read_text())["pid"], 4242)
        with patch.object(gpu_lock, "pid_alive", return_value=False):
            lk = self.lock("new")
            lk.acquire()
            lk.release()

    def test_live_other_pid_is_refused(self):
        self.owner_path.write_text(json.dumps({"pid": 4242, "holder": "live"}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=True):
            with self.assertRaises(gpu_lock.GpuLockHeld):
                self.lock("new").acquire()

    def test_context_manager_releases(self):
        with self.lock("ctx") as lk:
            self.assertTrue(lk.held)
        self.assertFalse(lk.held)
        self.assertEqual(json.loads(self.owner_path.read_text())["pid"], 0)

    def test_owner_status_vocabulary(self):
        self.assertEqual(gpu_lock.owner_status({}), "free")
        self.assertEqual(gpu_lock.owner_status({"pid": 0}), "free")
        self.assertEqual(gpu_lock.owner_status({"pid": os.getpid()}), "self")
        with patch.object(gpu_lock, "pid_alive", return_value=None):
            self.assertEqual(gpu_lock.owner_status({"pid": 99}), "held")
        with patch.object(gpu_lock, "pid_alive", return_value=False):
            self.assertEqual(gpu_lock.owner_status({"pid": 99}), "free")


class PidAliveTests(unittest.TestCase):
    def test_own_pid_is_alive(self):
        self.assertIs(gpu_lock.pid_alive(os.getpid()), True)

    def test_nonsense_pids_are_dead(self):
        self.assertIs(gpu_lock.pid_alive(0), False)
        self.assertIs(gpu_lock.pid_alive(None), False)
        self.assertIs(gpu_lock.pid_alive("x"), False)

    def test_probe_failure_is_unknown_not_dead(self):
        broken = types.SimpleNamespace(pid_exists=lambda pid: (_ for _ in ()).throw(RuntimeError("boom")))
        with patch.object(gpu_lock, "psutil", broken):
            self.assertIsNone(gpu_lock.pid_alive(1234))
        with patch.object(gpu_lock, "psutil", None), patch.object(gpu_lock.os, "name", "nt"), \
                patch.object(gpu_lock.subprocess, "check_output", side_effect=OSError("no tasklist")):
            self.assertIsNone(gpu_lock.pid_alive(1234))


class IsHeldByOtherTests(_Tmp):
    def probe(self):
        return gpu_lock.is_held_by_other(lock_path=self.lock_path, owner_path=self.owner_path)

    def test_nothing_held(self):
        self.assertFalse(self.probe())

    def test_live_other_owner_is_held(self):
        self.owner_path.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        with patch.object(gpu_lock, "pid_alive", return_value=True):
            self.assertTrue(self.probe())
        with patch.object(gpu_lock, "pid_alive", return_value=None):
            self.assertTrue(self.probe(), "unknown liveness must read as held")

    def test_our_own_lock_is_not_other(self):
        with self.lock("me"):
            self.assertFalse(self.probe())

    def test_os_lock_without_owner_record_is_held(self):
        lk = self.lock("os-only")
        lk.acquire()
        try:
            # simulate an owner file that cannot name the holder
            self.owner_path.write_text("{}", encoding="utf-8")
            self.assertTrue(self.probe())
        finally:
            lk.release()

    def test_probe_errors_fail_closed(self):
        with patch.object(gpu_lock, "read_owner", side_effect=OSError("disk")):
            self.assertTrue(self.probe())


class BackroomsWatchLockTests(_Tmp):
    """backrooms_watch imports on Linux (thermal_guard is lazy) and uses GpuLock."""

    def test_module_imports_without_work_dir_and_guard_is_injectable(self):
        import backrooms_watch

        fake = types.SimpleNamespace(EMERGENCY_C=85, wait_before_render=lambda p: None,
                                     wait_after_render=lambda p: None)
        backrooms_watch.set_thermal_guard(fake)
        try:
            self.assertIs(backrooms_watch.thermal_guard_module(), fake)
        finally:
            backrooms_watch.set_thermal_guard(None)

    def test_acquire_uses_shared_lock_and_releases_on_preflight_failure(self):
        import backrooms_watch

        with patch.object(backrooms_watch, "RUNTIME", self.tmp), \
                patch.object(backrooms_watch, "LOCK_PATH", self.lock_path), \
                patch.object(backrooms_watch, "OWNER_PATH", self.owner_path), \
                patch.object(backrooms_watch, "port_open", return_value=True):
            w = backrooms_watch.BackroomsWatch()
            with self.assertRaises(RuntimeError):
                w.acquire()  # port 8188 "owned" -> refuse, and the lock must be released
            self.assertIsNone(w.lock_file)
            self.assertEqual(json.loads(self.owner_path.read_text())["pid"], 0)
            self.assertFalse(gpu_lock.is_held_by_other(lock_path=self.lock_path, owner_path=self.owner_path))

    def test_acquire_refuses_when_another_renderer_holds_the_lock(self):
        import backrooms_watch

        other = self.lock("gvd_watcher")
        other.acquire()
        try:
            with patch.object(backrooms_watch, "RUNTIME", self.tmp), \
                    patch.object(backrooms_watch, "LOCK_PATH", self.lock_path), \
                    patch.object(backrooms_watch, "OWNER_PATH", self.owner_path):
                w = backrooms_watch.BackroomsWatch()
                with self.assertRaises(RuntimeError) as ctx:
                    w.acquire()
                self.assertIn("Another renderer", str(ctx.exception))
        finally:
            other.release()


if __name__ == "__main__":
    unittest.main()
