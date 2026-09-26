#!/usr/bin/env python3
"""Static checks for the isolated pyjnius SAF spike. No device, no compile."""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE / "saf_pyjnius_spike"
SIDEBAND_SPEC = HERE / "vendor_sideband" / "sbapp" / "buildozer.spec"

FORBIDDEN = (
    "MANAGE_EXTERNAL_STORAGE",
    "REQUEST_INSTALL_PACKAGES",
    "INSTALL_PACKAGES",
    "BIND_DEVICE_ADMIN",
    "pm install",
    "installPackage",
)
SCAN_SUFFIXES = {".py", ".spec", ".xml", ".java", ".kt", ".kts", ".gradle"}


class SafSpikeStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.main = (SPIKE / "main.py").read_text(encoding="utf-8")
        self.spec = (SPIKE / "buildozer.spec").read_text(encoding="utf-8")
        self.overlay_spec = SIDEBAND_SPEC.read_text(encoding="utf-8")

    def test_package_is_not_the_companion_or_stock(self) -> None:
        self.assertIn("package.name = safspike", self.spec)
        self.assertIn("package.domain = local.equalshares", self.spec)
        self.assertNotIn("package.name = sidebandagent", self.spec)
        self.assertNotIn("package.name = sideband\n", self.spec)

    def test_pins_match_overlay_api_ndk_p4a(self) -> None:
        for key in ("android.api = 33", "android.ndk = 25b",
                    "p4a.commit = 1fc0269438c365e07ea456793c300e3e18773939"):
            self.assertIn(key, self.spec)
            self.assertIn(key, self.overlay_spec)
        self.assertIn("p4a.local_recipes", self.spec)
        self.assertIn("p4a.local_recipes", self.overlay_spec)

    def test_spike_uses_tree_intent_and_read_persist(self) -> None:
        self.assertIn("ACTION_OPEN_DOCUMENT_TREE", self.main)
        self.assertIn("takePersistableUriPermission", self.main)
        self.assertIn("FLAG_GRANT_READ_URI_PERMISSION", self.main)
        self.assertIn("FLAG_GRANT_PERSISTABLE_URI_PERMISSION", self.main)
        self.assertIn("getPersistedUriPermissions", self.main)
        self.assertNotIn("FLAG_GRANT_WRITE_URI_PERMISSION", self.main)
        self.assertNotIn("ACTION_GET_CONTENT", self.main)

    def test_spike_source_forbids_all_files_and_silent_install(self) -> None:
        hits: list[str] = []
        for path in SPIKE.rglob("*"):
            if any(p in {".buildozer", "bin", "__pycache__", "artifacts",
                         "recipes"}
                   for p in path.parts):
                continue
            try:
                if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
                    continue
            except OSError:
                continue
            if path.name in {"check_artifacts.py", "snapshot_toolchain.py",
                             "patch_p4a_no_isolation.py",
                             "patch_p4a_hostpython_interpreter.py",
                             "diagnose_build_meta.py",
                             "diagnose_build_meta2.py",
                             "diagnose_build_meta3.py",
                             "diagnose_build_meta4.py",
                             "pin_hostpython_cython.py",
                             "inspect_apk.py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(SPIKE).as_posix()
            for token in FORBIDDEN:
                if token in text:
                    hits.append(f"{rel}: {token}")
        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()
