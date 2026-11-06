#!/usr/bin/env python3
"""Paired phones no longer get file-system / network reach by default.

Audit 2026-11-02 #21: read_file, list_dir, inspect_workspace, inspect_binary,
fetch_url, propose_file_diff and dispatch_subtasks moved from
REMOTE_DEFAULT_TOOLS to GATED_REMOTE_TOOLS. Each needs an explicit
per-identity grant through the existing set_tool_grant / permits() path.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remote_security
import tools


MOVED_TO_GATED = (
    "read_file",
    "list_dir",
    "inspect_workspace",
    "inspect_binary",
    "fetch_url",
    "propose_file_diff",
    "dispatch_subtasks",
)
STILL_DEFAULT = (
    "search_docs",
    "agentic_search_docs",
    "list_memory",
    "read_doc",
    "capabilities",
    "see_image",
    "transcribe",
    "list_phone_schedules",
)
IDENTITY = "11" * 16
OTHER = "22" * 16


class RemoteDefaultToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pairs = Path(self.tmp.name) / "paired.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_and_network_tools_are_gated_not_default(self):
        for name in MOVED_TO_GATED:
            with self.subTest(tool=name):
                self.assertNotIn(name, remote_security.REMOTE_DEFAULT_TOOLS)
                self.assertIn(name, remote_security.GATED_REMOTE_TOOLS)
                self.assertIn(name, tools.TOOLS, "tool must still exist to be gated")

    def test_conversation_search_and_memory_read_tools_stay_default(self):
        for name in STILL_DEFAULT:
            with self.subTest(tool=name):
                self.assertIn(name, remote_security.REMOTE_DEFAULT_TOOLS)

    def test_every_registered_tool_is_still_classified_exactly_once(self):
        names = set(tools.TOOLS)
        default = remote_security.REMOTE_DEFAULT_TOOLS
        gated = remote_security.GATED_REMOTE_TOOLS
        self.assertFalse(names - default - gated)
        self.assertFalse(default & gated)

    def test_phone_without_grant_is_denied_and_desktop_is_not(self):
        phone = remote_security.ToolContext(source="phone", remote_identity=IDENTITY)
        for name in MOVED_TO_GATED:
            with self.subTest(tool=name):
                self.assertFalse(phone.permits(name))
                self.assertTrue(remote_security.DESKTOP_CONTEXT.permits(name))

    def test_explicit_grant_is_required_and_per_identity(self):
        remote_security.pair(IDENTITY, "phone a", path=self.pairs)
        remote_security.pair(OTHER, "phone b", path=self.pairs)
        for name in MOVED_TO_GATED:
            remote_security.set_tool_grant(IDENTITY, name, True, self.pairs)
        granted = remote_security.context_for(IDENTITY, path=self.pairs)
        denied = remote_security.context_for(OTHER, path=self.pairs)
        for name in MOVED_TO_GATED:
            with self.subTest(tool=name):
                self.assertTrue(granted.permits(name))
                self.assertFalse(denied.permits(name))
        remote_security.set_tool_grant(IDENTITY, "read_file", False, self.pairs)
        revoked = remote_security.context_for(IDENTITY, path=self.pairs)
        self.assertFalse(revoked.permits("read_file"))
        self.assertTrue(revoked.permits("list_dir"))

    def test_tool_dispatch_refuses_ungranted_read_file_from_a_phone(self):
        remote_security.pair(IDENTITY, "phone a", path=self.pairs)
        audit = Path(self.tmp.name) / "audit.jsonl"
        context = remote_security.context_for(IDENTITY, "cid", "req", self.pairs, audit)
        raw = tools.call("read_file", {"path": "local_agent/agent.py"}, context=context)
        self.assertIn("not permitted", raw)
        self.assertNotIn("import", raw)
        self.assertTrue(audit.is_file())
        self.assertIn('"refused"', audit.read_text(encoding="utf-8"))

    def test_module_docs_describe_the_default_set_honestly(self):
        source = (HERE / "remote_security.py").read_text(encoding="utf-8")
        self.assertIn("need an explicit grant", source)
        self.assertNotIn("use the read/sensory tools in REMOTE_DEFAULT_TOOLS", source)


if __name__ == "__main__":
    unittest.main()
