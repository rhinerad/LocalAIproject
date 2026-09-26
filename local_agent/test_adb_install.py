#!/usr/bin/env python3
"""Tests for the refuse-by-default ADB wrapper. Fake adb only; no live install."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import adb_install


SERIAL = "PIXELSERIAL01"
FINGERPRINT = "google/tokay/tokay:16/BP2A.250605.031.A3/fake:user/release-keys"


class FakeAdb:
    def __init__(
        self,
        *,
        devices: str = f"List of devices attached\n{SERIAL}\tdevice\n",
        fingerprint: str = FINGERPRINT,
        devices_rc: int = 0,
        getprop_rc: int = 0,
        install_rc: int = 0,
        raise_on: str | None = None,
    ) -> None:
        self.devices = devices
        self.fingerprint = fingerprint
        self.devices_rc = devices_rc
        self.getprop_rc = getprop_rc
        self.install_rc = install_rc
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, adb, args, *, timeout=30):
        argv = list(args)
        self.calls.append(argv)
        if self.raise_on and self.raise_on in argv:
            raise OSError("adb missing")
        if argv == ["devices"]:
            return subprocess.CompletedProcess(
                argv, self.devices_rc, self.devices, "")
        if argv[:4] == ["-s", SERIAL, "shell", "getprop"]:
            return subprocess.CompletedProcess(
                argv, self.getprop_rc, self.fingerprint + "\n", "")
        if len(argv) >= 4 and argv[0] == "-s" and argv[2] == "install":
            return subprocess.CompletedProcess(
                argv, self.install_rc, "Success\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected")

    def install_calls(self) -> list[list[str]]:
        return [c for c in self.calls if "install" in c]


def _ledger(serial: str, sha: str, **extra) -> dict:
    row = {
        "name": "pixel-operator",
        "serial": serial,
        "build_fingerprint": FINGERPRINT,
        "approved_at": 1_725_000_000,
        "approved_apk_sha256": sha,
        "revoked_at": None,
    }
    row.update(extra)
    return {"version": 1, "devices": {serial: row}}


class AdbInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.apk = self.dir / "companion.apk"
        self.apk.write_bytes(b"PK\x03\x04fake-apk-body-not-installed")
        self.sha = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        self.ledger = self.dir / "adb_trusted_devices.json"
        self.jsonl = self.dir / "adb_install.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_ledger(self, data: dict) -> None:
        self.ledger.write_text(json.dumps(data), encoding="utf-8")

    def _run(self, fake: FakeAdb, **kwargs) -> dict:
        opts = dict(
            apk=self.apk,
            serial=SERIAL,
            ledger_path=self.ledger,
            adb="adb-not-on-path-for-tests",
            adb_runner=fake,
            jsonl_path=self.jsonl,
            write_jsonl=True,
        )
        opts.update(kwargs)
        return adb_install.trusted_install(**opts)

    def test_module_does_not_import_agent_or_lxmf(self) -> None:
        tree = ast.parse((HERE / "adb_install.py").read_text(encoding="utf8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        for banned in ("agent", "tools", "lxmf_agent", "router"):
            self.assertNotIn(banned, names)
        self.assertIn("apk_review", names)

    def test_missing_ledger_refuses_without_install(self) -> None:
        fake = FakeAdb()
        row = self._run(fake)
        self.assertEqual(adb_install.OUTCOME_REFUSED, row["outcome"])
        self.assertIn("ledger_missing", row["reasons"])
        self.assertEqual([], fake.install_calls())
        self.assertEqual([], fake.calls)

    def test_empty_devices_refuses(self) -> None:
        self._write_ledger({"version": 1, "devices": {}})
        fake = FakeAdb()
        row = self._run(fake)
        self.assertEqual(adb_install.OUTCOME_REFUSED, row["outcome"])
        self.assertIn("no_approval_row", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_missing_approved_at_refuses(self) -> None:
        data = _ledger(SERIAL, self.sha)
        del data["devices"][SERIAL]["approved_at"]
        self._write_ledger(data)
        fake = FakeAdb()
        row = self._run(fake)
        self.assertEqual(adb_install.OUTCOME_REFUSED, row["outcome"])
        self.assertIn("approved_at_missing", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_null_approved_at_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha, approved_at=None))
        fake = FakeAdb()
        row = self._run(fake)
        self.assertIn("approved_at_missing", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_revoked_row_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha, revoked_at=1_725_000_100))
        fake = FakeAdb()
        row = self._run(fake)
        self.assertIn("revoked", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_sha256_mismatch_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, "0" * 64))
        fake = FakeAdb()
        row = self._run(fake)
        self.assertIn("sha256_mismatch", row["reasons"])
        self.assertEqual(self.sha, row["sha256"])
        self.assertEqual([], fake.install_calls())

    def test_fingerprint_mismatch_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(fingerprint="other/device/fingerprint")
        row = self._run(fake)
        self.assertIn("fingerprint_mismatch", row["reasons"])
        self.assertEqual([], fake.install_calls())
        self.assertTrue(any(c == ["devices"] for c in fake.calls))
        self.assertFalse(fake.install_calls())

    def test_unauthorized_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(
            devices=f"List of devices attached\n{SERIAL}\tunauthorized\n")
        row = self._run(fake)
        self.assertIn("unauthorized", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_multiple_devices_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(
            devices=(
                "List of devices attached\n"
                f"{SERIAL}\tdevice\n"
                "OTHERSERIAL\tdevice\n"
            ))
        row = self._run(fake)
        self.assertIn("multiple_devices", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_no_device_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(devices="List of devices attached\n")
        row = self._run(fake)
        self.assertIn("no_device", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_wrong_serial_only_device_refuses(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(
            devices="List of devices attached\nOTHERSERIAL\tdevice\n")
        row = self._run(fake)
        self.assertIn("serial_mismatch", row["reasons"])
        self.assertEqual([], fake.install_calls())

    def test_match_dry_run_does_not_install(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb()
        row = self._run(fake, dry_run=True)
        self.assertEqual(adb_install.OUTCOME_DRY_RUN, row["outcome"])
        self.assertEqual([], row["reasons"])
        self.assertEqual([], fake.install_calls())
        self.assertEqual(FINGERPRINT, row["fingerprint_seen"])

    def test_match_calls_install_r_on_fake_adb_only(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb()
        row = self._run(fake)
        self.assertEqual(adb_install.OUTCOME_INSTALLED, row["outcome"])
        self.assertEqual([], row["reasons"])
        installs = fake.install_calls()
        self.assertEqual(1, len(installs))
        self.assertEqual(["-s", SERIAL, "install", "-r", str(self.apk)], installs[0])
        self.assertNotIn(self.apk.read_bytes().decode("latin-1"), json.dumps(row))

    def test_sha_case_insensitive(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha.upper()))
        fake = FakeAdb()
        row = self._run(fake, dry_run=True)
        self.assertEqual(adb_install.OUTCOME_DRY_RUN, row["outcome"])

    def test_log_has_no_apk_body(self) -> None:
        token = b"UNIQUE_APK_BODY_TOKEN_9f3a"
        self.apk.write_bytes(b"PK\x03\x04" + token)
        self.sha = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb()
        row = self._run(fake, dry_run=True)
        blob = self.jsonl.read_text(encoding="utf-8")
        self.assertNotIn("UNIQUE_APK_BODY_TOKEN_9f3a", blob)
        self.assertNotIn("UNIQUE_APK_BODY_TOKEN_9f3a", json.dumps(row))
        self.assertEqual(self.sha, row["sha256"])

    def test_cli_exit_2_on_refuse(self) -> None:
        buf = io.StringIO()
        argv = [
            str(self.apk), "--serial", SERIAL,
            "--ledger", str(self.ledger),
            "--jsonl", str(self.jsonl),
            "--adb", "adb-not-on-path-for-tests",
            "--dry-run",
        ]
        with unittest.mock.patch.object(adb_install, "run_adb", FakeAdb()):
            old = sys.stdout
            try:
                sys.stdout = buf
                rc = adb_install.main(argv)
            finally:
                sys.stdout = old
        self.assertEqual(adb_install.EXIT_REFUSE, rc)

    def test_cli_exit_0_on_dry_run_match(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb()
        buf = io.StringIO()
        argv = [
            str(self.apk), "--serial", SERIAL,
            "--ledger", str(self.ledger),
            "--jsonl", str(self.jsonl),
            "--adb", "adb-not-on-path-for-tests",
            "--dry-run",
        ]
        with unittest.mock.patch.object(adb_install, "run_adb", fake):
            old = sys.stdout
            try:
                sys.stdout = buf
                rc = adb_install.main(argv)
            finally:
                sys.stdout = old
        self.assertEqual(adb_install.EXIT_OK, rc)
        self.assertEqual([], fake.install_calls())

    def test_parse_adb_devices_skips_daemon_noise(self) -> None:
        text = (
            "* daemon not running; starting now at tcp:5037 *\n"
            "* daemon started successfully *\n"
            "List of devices attached\n"
            f"{SERIAL}\tdevice\n"
        )
        rows = adb_install.parse_adb_devices(text)
        self.assertEqual([(SERIAL, "device")], rows)

    def test_adb_missing_refuses_after_ledger_ok(self) -> None:
        self._write_ledger(_ledger(SERIAL, self.sha))
        fake = FakeAdb(raise_on="devices")
        row = self._run(fake)
        self.assertIn("adb_failed", row["reasons"])
        self.assertEqual(adb_install.OUTCOME_REFUSED, row["outcome"])
        self.assertEqual([], fake.install_calls())


if __name__ == "__main__":
    unittest.main()
