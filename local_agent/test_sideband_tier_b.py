#!/usr/bin/env python3
"""Static safety checks for the minimal Sideband Tier-B fork overlay.

These tests intentionally do not import Kivy, Android, RNS, or LXMF.  They
prove the checked-in source preserves the workstation boundary before a future
Android toolchain is installed.
"""
from __future__ import annotations

import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SIDEBAND = HERE / "vendor_sideband" / "sbapp"

# Source-only forbids (companion PR 3). REQUEST_INSTALL_PACKAGES stays
# forbidden until PR 6. Do not compile an APK from these tests.
FORBIDDEN_OVERLAY_TOKENS = (
    "MANAGE_EXTERNAL_STORAGE",
    "REQUEST_INSTALL_PACKAGES",
    "INSTALL_PACKAGES",
    "BIND_DEVICE_ADMIN",
    "pm install",
    "installPackage",
)
SCAN_SUFFIXES = {".py", ".spec", ".xml", ".java", ".kt", ".kts", ".gradle"}
SKIP_DIR_NAMES = {".buildozer", "bin", "__pycache__", ".git"}


def _overlay_text_files():
    for path in SIDEBAND.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        yield path, path.read_text(encoding="utf-8", errors="replace")


class SidebandTierBTests(unittest.TestCase):
    def setUp(self):
        self.main = (SIDEBAND / "main.py").read_text(encoding="utf-8")
        self.spec = (SIDEBAND / "buildozer.spec").read_text(encoding="utf-8")
        self.bridge = (HERE / "lxmf_agent.py").read_text(encoding="utf-8")

    def test_camera_permission_is_declared_and_requested_only_on_capture(self):
        self.assertIn("RECORD_AUDIO,CAMERA,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS", self.spec)
        self.assertIn("def request_camera_permission(self):", self.main)
        self.assertIn('check_permission("android.permission.CAMERA")', self.main)
        start = self.main.index("def message_capture_camera_action")
        end = self.main.index("def message_attachment_action", start)
        capture = self.main[start:end]
        self.assertIn("self.request_camera_permission()", capture)
        self.assertIn("RNS.vendor.platformutils.is_android()", capture)

    def test_derivative_package_identity_does_not_replace_stock_sideband(self):
        self.assertIn("title = Equal Shares Agent", self.spec)
        self.assertIn("package.name = sidebandagent", self.spec)
        self.assertIn("package.domain = local.equalshares", self.spec)
        self.assertIn("local.equalshares.sidebandagent", self.main)
        self.assertNotIn('package.name = sideband\\n', self.spec)

    def test_camera_uses_normal_medium_image_send_path(self):
        start = self.main.index("def message_capture_camera_action")
        end = self.main.index("def message_attachment_action", start)
        capture = self.main[start:end]
        self.assertIn("plyer.camera.take_picture", capture)
        self.assertIn('self.attach_type = "defimg"', capture)
        self.assertIn("Capture Camera Image", self.main)

    def test_bridge_remains_the_path_only_remote_boundary(self):
        self.assertIn("paths only; use tools first", self.bridge)
        self.assertIn("MAX_ATTACHMENT_BYTES", self.bridge)
        self.assertIn('with path.open("xb")', self.bridge)
        security = (HERE / "remote_security.py").read_text(encoding="utf-8")
        self.assertIn("GATED_REMOTE_TOOLS", security)
        self.assertIn("batch_render", security)
        self.assertIn("write_file", security)

    def test_spec_does_not_request_all_files_storage(self):
        self.assertNotIn("MANAGE_EXTERNAL_STORAGE", self.spec)
        self.assertNotIn("REQUEST_INSTALL_PACKAGES", self.spec)
        self.assertNotIn("INSTALL_PACKAGES", self.spec)
        self.assertNotIn("BIND_DEVICE_ADMIN", self.spec)
        perms_lines = [
            line for line in self.spec.splitlines()
            if line.strip().startswith("android.permissions")
        ]
        self.assertEqual(1, len(perms_lines))
        self.assertIn("RECORD_AUDIO,CAMERA,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
                      perms_lines[0])

    def test_overlay_forbids_all_files_and_silent_install_apis(self):
        hits: list[str] = []
        for path, text in _overlay_text_files():
            rel = path.relative_to(SIDEBAND).as_posix()
            for token in FORBIDDEN_OVERLAY_TOKENS:
                if token in text:
                    hits.append(f"{rel}: {token}")
        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()
