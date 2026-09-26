"""NTFS ACL lockdown for farm secret-writing scripts.

Correct invocation — from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_phase1_secret_acl -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_phase1_secret_acl -v"
)


def _require_package_layout() -> None:
    """Fail loudly when this file is executed by path instead of as a package."""
    try:
        import local_agent.worker_farm  # noqa: F401
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
            raise
        sys.stderr.write(
            "ERROR: local_agent is not importable because this file was run by path.\n"
            "From the repository root, use the farm venv:\n"
            f"  {_FARM_UNITTEST}\n"
        )
        raise SystemExit(2) from exc


_require_package_layout()

HERE = Path(__file__).resolve().parent


def _powershell() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def _run_ps(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", *args],
        capture_output=True,
        text=True,
        cwd=str(HERE.parent.parent),
    )


@unittest.skipUnless(sys.platform == "win32", "NTFS ACL lockdown is Windows-only")
class Phase1SecretAclTests(unittest.TestCase):
    def test_helper_probe_locks_dummy_file(self):
        completed = _run_ps("-File", str(HERE / "Lock-Phase1SecretFile.ps1"), "-Probe")
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr + "\n" + completed.stdout,
        )
        self.assertIn("PASS:", completed.stdout)

    def test_initialize_phase1_secrets_lockdown_probe(self):
        completed = _run_ps("-File", str(HERE / "Initialize-Phase1Secrets.ps1"), "-LockdownProbe")
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr + "\n" + completed.stdout,
        )
        self.assertIn("PASS:", completed.stdout)
        self.assertNotIn("REDIS_PASSWORD=", completed.stdout)
        self.assertNotIn("FARM_ENCRYPTION_KEY_B64=", completed.stdout)
        live = HERE / ".env"
        self.assertTrue(live.is_file(), "probe must not delete the live .env")

    def test_add_secondary_credential_lockdown_probe(self):
        completed = _run_ps(
            "-File", str(HERE / "Add-Phase1SecondaryWorkerCredential.ps1"),
            "-LockdownProbe",
        )
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr + "\n" + completed.stdout,
        )
        self.assertIn("PASS:", completed.stdout)
        self.assertFalse(
            (HERE / ".env.probe_worker.generated").exists(),
            "probe must not leave a generated file in worker_farm/",
        )

    def test_resolve_farm_redis_engine_probe(self):
        completed = _run_ps("-File", str(HERE / "Resolve-FarmRedisEngine.ps1"), "-Probe")
        self.assertEqual(
            completed.returncode, 0,
            completed.stderr + "\n" + completed.stdout,
        )
        self.assertIn("PASS:", completed.stdout)
        self.assertIn("default=desktop", completed.stdout)

    def test_secret_scripts_lock_after_write(self):
        cases = (
            ("Initialize-Phase1Secrets.ps1", "WriteAllText", "Lock-Phase1SecretFile -LiteralPath $envFile"),
            ("Add-Phase1SecondaryWorkerCredential.ps1", "WriteAllText($outFile", "Lock-Phase1SecretFile -LiteralPath $outFile"),
            ("Restore-Phase1SecondaryWorkerCredentials.ps1", "Copy-Item -LiteralPath $file.FullName", "Lock-Phase1SecretFile -LiteralPath $dest"),
        )
        for name, write_token, lock_token in cases:
            with self.subTest(script=name):
                text = (HERE / name).read_text(encoding="utf-8")
                self.assertIn("Lock-Phase1SecretFile.ps1", text)
                self.assertIn(lock_token, text)
                self.assertGreater(
                    text.rindex(lock_token),
                    text.rindex(write_token),
                    f"{name} must lock after the write/copy, not before",
                )


if __name__ == "__main__":
    unittest.main()
