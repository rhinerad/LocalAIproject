#!/usr/bin/env python3
"""Keep the desktop launcher's readiness check in lockstep with server.py."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class LauncherRevisionTests(unittest.TestCase):
    def test_launcher_expects_the_server_revision(self):
        server = (HERE / "server.py").read_text(encoding="utf-8")
        launcher = (HERE / "START_LOCAL_AGENT_GUI.ps1").read_text(encoding="utf-8")
        app = re.search(r'^APP_REVISION\s*=\s*"([^"]+)"', server, re.MULTILINE)
        expected = re.search(r"^\$ExpectedAgentRevision\s*=\s*'([^']+)'", launcher,
                             re.MULTILINE)
        self.assertIsNotNone(app, "server.py must expose APP_REVISION")
        self.assertIsNotNone(expected, "launcher must expose ExpectedAgentRevision")
        self.assertEqual(expected.group(1), app.group(1))


if __name__ == "__main__":
    unittest.main()
