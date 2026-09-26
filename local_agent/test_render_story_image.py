#!/usr/bin/env python3
"""render_story_image / story_image_job_status — the actual image-execution tools.

These cover the gap the operator hit in production: plan_story_image could only
ever plan, and the model hallucinated a completed render. render_story_image
now actually launches work/image_render.py --execute, gated the same way every
other GPU action in this agent is gated; story_image_job_status is the only
honest way to find out whether that background job produced a real file.
Everything here mocks subprocess/router/gpu_gate — no GPU or ComfyUI is ever
touched by this suite.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import remote_security
import tools


class _FakeImageRender:
    """Stand-in for the work/image_render module tools.py imports lazily."""
    IMAGE_OWNER = None  # set per-test to a real temp path
    DEFAULT_NEGATIVE = "blurry, low quality"
    DEFAULT_STEPS = 35
    MODEL_PROFILES = {
        "realvisxl": {"model": "realvisxl.safetensors",
                      "defaults": {"width": 1024, "height": 1024, "steps": 35,
                                   "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"}},
        "realpro_flux": {"model": "flux1-dev.safetensors",
                         "defaults": {"width": 1024, "height": 1024, "steps": 20,
                                      "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}},
    }

    class ImageRenderError(RuntimeError):
        pass

    @staticmethod
    def _safe_segment(value, label):
        value = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
        value = value.strip("-_")
        if not value:
            raise _FakeImageRender.ImageRenderError(f"{label} must contain letters or numbers")
        return value[:80]

    @staticmethod
    def _live_owner():
        return False

    @staticmethod
    def _port_open():
        return False


class RenderStoryImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.owner_path = Path(self._tmp.name) / "image_render_owner.json"
        _FakeImageRender.IMAGE_OWNER = self.owner_path

    def _patched(self, **overrides):
        """Context manager stack patching everything render_story_image touches."""
        import router
        import gpu_gate
        patches = {
            "router.gpu_busy": (False, "idle", {}),
        }
        patches.update(overrides)
        stack = [
            patch.dict(sys.modules, {"image_render": _FakeImageRender}),
            patch.object(router, "gpu_busy", return_value=patches["router.gpu_busy"]),
        ]
        return stack

    def test_refuses_when_gpu_is_busy(self):
        import router
        with patch.object(router, "gpu_busy", return_value=(True, "another render is active", {})), \
             patch.dict(sys.modules, {"image_render": _FakeImageRender}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("another render is active", str(ctx.exception))

    def test_refuses_when_equal_shares_owns_the_gpu(self):
        import router
        fake = _FakeImageRender
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(fake, "_live_owner", return_value=True), \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("Equal Shares", str(ctx.exception))

    def test_refuses_when_port_8188_already_listening(self):
        import router
        fake = _FakeImageRender
        holder = {"kind": "foreign_backend", "summary": "port 8188 is held by pid 52504"}
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(fake, "_port_open", return_value=True), \
             patch.object(tools, "_describe_port_8188_holder", return_value=holder), \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("already listening on port 8188", str(ctx.exception))
        self.assertIn("pid 52504", str(ctx.exception))
        self.assertEqual(ctx.exception.blocked_by["kind"], "foreign_backend")

    def test_router_port_busy_reason_becomes_the_same_structured_refusal(self):
        # 2026-09-23 regression: gpu_busy()'s own wording ("a ComfyUI backend
        # is listening on port 8188") used to be re-raised verbatim, which the
        # batch retry/diagnosis logic never recognised.
        import router
        holder = {"kind": "foreign_backend", "summary": "port 8188 is held by pid 52504"}
        busy = (True, "a ComfyUI backend is listening on port 8188", {"comfy_port_8188": "listening"})
        with patch.object(router, "gpu_busy", return_value=busy), \
             patch.object(tools, "_describe_port_8188_holder", return_value=holder), \
             patch.dict(sys.modules, {"image_render": _FakeImageRender}):
            with self.assertRaises(tools.Port8188BusyError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("already listening on port 8188", str(ctx.exception))
        self.assertIs(ctx.exception.blocked_by, holder)

    def test_port_busy_with_live_image_owner_is_reported_as_draining(self):
        import router
        busy = (True, "a ComfyUI backend is listening on port 8188", {"comfy_port_8188": "listening"})
        with patch.object(router, "gpu_busy", return_value=busy), \
             patch.object(tools, "_image_owner_snapshot", return_value={"pid": 4242}), \
             patch.object(tools, "_pid_is_live", return_value=True), \
             patch.object(tools, "_describe_port_8188_holder") as describe, \
             patch.dict(sys.modules, {"image_render": _FakeImageRender}):
            with self.assertRaises(tools.Port8188BusyError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertEqual(ctx.exception.blocked_by["kind"], "draining_image_job")
        self.assertEqual(ctx.exception.blocked_by["image_owner_pid"], 4242)
        describe.assert_not_called()

    def test_refuses_when_another_image_job_already_owns_the_backend(self):
        import router
        fake = _FakeImageRender
        self.owner_path.write_text(json.dumps({"pid": 999999999}), encoding="utf-8")
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(tools, "_pid_is_live", return_value=True), \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("another image render owns the backend", str(ctx.exception))

    def test_refuses_face_detail_with_realpro_flux_before_spawning_backend(self):
        # 2026-09-24 live failure: face_detail=true + model_profile=realpro_flux
        # always fails inside image_render.py's own graph builder, but only after
        # a real backend has already spent 1-5 minutes starting up. Fail fast,
        # before router/gpu_gate/subprocess are ever touched, so a batch with this
        # mistake on job 1 doesn't burn a launch (or block 5 unrelated jobs behind it)
        # for a combination that can never succeed.
        import router
        import gpu_gate
        fake = _FakeImageRender
        with patch.object(router, "gpu_busy") as gpu_busy, \
             patch.object(gpu_gate, "request") as gate_request, \
             patch("subprocess.Popen") as popen, \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({
                    "story": "s1", "prompt": "a photo",
                    "model_profile": "realpro_flux", "face_detail": True,
                })
        self.assertIn("face_detail is not available with model_profile=realpro_flux", str(ctx.exception))
        gpu_busy.assert_not_called()
        gate_request.assert_not_called()
        popen.assert_not_called()

    def test_face_detail_with_realvisxl_is_unaffected(self):
        # Negative control: the realpro_flux-specific guard must not reject the
        # default profile.
        import router
        import gpu_gate
        fake = _FakeImageRender
        fake_proc = MagicMock()
        fake_proc.pid = 4242
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.dict(sys.modules, {"image_render": fake}), \
             patch.object(tools, "_IMAGE_JOB_LOG_DIR", Path(self._tmp.name) / "logs"), \
             patch.object(tools.subprocess, "Popen", return_value=fake_proc):
            result = json.loads(tools.render_story_image({
                "story": "s1", "prompt": "a photo",
                "model_profile": "realvisxl", "face_detail": True,
            }))
        self.assertTrue(result.get("started"))
        self.assertTrue(result.get("face_detail"))

    def test_gateway_denial_blocks_the_launch(self):
        import router
        import gpu_gate
        fake = _FakeImageRender
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": False, "blocked": True}), \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo"})
        self.assertIn("Block", str(ctx.exception))

    def test_successful_launch_starts_a_background_process_and_never_blocks(self):
        import router
        import gpu_gate
        fake = _FakeImageRender
        fake_proc = MagicMock()
        fake_proc.pid = 4242
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.dict(sys.modules, {"image_render": fake}), \
             patch.object(tools, "_IMAGE_JOB_LOG_DIR", Path(self._tmp.name) / "logs"), \
             patch.object(tools.subprocess, "Popen", return_value=fake_proc) as popen:
            result = json.loads(tools.render_story_image({
                "story": "night greenhouse!", "prompt": "two women in a greenhouse at night",
                "seed": 7,
            }))
        self.assertTrue(result["started"])
        self.assertEqual(4242, result["pid"])
        self.assertEqual("night-greenhouse", result["story"])
        self.assertIn("story_image_job_status", result["note"])
        argv = popen.call_args.args[0]
        self.assertIn("--execute", argv)
        self.assertIn("--allow-model-load", argv)
        self.assertIn("night-greenhouse", argv)
        # hires_fix defaults to True, which means NOT passing --no-hires-fix
        # (the CLI's own default is already True; this call must not disable it).
        self.assertNotIn("--no-hires-fix", argv)
        # Regression: a prompt containing any character outside the Windows
        # console's codepage crashed image_render.py's own final status print
        # with UnicodeEncodeError (seen in production). The subprocess must
        # be launched with UTF-8 forced, the same way the ComfyUI backend
        # subprocess it starts internally already is.
        env = popen.call_args.kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertEqual("1", env.get("PYTHONUTF8"))
        self.assertEqual("utf-8", env.get("PYTHONIOENCODING"))

    def test_hires_fix_false_is_forwarded_to_the_cli(self):
        import router
        import gpu_gate
        fake = _FakeImageRender
        fake_proc = MagicMock()
        fake_proc.pid = 4243
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.dict(sys.modules, {"image_render": fake}), \
             patch.object(tools, "_IMAGE_JOB_LOG_DIR", Path(self._tmp.name) / "logs"), \
             patch.object(tools.subprocess, "Popen", return_value=fake_proc) as popen:
            tools.render_story_image({"story": "s1", "prompt": "a photo", "hires_fix": False})
        argv = popen.call_args.args[0]
        self.assertIn("--no-hires-fix", argv)

    def test_concurrent_calls_are_serialized_and_second_sees_first_owner_claim(self):
        # Regression for a self-audit finding: the desktop and a paired phone
        # can call render_story_image at nearly the same instant via
        # ThreadingHTTPServer. Without _IMAGE_RENDER_LAUNCH_LOCK, both could
        # pass the "no other image render owns the backend" check before
        # either subprocess claimed it, and both would go on to fight over
        # port 8188. The lock must force one to see the other's live claim.
        import router
        import gpu_gate
        import threading
        fake = _FakeImageRender
        owner_path = self.owner_path

        def fake_popen(argv, **kwargs):
            proc = MagicMock()
            proc.pid = 1000 + fake_popen.calls
            proc.poll.return_value = None  # still "running"
            fake_popen.calls += 1
            # Simulates image_render.py's own _write_owner(), which happens
            # very early in the subprocess, almost immediately after launch.
            owner_path.write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
            return proc
        fake_popen.calls = 0

        results: dict[str, str] = {}

        def call(story):
            try:
                results[story] = tools.render_story_image({"story": story, "prompt": "x"})
            except tools.ToolError as exc:
                results[story] = f"ERROR: {exc}"

        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "request", return_value={"granted": True}), \
             patch.dict(sys.modules, {"image_render": fake}), \
             patch.object(tools, "_IMAGE_JOB_LOG_DIR", Path(self._tmp.name) / "logs"), \
             patch.object(tools.subprocess, "Popen", side_effect=fake_popen), \
             patch.object(tools, "_pid_is_live", side_effect=lambda pid: pid is not None and int(pid) >= 1000):
            threads = [threading.Thread(target=call, args=(f"story{i}",)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        outcomes = list(results.values())
        successes = [o for o in outcomes if o.startswith("{")]
        failures = [o for o in outcomes if o.startswith("ERROR")]
        self.assertEqual(1, len(successes), outcomes)
        self.assertEqual(1, len(failures), outcomes)
        self.assertIn("another image render owns the backend", failures[0])

    def test_i2i_requires_a_reference_name(self):
        import router
        fake = _FakeImageRender
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.dict(sys.modules, {"image_render": fake}):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.render_story_image({"story": "s1", "prompt": "a photo", "mode": "i2i"})
        self.assertIn("reference_name is required", str(ctx.exception))

    def test_registered_as_tools_and_schemas(self):
        names = {item["function"]["name"] for item in tools.schemas()}
        self.assertIn("render_story_image", names)
        self.assertIn("story_image_job_status", names)
        self.assertIn("render_story_image", tools.TOOLS)
        self.assertIn("story_image_job_status", tools.TOOLS)

    def test_render_story_image_is_not_concurrency_safe(self):
        # It starts a GPU-owning backend; must stay off the parallel allow-list.
        self.assertNotIn("render_story_image", tools.CONCURRENCY_SAFE_TOOLS)

    def test_status_tool_is_concurrency_safe(self):
        self.assertIn("story_image_job_status", tools.CONCURRENCY_SAFE_TOOLS)

    def test_unpaired_phone_identity_is_denied_before_reaching_the_tool(self):
        # Regression for a self-audit finding: render_story_image was
        # accidentally reachable by any paired phone with no explicit grant,
        # unlike every other GPU-owning render action in this codebase.
        context = remote_security.ToolContext(source="phone", remote_identity="a" * 32)
        result = tools.call("render_story_image", {"story": "s1", "prompt": "x"}, context=context)
        self.assertIn("not permitted", result)

    def test_granted_phone_identity_reaches_the_tool_with_identity_injected(self):
        import router
        import gpu_gate
        fake = _FakeImageRender
        fake_proc = MagicMock()
        fake_proc.pid = 555
        fake_proc.poll.return_value = None
        context = remote_security.ToolContext(
            source="phone", remote_identity="a" * 32,
            allowed_tools=frozenset({"render_story_image"}))
        snapshot_mock = MagicMock(return_value={"mode": "auto"})
        request_mock = MagicMock(return_value={"granted": True})
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(gpu_gate, "snapshot", snapshot_mock), \
             patch.object(gpu_gate, "request", request_mock), \
             patch.dict(sys.modules, {"image_render": fake}), \
             patch.object(tools, "_IMAGE_JOB_LOG_DIR", Path(self._tmp.name) / "logs"), \
             patch.object(tools.subprocess, "Popen", return_value=fake_proc):
            result = tools.call("render_story_image", {"story": "s1", "prompt": "x"}, context=context)
        payload = json.loads(result)
        self.assertTrue(payload["started"])
        snapshot_mock.assert_called_once()
        # A granted phone call must substitute its own paired-identity grant
        # instead of falling through to the desktop-sidebar gpu_gate.request()
        # path, exactly like start_batch_render already does.
        request_mock.assert_not_called()


class StoryImageJobStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _patched_root(self):
        return patch.object(tools, "ROOT", self.root)

    def test_missing_story_is_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.story_image_job_status({})

    def test_no_manifest_and_dead_pid_reports_finished_or_crashed(self):
        with self._patched_root(), patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=False):
            result = json.loads(tools.story_image_job_status({"story": "s1", "pid": 123}))
        self.assertEqual("finished_or_crashed", result["state"])
        self.assertFalse(result["manifest_found"])

    def test_alive_pid_with_no_manifest_reports_running(self):
        with self._patched_root(), patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=True):
            result = json.loads(tools.story_image_job_status({"story": "s1", "pid": 123}))
        self.assertEqual("running", result["state"])

    def test_manifest_with_complete_status_is_reported_complete_even_if_pid_died(self):
        manifests_dir = self.root / "outputs" / "stories" / "s1" / "manifests"
        manifests_dir.mkdir(parents=True)
        (manifests_dir / "image_abc.json").write_text(
            json.dumps({"status": "complete", "outputs": [{"filename": "x.png"}]}),
            encoding="utf-8")
        with self._patched_root(), patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=False):
            result = json.loads(tools.story_image_job_status({"story": "s1", "pid": 123}))
        self.assertEqual("complete", result["state"])
        self.assertTrue(result["manifest_found"])
        self.assertEqual("x.png", result["manifest"]["outputs"][0]["filename"])

    def test_manifest_from_before_this_job_launched_is_not_reported_complete(self):
        # Re-rendering an existing story: the previous still's manifest must
        # not be presented as this job's result (it would be shown inline as
        # the new image for review).
        manifests_dir = self.root / "outputs" / "stories" / "s1" / "manifests"
        manifests_dir.mkdir(parents=True)
        old = manifests_dir / "image_old.json"
        old.write_text(json.dumps({"status": "complete", "outputs": [{"filename": "old.png"}]}),
                       encoding="utf-8")
        launched = time.time() - 60
        os.utime(old, (launched - 3600, launched - 3600))
        log_path = self.root / f"s1_{time.strftime('%Y%m%d_%H%M%S', time.localtime(launched))}.log"
        log_path.write_text("starting backend\n", encoding="utf-8")
        args = {"story": "s1", "pid": 123, "log": str(log_path)}
        with self._patched_root(), patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=True):
            result = json.loads(tools.story_image_job_status(args))
            self.assertEqual("running", result["state"])
            self.assertFalse(result["manifest_found"])
            new = manifests_dir / "image_new.json"
            new.write_text(json.dumps({"status": "complete", "outputs": [{"filename": "new.png"}]}),
                           encoding="utf-8")
            later = manifests_dir / "image_later.json"
            later.write_text(json.dumps({"status": "complete", "outputs": [{"filename": "later.png"}]}),
                             encoding="utf-8")
            os.utime(later, (time.time() + 600, time.time() + 600))
            result = json.loads(tools.story_image_job_status(args))
        self.assertEqual("complete", result["state"])
        self.assertEqual("new.png", result["manifest"]["outputs"][0]["filename"])

    def test_log_tail_is_included_when_log_path_given(self):
        log_path = self.root / "job.log"
        log_path.write_text("line one\nline two\n", encoding="utf-8")
        with self._patched_root(), patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=False):
            result = json.loads(tools.story_image_job_status({
                "story": "s1", "pid": 123, "log": str(log_path),
            }))
        self.assertIn("line two", result["log_tail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
