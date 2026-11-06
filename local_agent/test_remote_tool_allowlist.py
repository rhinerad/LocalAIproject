#!/usr/bin/env python3
"""Remote tools are allowlisted. Production entry points need an explicit grant."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remote_security
import tools


class RemoteAllowlistTests(unittest.TestCase):
    def test_every_registered_tool_is_classified(self) -> None:
        names = set(tools.TOOLS)
        default = remote_security.REMOTE_DEFAULT_TOOLS
        gated = remote_security.GATED_REMOTE_TOOLS
        self.assertFalse(names - default - gated)
        self.assertFalse(default & gated)
        for name in (
            "generate_still", "upscale_still", "run_prompt_pack_production",
            "execute_narrative_scene", "execute_continuous_take",
            "execute_montage_morph", "execute_fast_action",
        ):
            self.assertIn(name, gated)
            self.assertNotIn(name, default)

    def test_phone_without_grants_cannot_generate_still(self) -> None:
        context = remote_security.ToolContext(source="phone", allowed_tools=frozenset())
        with patch("gvd_tool_router.tools.execute_tool") as execute:
            raw = tools.call("generate_still", {"live": True, "manifest": {}}, context=context)
        self.assertIn("not permitted", raw)
        execute.assert_not_called()

    def test_forged_identity_does_not_skip_gpu_approval(self) -> None:
        context = remote_security.ToolContext(source="desktop", conversation_id="cid-real")
        with patch("gpu_gate.request", return_value={"granted": False}) as gate, \
             patch("prompt_pack_production.start_supervisor") as start:
            raw = tools.call("run_prompt_pack_production", {
                "__conversation_id": "forged",
                "__remote_render_identity": "a" * 32,
                "operator_text": "go",
            }, context=context)
        self.assertTrue(raw.startswith("ERROR:"))
        gate.assert_called_once()
        start.assert_not_called()

    def test_forged_conversation_id_is_replaced_from_context(self) -> None:
        seen = {}

        def fake(args):
            seen["cid"] = args.get("__conversation_id")
            return json.dumps({"ok": True})

        context = remote_security.ToolContext(source="desktop", conversation_id="realchat")
        with patch.dict(tools.TOOLS, {"prompt_pack_status": (fake, "status")}):
            tools.call("prompt_pack_status", {"__conversation_id": "forged"}, context=context)
        self.assertEqual("realchat", seen["cid"])

    def test_granted_phone_still_obeys_gpu_block(self) -> None:
        context = remote_security.ToolContext(
            source="phone", remote_identity="d" * 32, conversation_id="cid-real",
            allowed_tools=frozenset({"run_prompt_pack_production"}),
        )
        with patch("gpu_gate.snapshot", return_value={"mode": "block"}), \
             patch("gpu_gate.request") as gate, \
             patch("prompt_pack_production.start_supervisor") as start:
            raw = tools.call("run_prompt_pack_production", {
                "__remote_render_identity": "forged",
            }, context=context)
        self.assertIn("Block", raw)
        gate.assert_not_called()
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
