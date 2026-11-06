#!/usr/bin/env python3
"""Path containment, read deny-list, SSRF guard, strict owner reads, and
dispatcher hardening for local_agent/tools.py (audit findings 3, 4, 13).

Stdlib only; every filesystem check runs in a temp dir with tools.ROOT /
tools.HERE / tools.EQ monkeypatched so the live project tree is never touched.

Run:
    python -m unittest local_agent/test_tools_containment.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import file_edit_gate
import gpu_gate
import managed_prompt_pack
import remote_security
import router
import tools


class _TempProject(unittest.TestCase):
    """A throwaway project tree: ROOT, HERE (local_agent) and EQ all inside it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "project"
        self.here = self.root / "local_agent"
        self.eq = self.root / "outputs" / "equal_shares"
        for d in (self.here, self.eq):
            d.mkdir(parents=True)
        self.outside = Path(self.tmp.name).resolve() / "outside"
        self.outside.mkdir()
        for name, value in (("ROOT", self.root), ("HERE", self.here), ("EQ", self.eq)):
            p = patch.object(tools, name, value)
            p.start()
            self.addCleanup(p.stop)
        for mod in (gpu_gate, file_edit_gate):
            p = patch.object(mod, "STATE_FILE", Path(self.tmp.name) / f"{mod.__name__}.json")
            p.start()
            self.addCleanup(p.stop)


