"""Synthetic-only age sealer: chats/ lock, no plaintext tempfile, round-trip."""
from __future__ import annotations

import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sealed_export

_HELPER = HERE / "sealed_export.py"
_SUBMIT = HERE / "worker_farm" / "submit_distillation.py"
_CANARY = sealed_export.SYNTHETIC_FIXTURE.encode("utf-8")
_FORBIDDEN_HELPER_RE = re.compile(
    r"NamedTemporaryFile|store\.load|plaintext_sha256"
)


class _PlaintextDiskProbe:
    """Scan dest + process temp dirs for the fixture bytes while seal runs."""

    def __init__(self, watch: list[Path], canary: bytes):
        self.watch = watch
        self.canary = canary
        self.hits: list[str] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._scan()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._scan()
            time.sleep(0.01)

    def _scan(self) -> None:
        for root in self.watch:
            try:
                exists = root.is_dir()
            except OSError:
                continue
            if not exists:
                continue
            try:
                paths = list(root.rglob("*"))
            except OSError:
                continue
            for path in paths:
                try:
                    if not path.is_file():
                        continue
                    data = path.read_bytes()
                except OSError:
                    continue
                if self.canary in data:
                    name = str(path)
                    if name not in self.hits:
                        self.hits.append(name)


class SealedExportTests(unittest.TestCase):
    def test_fixture_matches_distill_sample_source(self):
        text = _SUBMIT.read_text(encoding="utf-8")
        match = re.search(r'^SAMPLE = """(.*)"""\s*$', text, re.M)
        self.assertIsNotNone(match)
        sample = match.group(1).encode("utf-8").decode("unicode_escape")
        self.assertEqual(sealed_export.SYNTHETIC_FIXTURE, sample)

    def test_helper_grep_lock_forbids_plaintext_temp_and_chat_store(self):
        source = _HELPER.read_text(encoding="utf-8")
        self.assertIsNone(_FORBIDDEN_HELPER_RE.search(source))
        self.assertIn("assert_not_chat_source", source)
        self.assertIn("local_agent/chats/", source)
        self.assertNotIn("NamedTemporaryFile", source)

    def test_grep_lock_fails_on_deliberate_chats_read(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "sealed_export.py"
            bad.write_text("import store\nstore.load('x')\nNamedTemporaryFile()\n",
                           encoding="utf-8")
            hits = _FORBIDDEN_HELPER_RE.findall(bad.read_text(encoding="utf-8"))
            self.assertTrue(hits)

    def test_chats_path_is_refused_before_any_read(self):
        trap = HERE / "chats" / "must_not_be_read.json"
        with tempfile.TemporaryDirectory() as td:
            identity, recipient = sealed_export.generate_identity()
            with self.assertRaises(sealed_export.SealedExportError) as raised:
                sealed_export.seal_from_path(
                    trap, recipient=recipient, dest_dir=Path(td))
            self.assertIn("chats", str(raised.exception).lower())
            self.assertFalse(trap.is_file())
            relative = Path("chats") / "other.json"
            with self.assertRaises(sealed_export.SealedExportError) as raised:
                sealed_export.assert_not_chat_source(relative)
            self.assertIn("chats", str(raised.exception).lower())

    def test_cli_source_under_chats_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            code = sealed_export.main([
                "--source", str(HERE / "chats" / "nope.json"),
                "--recipient", "age1invalid",
                "--out-dir", td,
            ])
            self.assertEqual(2, code)

    def test_synthetic_fixture_seals_and_round_trips(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            identity, recipient = sealed_export.generate_identity()
            record = sealed_export.seal_synthetic(recipient=recipient, dest_dir=dest)
            path = Path(record["path"])
            self.assertTrue(path.is_file())
            self.assertRegex(record["filename"], r"^sealed_export_[0-9a-f]{12}\.age$")
            self.assertTrue(record["filename"].endswith(".age"))
            self.assertNotIn("plaintext_sha256", record)
            blob = path.read_bytes()
            self.assertTrue(blob.startswith(b"age-encryption.org/v1\n"))
            self.assertNotIn(_CANARY, blob)
            plain = sealed_export.decrypt_age_for_tests(blob, identity)
            self.assertEqual(_CANARY, plain)

    def test_no_plaintext_hits_disk_during_seal(self):
        with tempfile.TemporaryDirectory() as td:
            scratch = Path(td)
            dest = scratch / "out"
            dest.mkdir()
            proc_tmp = scratch / "proc_tmp"
            proc_tmp.mkdir()
            identity, recipient = sealed_export.generate_identity()
            previous_tempdir = tempfile.tempdir
            tempfile.tempdir = str(proc_tmp)
            probe = _PlaintextDiskProbe([scratch], _CANARY)
            probe.start()
            try:
                record = sealed_export.seal_synthetic(
                    recipient=recipient, dest_dir=dest)
            finally:
                probe.stop()
                tempfile.tempdir = previous_tempdir
            self.assertEqual(
                [], probe.hits,
                f"plaintext fixture appeared on disk: {probe.hits}")
            path = Path(record["path"])
            self.assertTrue(path.is_file())
            self.assertNotIn(_CANARY, path.read_bytes())
            self.assertEqual(
                _CANARY,
                sealed_export.decrypt_age_for_tests(path.read_bytes(), identity),
            )


if __name__ == "__main__":
    unittest.main()
