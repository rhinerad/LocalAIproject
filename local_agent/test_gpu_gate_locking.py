#!/usr/bin/env python3
"""Cross-process locking, approval TTL, and read-only snapshot checks.

Covers audit finding 11 (gate files wiped on transient read errors; snapshot
saved; thread-only lock) for gpu_gate and file_edit_gate. Stdlib only.

Run:
    python -m unittest local_agent/test_gpu_gate_locking.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import file_edit_gate
import gpu_gate

# A separate process tries to take the sidecar lock without blocking.
_PROBE = r"""
import os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
try:
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("free")
except OSError:
    print("held")
"""


def _probe_lock(path: Path) -> str:
    proc = subprocess.run([sys.executable, "-I", "-c", _PROBE, str(path)],
                          capture_output=True, text=True, timeout=60)
    return proc.stdout.strip()


class GpuGateStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = gpu_gate.STATE_FILE
        gpu_gate.STATE_FILE = Path(self.tmp.name) / "gate.json"
        gpu_gate._LAST_GOOD = None
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        gpu_gate.STATE_FILE = self._old
        gpu_gate._LAST_GOOD = None

    def _write(self, **fields) -> None:
        state = {"mode": "ask", "pending": [], "approved_keys": [], "history": []}
        state.update(fields)
        gpu_gate.STATE_FILE.write_text(json.dumps(state), encoding="utf-8")

    # 3(d): approved_keys records + TTL
    def test_approval_is_a_timestamped_record_and_one_shot(self):
        req = gpu_gate.request("vision", source="test", key="k1")
        gpu_gate.decide(req["request"]["id"], "approve")
        raw = json.loads(gpu_gate.STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual("k1", raw["approved_keys"][0]["key"])
        self.assertAlmostEqual(time.time(), raw["approved_keys"][0]["approved_at"], delta=5)
        self.assertTrue(gpu_gate.request("vision", source="test", key="k1")["granted"])
        self.assertFalse(gpu_gate.request("vision", source="test", key="k1")["granted"])

    def test_expired_approval_is_dropped_on_load(self):
        stale = time.time() - gpu_gate.APPROVAL_TTL_SECONDS - 1
        self._write(approved_keys=[{"key": "old", "approved_at": stale},
                                   {"key": "fresh", "approved_at": time.time()}])
        self.assertEqual(["fresh"], [e["key"] for e in gpu_gate.snapshot()["approved_keys"]])
        self.assertFalse(gpu_gate.request("w", source="t", key="old")["granted"])
        self.assertTrue(gpu_gate.request("w", source="t", key="fresh")["granted"])

    def test_legacy_bare_string_entries_are_still_read(self):
        self._write(approved_keys=["legacy"], updated_at=time.time())
        self.assertEqual("legacy", gpu_gate.snapshot()["approved_keys"][0]["key"])
        self.assertTrue(gpu_gate.request("w", source="t", key="legacy")["granted"])

    def test_legacy_entry_uses_updated_at_for_its_ttl(self):
        self._write(approved_keys=["legacy"],
                    updated_at=time.time() - gpu_gate.APPROVAL_TTL_SECONDS - 1)
        self.assertEqual([], gpu_gate.snapshot()["approved_keys"])
        self.assertFalse(gpu_gate.request("w", source="t", key="legacy")["granted"])

    # 3(a): _load blank only on missing / unparseable; other OSError propagates
    def test_missing_or_corrupt_file_loads_blank(self):
        self.assertEqual("ask", gpu_gate._load()["mode"])
        gpu_gate.STATE_FILE.write_text("{not json", encoding="utf-8")
        self.assertEqual([], gpu_gate._load()["pending"])

    def test_load_reraises_other_oserror_and_request_fails_closed(self):
        gpu_gate.STATE_FILE.mkdir()  # a directory in the way: IsADirectory/Permission error
        with self.assertRaises(OSError):
            gpu_gate._load()
        with self.assertRaises(OSError):
            gpu_gate.request("w", source="t", key="k")
        self.assertTrue(gpu_gate.STATE_FILE.is_dir(), "nothing may be written over the error")

    # 3(b): snapshot read-only
    def test_snapshot_never_writes(self):
        self.assertFalse(gpu_gate.STATE_FILE.exists())
        gpu_gate.snapshot()
        self.assertFalse(gpu_gate.STATE_FILE.exists())
        self._write(pending=[{"id": "gpu_x", "key": "x", "workload": "w"}])
        before = gpu_gate.STATE_FILE.read_bytes()
        self.assertEqual("gpu_x", gpu_gate.snapshot()["pending"][0]["id"])
        self.assertEqual(before, gpu_gate.STATE_FILE.read_bytes())

    def test_snapshot_returns_last_good_state_on_read_error(self):
        req = gpu_gate.request("w", source="t", key="k")
        gpu_gate.STATE_FILE.unlink()
        gpu_gate.STATE_FILE.mkdir()
        snap = gpu_gate.snapshot()
        self.assertTrue(snap.get("stale"))
        self.assertEqual(req["request"]["id"], snap["pending"][0]["id"])
        self.assertTrue(gpu_gate.STATE_FILE.is_dir())

    def test_snapshot_without_history_returns_blank_on_read_error(self):
        gpu_gate.STATE_FILE.mkdir()
        snap = gpu_gate.snapshot()
        self.assertEqual("ask", snap["mode"])
        self.assertEqual([], snap["pending"])

    # 3(e): atomic saves
    def test_save_is_atomic_and_leaves_no_temp_files(self):
        gpu_gate.request("w", source="t", key="k")
        gpu_gate.set_mode("block")
        names = sorted(os.listdir(self.tmp.name))
        self.assertEqual(["gate.json", "gate.json.lock"], names)
        self.assertEqual("block", json.loads(gpu_gate.STATE_FILE.read_text(encoding="utf-8"))["mode"])

    # 3(c): cross-process lock
    def test_file_lock_excludes_other_processes(self):
        with gpu_gate._file_lock():
            self.assertEqual("held", _probe_lock(gpu_gate._lock_path()))
        self.assertEqual("free", _probe_lock(gpu_gate._lock_path()))

    def test_lock_sidecar_sits_next_to_state_file(self):
        self.assertEqual(gpu_gate.STATE_FILE.parent, gpu_gate._lock_path().parent)
        self.assertEqual("gate.json.lock", gpu_gate._lock_path().name)

    def test_every_mutator_holds_the_file_lock(self):
        import contextlib
        taken: list[str] = []

        @contextlib.contextmanager
        def counting():
            taken.append("lock")
            yield

        with patch.object(gpu_gate, "_file_lock", counting):
            gpu_gate.set_mode("ask")
            req = gpu_gate.request("w", source="t", key="k")
            gpu_gate.decide(req["request"]["id"], "deny")
        self.assertEqual(3, len(taken))

    def test_lock_timeout_is_an_oserror(self):
        path = gpu_gate._lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        holder = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            gpu_gate._acquire(holder)
            with patch.object(gpu_gate, "LOCK_TIMEOUT_SECONDS", 0.2):
                with self.assertRaises(OSError):
                    with gpu_gate._file_lock():
                        pass
        finally:
            gpu_gate._release(holder)
            os.close(holder)


class FileEditGateStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = file_edit_gate.STATE_FILE
        file_edit_gate.STATE_FILE = Path(self.tmp.name) / "file_edit_gate.json"
        file_edit_gate._LAST_GOOD = None
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        file_edit_gate.STATE_FILE = self._old
        file_edit_gate._LAST_GOOD = None

    def test_missing_or_corrupt_file_loads_blank(self):
        self.assertEqual([], file_edit_gate._load()["pending"])
        file_edit_gate.STATE_FILE.write_text("nope", encoding="utf-8")
        self.assertEqual([], file_edit_gate._load()["approved"])

    def test_load_reraises_other_oserror(self):
        file_edit_gate.STATE_FILE.mkdir()
        with self.assertRaises(OSError):
            file_edit_gate._load()
        with self.assertRaises(OSError):
            file_edit_gate.request("x.py", "print(1)")

    def test_snapshot_never_writes_and_survives_read_error(self):
        file_edit_gate.snapshot()
        self.assertFalse(file_edit_gate.STATE_FILE.exists())
        pending = file_edit_gate.request("x.py", "print(1)")
        before = file_edit_gate.STATE_FILE.read_bytes()
        file_edit_gate.snapshot()
        self.assertEqual(before, file_edit_gate.STATE_FILE.read_bytes())
        file_edit_gate.STATE_FILE.unlink()
        file_edit_gate.STATE_FILE.mkdir()
        snap = file_edit_gate.snapshot()
        self.assertTrue(snap["stale"])
        self.assertEqual(pending["request"]["id"], snap["pending"][0]["id"])

    def test_save_is_atomic_with_no_fixed_tmp_name(self):
        req = file_edit_gate.request("x.py", "print(1)")
        file_edit_gate.decide(req["request"]["id"], True)
        self.assertEqual(["file_edit_gate.json"], os.listdir(self.tmp.name))
        self.assertTrue(file_edit_gate.request("x.py", "print(1)")["granted"])


if __name__ == "__main__":
    unittest.main()
