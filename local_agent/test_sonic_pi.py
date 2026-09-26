#!/usr/bin/env python3
"""Stdlib tests for Sonic Pi OSC helpers used by the local agent on :8760."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import remote_security
import router
import sonic_pi
import tools


class OscEncodingTests(unittest.TestCase):
    def test_padded_strings_are_multiples_of_four(self):
        packet = sonic_pi.encode_osc("/run-code", "live_loop :drums do\nend")
        self.assertEqual(0, len(packet) % 4)
        self.assertTrue(packet.startswith(b"/run-code\x00\x00\x00"))
        self.assertIn(b",s\x00\x00", packet)

    def test_stop_all_has_no_payload_args(self):
        packet = sonic_pi.encode_osc("/stop-all-jobs")
        self.assertTrue(packet.startswith(b"/stop-all-jobs\x00\x00"))
        self.assertIn(b",\x00\x00\x00", packet)

    def test_spider_token_is_signed_int32(self):
        token = 1794043680
        packet = sonic_pi.encode_osc("/run-code", token, "play 60")
        self.assertIn(b",is\x00", packet)
        self.assertIn(struct.pack(">i", token), packet)


class QueueInstallTests(unittest.TestCase):
    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = Path(tmp) / "init.rb"
            workspace = Path(tmp) / "workspace_zero.spi"
            with patch.object(sonic_pi, "INIT_RB", init), \
                 patch.object(sonic_pi, "WORKSPACE_ZERO", workspace):
                first = sonic_pi.install_queue_runner()
                second = sonic_pi.install_queue_runner()
            text = init.read_text(encoding="utf-8")
            self.assertTrue(first["ok"] and second["ok"])
            self.assertEqual(1, text.count(sonic_pi.BEGIN))
            self.assertIn("live_loop :mcp_song_queue", text)
            self.assertIn("live_loop :mcp_song_queue", workspace.read_text(encoding="utf-8"))

    def test_discover_spider_from_command_line(self):
        line = (
            r'"C:\Program Files\Sonic Pi\app\server\native\ruby\bin\ruby.exe" '
            r"--disable=gems -E utf-8 "
            r'"C:\Program Files\Sonic Pi\app\server\ruby\bin\spider-server.rb" '
            r"-u 38273 38274 38275 38275 4560 1794043680"
        )
        found = sonic_pi.discover_spider(line)
        self.assertEqual(38273, found["server_port"])
        self.assertEqual(4560, found["osc_cues_port"])
        self.assertEqual(1794043680, found["token"])


class ToolDispatchTests(unittest.TestCase):
    def test_queue_segment_sends_code_to_run_code_path(self):
        captured = {}

        def fake_sendto(packet, dest):
            captured["packet"] = packet
            captured["dest"] = dest
            return len(packet)

        with patch.object(sonic_pi, "discover_spider", return_value=None), \
             patch("sonic_pi.socket.socket") as sock_cls:
            sock_cls.return_value.sendto.side_effect = fake_sendto
            raw = tools.call("queue_sonic_pi", {
                "code": "use_bpm 120\nlive_loop :drums do\n  sample :bd_haus\n  sleep 1\nend",
            })
        result = json.loads(raw)
        self.assertTrue(result["ok"])
        self.assertEqual(("127.0.0.1", 4560), captured["dest"])
        self.assertTrue(captured["packet"].startswith(b"/run-code"))
        self.assertIn(b"live_loop :drums", captured["packet"])

    def test_play_note_uses_spider_when_available(self):
        spider = {"server_port": 38273, "token": 42, "osc_cues_port": 4560}
        with patch.object(sonic_pi, "discover_spider", return_value=spider), \
             patch.object(sonic_pi, "send_osc", return_value={
                 "ok": True, "host": "127.0.0.1", "port": 38273,
                 "path": "/run-code", "bytes": 1,
             }) as send:
            raw = tools.call("play_sonic_pi_note", {"note": 64, "synth": "saw"})
        self.assertEqual("/run-code", send.call_args[0][0])
        self.assertEqual(42, send.call_args[0][1])
        self.assertIn("play 64", send.call_args[0][2])
        self.assertEqual("spider", json.loads(raw)["via"])

    def test_stop_all_uses_spider_token(self):
        spider = {"server_port": 38273, "token": 99, "osc_cues_port": 4560}
        with patch.object(sonic_pi, "discover_spider", return_value=spider), \
             patch.object(sonic_pi, "send_osc", return_value={
                 "ok": True, "host": "127.0.0.1", "port": 38273,
                 "path": "/stop-all-jobs", "bytes": 1,
             }) as send:
            raw = tools.call("stop_sonic_pi", {})
        self.assertEqual(("/stop-all-jobs", 99), send.call_args[0][:2])
        self.assertTrue(json.loads(raw)["stopped"])

    def test_empty_code_is_refused(self):
        raw = tools.call("queue_sonic_pi", {"code": "  "})
        self.assertTrue(raw.startswith("ERROR:"))
        self.assertIn("code is required", raw)

    def test_phone_is_gated_without_grant(self):
        ctx = remote_security.ToolContext(source="lxmf", remote_identity="a" * 32)
        raw = tools.call("queue_sonic_pi", {"code": "play 60"}, context=ctx)
        self.assertIn("not permitted from this phone identity", raw)

    def test_general_chat_schemas_include_sonic_pi(self):
        names = {item["function"]["name"] for item in tools.schemas(include_project=False)}
        self.assertTrue(
            {"ensure_sonic_pi", "queue_sonic_pi", "play_sonic_pi_note", "stop_sonic_pi"}
            <= names
        )

    def test_ensure_skips_wait_when_spider_already_running(self):
        spider = {"server_port": 35212, "token": 7, "osc_cues_port": 4560}
        with patch.object(sonic_pi, "install_queue_runner", return_value={"ok": True}), \
             patch.object(sonic_pi, "discover_spider", return_value=spider), \
             patch.object(sonic_pi, "inject_queue_runner",
                          return_value={"ok": True, "injected": True}), \
             patch.object(sonic_pi, "port_open", return_value=True), \
             patch.object(sonic_pi.time, "sleep") as sleep:
            raw = sonic_pi.ensure_sonic_pi({"timeout": 90})
        sleep.assert_not_called()
        self.assertTrue(json.loads(raw)["ok"])

    def test_every_model_prompt_includes_sonic_pi_tools(self):
        history = [{"role": "user", "content": "play a house beat in sonic pi"}]
        general = agent.system_prompt(history)
        coding = agent.system_prompt(history, model=router.CODING_MODEL)
        self.assertIn("queue_sonic_pi", general)
        self.assertIn("queue_sonic_pi", coding)

    def test_sp_alias_after_operator_defines_it(self):
        history = [
            {"role": "user", "content": "play house beat at 120 in sonic pi also im going to refer to sonic pi as 'sp' for short"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "sp: make it dirtier"},
        ]
        self.assertTrue(agent._sonic_pi_control_request(history))
        self.assertTrue(agent._sonic_pi_control_request(
            [{"role": "user", "content": "open sonic pi"}]))
        self.assertTrue(agent._sonic_pi_stop_request(
            [{"role": "user", "content": "stop the music in sonic pi"}]))
        self.assertFalse(agent._sonic_pi_control_request(
            [{"role": "user", "content": "list files in this folder"}]))


if __name__ == "__main__":
    unittest.main()