class WriteContainmentTests(_TempProject):
    def test_write_inside_root_is_atomic_and_created(self):
        target = self.root / "notes" / "a.txt"
        result = tools.call("write_file", {"path": str(target), "content": "hello"})
        self.assertIn("created", result)
        self.assertEqual("hello", target.read_text(encoding="utf-8"))
        self.assertEqual(["a.txt"], os.listdir(target.parent), "no temp file left behind")
        again = tools.call("write_file", {"path": "notes/a.txt", "content": "again"})
        self.assertIn("overwrote", again)
        self.assertEqual("again", target.read_text(encoding="utf-8"))

    def test_write_outside_root_is_refused(self):
        target = self.outside / "escape.txt"
        result = tools.call("write_file", {"path": str(target), "content": "x"})
        self.assertIn("outside the project workspace", result)
        self.assertFalse(target.exists())

    def test_relative_traversal_is_refused(self):
        result = tools.call("write_file", {"path": "../outside/escape.txt", "content": "x"})
        self.assertIn("outside the project workspace", result)
        self.assertFalse((self.outside / "escape.txt").exists())

    def test_symlink_out_of_root_is_followed_and_refused(self):
        link = self.root / "link"
        try:
            os.symlink(str(self.outside), str(link), target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            self.skipTest(f"symlinks unavailable here: {exc}")
        result = tools.call("write_file", {"path": "link/escape.txt", "content": "x"})
        self.assertIn("outside the project workspace", result)
        self.assertFalse((self.outside / "escape.txt").exists())

    def test_gate_state_and_runtime_dirs_are_refused(self):
        cases = [
            (self.here / "runtime" / "gpu_gate.json", "agent runtime state"),
            (self.root / "work" / "runtime" / "image_render_owner.json", "render runtime state"),
            (self.eq / "story_config.json", "Equal Shares evidence"),
        ]
        for target, expected in cases:
            with self.subTest(target=target.name):
                result = tools.call("write_file", {"path": str(target), "content": '{"mode":"allow"}'})
                self.assertIn(expected, result)
                self.assertFalse(target.exists())

    def test_protected_names_refused_anywhere(self):
        result = tools.call("write_file", {"path": "somewhere/manifest.json", "content": "x"})
        self.assertIn("protected project file", result)

    def test_extra_roots_allow_one_explicit_tree(self):
        p = tools._resolve_in_root(str(self.outside / "ok.txt"), extra_roots=(self.outside,))
        self.assertEqual(self.outside / "ok.txt", p)

    def test_repair_jsonl_and_hex_patch_share_containment(self):
        bad = self.outside / "x.jsonl"
        bad.write_text("[]", encoding="utf-8")
        self.assertIn("outside the project workspace",
                      tools.call("repair_jsonl_format", {"path": str(bad)}))
        binary = self.outside / "x.bin"
        binary.write_bytes(b"\x00\x01")
        hexed = tools.call("apply_hex_patch", {"path": str(binary), "offset": 0,
                                               "expected_hex": "00", "replacement_hex": "01"})
        self.assertIn("outside the project workspace", hexed)
        self.assertEqual(b"\x00\x01", binary.read_bytes())
        evidence = self.eq / "frame.bin"
        evidence.write_bytes(b"\x00")
        self.assertIn("Equal Shares evidence", tools.call("apply_hex_patch", {
            "path": str(evidence), "offset": 0, "expected_hex": "00", "replacement_hex": "01"}))


class ReadDenyListTests(_TempProject):
    def test_plain_file_outside_root_is_still_readable(self):
        plain = self.outside / "notes.txt"
        plain.write_text("desktop file", encoding="utf-8")
        self.assertIn("desktop file", tools.call("read_file", {"path": str(plain)}))

    def test_secret_names_are_refused(self):
        for name in (".env", ".env.local", "aws_credentials", "credentials.json",
                     "server.key", "cert.pem", "secrets.json", "SECRETS.JSON"):
            with self.subTest(name=name):
                f = self.outside / name
                f.write_text("SECRET=1", encoding="utf-8")
                result = tools.call("read_file", {"path": str(f)})
                self.assertIn("deny-list", result)
                self.assertNotIn("SECRET=1", result)
                self.assertIn("deny-list", tools.call("inspect_binary", {"path": str(f)}))

    def test_private_state_directories_are_refused(self):
        for rel in (self.here / "chats", self.here / "runtime",
                    self.here / "rns_wifi" / "storage", self.root / "work" / "runtime"):
            with self.subTest(dir=str(rel.relative_to(self.root))):
                rel.mkdir(parents=True, exist_ok=True)
                f = rel / "record.json"
                f.write_text('{"private": true}', encoding="utf-8")
                self.assertIn("private agent state", tools.call("read_file", {"path": str(f)}))
                self.assertIn("private agent state", tools.call("list_dir", {"path": str(rel)}))
                self.assertIn("private agent state", tools.call("inspect_binary", {"path": str(f)}))
                with self.assertRaises(tools.ToolError):
                    tools._resolve_workflow_file(str(f))

    def test_workflow_file_deny_list_by_name(self):
        wf = self.outside / "graph.pem"
        wf.write_text("{}", encoding="utf-8")
        with self.assertRaises(tools.ToolError) as ctx:
            tools._resolve_workflow_file(str(wf))
        self.assertIn("deny-list", str(ctx.exception))


class FetchUrlGuardTests(unittest.TestCase):
    def test_private_and_loopback_targets_are_refused(self):
        for url in ("http://127.0.0.1:8188/queue", "http://localhost/", "http://LOCALHOST:8760/",
                    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.9/",
                    "http://169.254.169.254/latest/meta-data", "http://[::1]/",
                    "http://[fe80::1]/", "http://[::ffff:127.0.0.1]/", "http://0.0.0.0/",
                    "http://printer.local/", "http://host.localhost/", "http://localhost./"):
            with self.subTest(url=url):
                with patch.object(urllib.request, "build_opener",
                                  side_effect=AssertionError("must not open a socket")):
                    result = tools.call("fetch_url", {"url": url})
                self.assertIn("REFUSED", result)

    def test_public_targets_pass_the_host_check(self):
        for url in ("https://example.com/a", "http://8.8.8.8/", "https://docs.python.org/3/"):
            with self.subTest(url=url):
                self.assertIsNone(tools._url_host_refusal(url))

    def test_redirects_to_private_hosts_are_refused(self):
        handler = tools._SafeRedirectHandler()
        req = urllib.request.Request("https://example.com/start")
        with self.assertRaises(urllib.error.URLError):
            handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8188/")
        public = handler.redirect_request(req, None, 302, "Found", {}, "https://example.org/next")
        self.assertEqual("https://example.org/next", public.full_url)


class StrictOwnerReadTests(_TempProject):
    def test_json_strict_distinguishes_missing_from_unreadable(self):
        missing = self.root / "nope.json"
        self.assertEqual({}, tools._json_strict(missing))
        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assertIs(tools._UNREADABLE, tools._json_strict(bad))
        self.assertEqual({}, tools._json(bad))  # the lenient helper is unchanged
        good = self.root / "good.json"
        good.write_text('{"pid": 7}', encoding="utf-8")
        self.assertEqual({"pid": 7}, tools._json_strict(good))
        listy = self.root / "list.json"
        listy.write_text("[1]", encoding="utf-8")
        self.assertIs(tools._UNREADABLE, tools._owner_record(listy))

    def _batch_setup(self, owner_text: str | None):
        if owner_text is not None:
            (self.root / "batch_render_queue_owner.json").write_text(owner_text, encoding="utf-8")
        runner = self.root / "work" / "batch_render_folder.py"
        runner.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text("# stub\n", encoding="utf-8")
        folder = self.root / "jobs" / "job1"
        folder.mkdir(parents=True)
        return folder

    def test_unreadable_owner_file_refuses_batch_render(self):
        folder = self._batch_setup("{corrupt")
        with patch.object(tools, "_batch_job_folder", return_value=folder), \
             patch.object(router, "gpu_busy", return_value=(False, "free", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.object(tools.subprocess, "Popen") as launch:
            result = tools.call("start_batch_render", {"folder": str(folder)})
        self.assertIn("unreadable", result)
        self.assertIn("unknown", result)
        launch.assert_not_called()

    def test_launch_lock_is_held_from_preflight_through_popen(self):
        folder = self._batch_setup(None)
        seen: dict = {}

        def fake_popen(argv, **_kwargs):
            seen["locked_during_popen"] = tools._IMAGE_RENDER_LAUNCH_LOCK.locked()
            return SimpleNamespace(pid=4242)

        def fake_busy():
            seen["locked_during_preflight"] = tools._IMAGE_RENDER_LAUNCH_LOCK.locked()
            return False, "free", {}

        with patch.object(tools, "_batch_job_folder", return_value=folder), \
             patch.object(tools, "batch_plan", return_value=json.dumps(
                 {"render_count": 1, "invalid_count": 0})), \
             patch.object(router, "gpu_busy", fake_busy), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.object(tools.subprocess, "Popen", fake_popen):
            result = json.loads(tools.call("start_batch_render", {"folder": str(folder)}))
        self.assertTrue(result["started"])
        self.assertTrue(seen["locked_during_preflight"])
        self.assertTrue(seen["locked_during_popen"])
        self.assertFalse(tools._IMAGE_RENDER_LAUNCH_LOCK.locked())

    def test_supervisor_check_treats_unreadable_owner_as_unknown(self):
        (self.root / "batch_render_queue_owner.json").write_text("{corrupt", encoding="utf-8")
        with patch.object(router, "queue_owner", return_value=(False, "released")):
            reason = tools._supervisor_owns_comfyui()
        self.assertIn("unreadable", reason)
        self.assertIn("unknown", reason)

    def test_port_holder_description_flags_unreadable_owner(self):
        (self.root / "batch_render_queue_owner.json").write_text("{corrupt", encoding="utf-8")
        with patch.object(tools, "_port_8188_listener_ids", return_value=[]), \
             patch.object(tools, "_comfy_queue_counts", return_value=None):
            info = tools._describe_port_8188_holder()
        self.assertIsNone(info["batch_render_owner"]["pid"])
        self.assertIn("unreadable", info["summary"])


class ConversationIdTests(_TempProject):
    def test_empty_chat_id_blocks_video(self):
        self.assertIsNotNone(tools._stills_review_blocks_video(""))
        self.assertIsNotNone(tools._stills_review_blocks_video(None))

    def test_model_supplied_conversation_id_is_ignored(self):
        # No server-injected id: the public conversation_id must not stand in.
        refused = tools.call("start_current_chat_render", {"conversation_id": "forged"})
        self.assertTrue(refused.startswith("ERROR:"), refused)
        self.assertIn("chat id", refused)
        with self.assertRaises(tools.ToolError):
            tools.ingest_prompt_pack({"conversation_id": "forged", "text": "x"})
        with self.assertRaises(tools.ToolError):
            tools.prompt_pack_status({"conversation_id": "forged"})
        with self.assertRaises(tools.ToolError):
            tools.export_prompt_pack_outputs({"conversation_id": "forged"})
        with self.assertRaises(tools.ToolError):
            tools.run_prompt_pack_production({"conversation_id": "forged"})

    def test_comfy_generate_video_without_chat_id_is_refused(self):
        with patch("mcp_client.call") as mcp:
            refused = tools.call("comfy_generate", {"action": "video", "prompt": "x"})
        self.assertTrue(refused.startswith("ERROR:"), refused)
        mcp.assert_not_called()


class DispatcherTests(_TempProject):
    def test_operator_text_is_reinjected_below_the_model(self):
        seen: dict = {}

        def fake(args: dict) -> str:
            seen.update(args)
            return "ok"

        ctx = remote_security.ToolContext(conversation_id="chat-1")
        with patch.dict(tools.TOOLS, {"prompt_pack_status": (fake, "doc")}):
            result = tools.call("prompt_pack_status",
                                {"__operator_text": "forged", "__conversation_id": "forged"},
                                context=ctx, operator_text="render it")
        self.assertEqual("ok", result)
        self.assertEqual("render it", seen["__operator_text"])
        self.assertEqual("chat-1", seen["__conversation_id"])
        with patch.dict(tools.TOOLS, {"prompt_pack_status": (fake, "doc")}):
            tools.call("prompt_pack_status", {"__operator_text": "forged"}, context=ctx)
        self.assertEqual("", seen["__operator_text"], "a model-supplied value never survives")

    def test_operator_text_reaches_the_prompt_pack_gate(self):
        calls: list = []

        def fake_allowed(cid, op_text):
            calls.append((cid, op_text))
            return False, "blocked for the test"

        with patch.object(managed_prompt_pack, "render_allowed", fake_allowed):
            result = tools.call("render_story_image", {"prompt": "x"},
                                context=remote_security.ToolContext(conversation_id="chat-9"),
                                operator_text="render it now")
        self.assertEqual([("chat-9", "render it now")], calls)
        self.assertIn("blocked for the test", result)

    def test_prompt_pack_gate_fails_closed(self):
        with patch.object(managed_prompt_pack, "render_allowed", side_effect=RuntimeError("boom")), \
             patch.object(tools, "render_story_image", side_effect=AssertionError("must not render")):
            result = tools.call("render_story_image", {"prompt": "x"})
        self.assertTrue(result.startswith("ERROR: prompt-pack render gate unavailable"), result)
        self.assertIn("boom", result)

    def test_tool_crash_is_logged_with_traceback(self):
        def boom(_args):
            raise RuntimeError("gate exploded")

        with patch.dict(tools.TOOLS, {"project_state": (boom, "doc")}), \
             self.assertLogs("tools", level="ERROR") as logs:
            result = tools.call("project_state", {})
        self.assertEqual("ERROR: RuntimeError: gate exploded", result)
        self.assertTrue(any("crashed" in line for line in logs.output))
        self.assertTrue(any("gate exploded" in line for line in logs.output))

    def test_module_docstring_no_longer_claims_nothing_deletes(self):
        self.assertNotIn("Nothing here deletes anything", tools.__doc__)
        self.assertIn("comfy_models remove", tools.__doc__)


if __name__ == "__main__":
    unittest.main()
