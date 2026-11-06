#!/usr/bin/env python3
"""Stills batch queue, review gate, stale PID status — r93/r94 (no still-batch cap)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import remote_security
import tools


class _FakeImageRender:
    IMAGE_OWNER = None
    DEFAULT_NEGATIVE = "blurry, low quality"

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


class StalePidStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.owner_path = Path(self._tmp.name) / "image_render_owner.json"
        _FakeImageRender.IMAGE_OWNER = self.owner_path
        self.root_patch = patch.object(tools, "ROOT", Path(self._tmp.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_released_owner_and_dead_pid_not_running(self):
        self.owner_path.parent.mkdir(parents=True, exist_ok=True)
        self.owner_path.write_text(
            json.dumps({"pid": 0, "purpose": "released"}), encoding="utf-8")
        with patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=False), \
             patch.object(tools, "_image_owner_snapshot",
                          return_value={"pid": 0, "purpose": "released"}):
            result = json.loads(tools.story_image_job_status({"story": "clip15_start", "pid": 36964}))
        self.assertFalse(result["pid_running"])
        self.assertTrue(result["owner_released"])
        self.assertEqual(result["state"], "finished_or_crashed")

    def test_owner_released_forces_not_running_even_if_pid_check_flakes(self):
        with patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(tools, "_pid_is_live", return_value=True), \
             patch.object(tools, "_image_owner_snapshot",
                          return_value={"pid": 0, "purpose": "released"}), \
             patch.object(_FakeImageRender, "_port_open", return_value=False):
            # Re-bind snapshot path via image_render module for port check inside status
            result = json.loads(tools.story_image_job_status({"story": "s1", "pid": 111}))
        self.assertFalse(result["pid_running"])
        self.assertEqual(result["state"], "finished_or_crashed")


class RenderStoryImageBatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tools._STORY_STILLS_REVIEW_DIR = Path(self._tmp.name) / "review"

    def test_batch_runs_jobs_sequentially_and_summarizes(self):
        launches = []

        def fake_render(args):
            launches.append(args["story"])
            return json.dumps({
                "started": True,
                "pid": 1000 + len(launches),
                "story": args["story"],
                "log": f"{args['story']}.log",
            })

        def fake_await(args):
            return json.dumps({
                "state": "complete",
                "pid_running": False,
                "story": args["story"],
                "manifest": {"status": "complete", "outputs": [
                    {"filename": f"{args['story']}.png", "subfolder": args["story"]}
                ]},
                "outputs_resolved": [
                    {"filename": f"{args['story']}.png", "path": f"C:/{args['story']}.png"}
                ],
            })

        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job", side_effect=fake_await), \
             patch.object(tools, "time") as tmod:
            tmod.strftime.return_value = "2026-09-06T00:00:00Z"
            tmod.gmtime.return_value = None
            result = json.loads(tools.render_story_image_batch({
                "jobs": [
                    {"story": "clip_a_start", "prompt": "frame a"},
                    {"story": "clip_a_end", "prompt": "frame b"},
                ],
                "model_profile": "realpro_flux",
                "__conversation_id": "chat-batch-1",
            }))
        self.assertEqual(launches, ["clip_a_start", "clip_a_end"])
        self.assertEqual(result["completed_count"], 2)
        self.assertEqual(result["failure_count"], 0)
        self.assertTrue(result["review"]["pending_review"])
        self.assertIn("operator review", result["next_step"].lower())

    def test_batch_defaults_flux_profile_when_requested(self):
        seen = []

        def fake_render(args):
            seen.append(args.get("model_profile"))
            return json.dumps({"started": True, "pid": 1, "story": args["story"], "log": "x.log"})

        def fake_await(args):
            return json.dumps({
                "state": "complete", "story": args["story"],
                "manifest": {"status": "complete", "outputs": []},
                "outputs_resolved": [],
            })

        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job", side_effect=fake_await):
            tools.render_story_image_batch({
                "jobs": [{"story": "s1", "prompt": "p"}],
                "flux": True,
                "__conversation_id": "c1",
            })
        self.assertEqual(seen, ["realpro_flux"])


    def test_batch_accepts_more_than_former_24_job_cap(self):
        """Former product cap was 24; full CLIP sheets must queue past that."""
        launches = []

        def fake_render(args):
            launches.append(args["story"])
            return json.dumps({
                "started": True,
                "pid": 2000 + len(launches),
                "story": args["story"],
                "log": f"{args['story']}.log",
            })

        def fake_await(args):
            return json.dumps({
                "state": "complete",
                "pid_running": False,
                "story": args["story"],
                "manifest": {"status": "complete", "outputs": [
                    {"filename": f"{args['story']}.png", "subfolder": args["story"]}
                ]},
                "outputs_resolved": [
                    {"filename": f"{args['story']}.png", "path": f"C:/{args['story']}.png"}
                ],
            })

        n = 30
        jobs = [{"story": f"clip_{i:03d}_start", "prompt": f"frame {i}"} for i in range(n)]
        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job", side_effect=fake_await), \
             patch.object(tools, "time") as tmod:
            tmod.strftime.return_value = "2026-09-06T00:00:00Z"
            tmod.gmtime.return_value = None
            result = json.loads(tools.render_story_image_batch({
                "jobs": jobs,
                "model_profile": "realpro_flux",
                "__conversation_id": "chat-batch-30",
            }))
        self.assertEqual(len(launches), n)
        self.assertEqual(result["completed_count"], n)
        self.assertEqual(result["failure_count"], 0)
        self.assertEqual(result["pending_count"], 0)
        self.assertTrue(result["review"]["pending_review"])
        self.assertNotIn("capped", json.dumps(result).lower())

    def test_batch_stop_on_failure_leaves_pending(self):
        def fake_render(args):
            if args["story"] == "bad":
                raise tools.ToolError("boom")
            return json.dumps({"started": True, "pid": 1, "story": args["story"], "log": "x"})

        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job",
                          return_value=json.dumps({
                              "state": "complete", "story": "ok",
                              "manifest": {"status": "complete", "outputs": []},
                              "outputs_resolved": [],
                          })):
            result = json.loads(tools.render_story_image_batch({
                "jobs": [
                    {"story": "ok", "prompt": "p1"},
                    {"story": "bad", "prompt": "p2"},
                    {"story": "later", "prompt": "p3"},
                ],
                "__conversation_id": "c2",
            }))
        self.assertEqual(result["completed_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["pending_count"], 1)
        self.assertIsNone(result["review"])

    def _complete(self, args):
        return json.dumps({
            "state": "complete", "story": args["story"],
            "manifest": {"status": "complete", "outputs": []},
            "outputs_resolved": [],
        })

    def test_foreign_backend_fails_fast_with_named_holder(self):
        """2026-09-23: resident Grok-launched ComfyUI on 8188 blocked job 1."""
        holder = {"kind": "foreign_backend",
                  "summary": "port 8188 is held by pid 52504, launched by start_comfy_rockernow.bat."}
        calls = []

        def fake_render(args):
            calls.append(args["story"])
            raise tools.Port8188BusyError(f"{tools._PORT_8188_REFUSAL}: {holder['summary']}", holder)

        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job", side_effect=self._complete), \
             patch.object(tools, "time") as tmod:
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": f"s{i}", "prompt": "p"} for i in range(7)],
                "__conversation_id": "c-foreign",
            }))
        self.assertEqual(calls, ["s0"] * tools._FOREIGN_BACKEND_GRACE_ATTEMPTS)
        self.assertEqual(tmod.sleep.call_count, tools._FOREIGN_BACKEND_GRACE_ATTEMPTS - 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["pending_count"], 6)
        failure = result["failures"][0]
        self.assertEqual(failure["phase"], "launch")
        self.assertEqual(failure["blocked_by"]["kind"], "foreign_backend")
        self.assertIn("start_comfy_rockernow.bat", result["next_step"])
        self.assertIn("not flaky", result["next_step"])

    def test_draining_prior_job_is_retried_until_backend_clears(self):
        """Job N's manifest lands before its backend stops; job N+1 must wait, not fail."""
        draining = {"kind": "draining_image_job", "summary": "previous job still shutting down"}
        refusals = {"s1": 4}
        launches = []

        def fake_render(args):
            if refusals.get(args["story"], 0) > 0:
                refusals[args["story"]] -= 1
                raise tools.Port8188BusyError(tools._PORT_8188_REFUSAL, draining)
            launches.append(args["story"])
            return json.dumps({"started": True, "pid": 1, "story": args["story"], "log": "x"})

        with patch.object(tools, "render_story_image", side_effect=fake_render), \
             patch.object(tools, "await_story_image_job", side_effect=self._complete), \
             patch.object(tools, "time") as tmod:
            tmod.strftime.return_value = "2026-09-23T00:00:00Z"
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "s0", "prompt": "p"}, {"story": "s1", "prompt": "p"},
                         {"story": "s2", "prompt": "p"}],
                "__conversation_id": "c-drain",
            }))
        self.assertEqual(launches, ["s0", "s1", "s2"])
        self.assertEqual(result["completed_count"], 3)
        self.assertEqual(result["failure_count"], 0)
        self.assertEqual(tmod.sleep.call_count, 4)

    def test_router_wording_reaches_batch_as_structured_foreign_block(self):
        """End-to-end through the real render_story_image preflight (no spawn)."""
        import router
        holder = {"kind": "foreign_backend", "summary": "port 8188 is held by pid 52504."}
        busy = (True, "a ComfyUI backend is listening on port 8188", {"comfy_port_8188": "listening"})
        with patch.dict(sys.modules, {"image_render": _FakeImageRender}), \
             patch.object(router, "gpu_busy", return_value=busy), \
             patch.object(tools, "_describe_port_8188_holder", return_value=holder), \
             patch.object(tools, "time") as tmod:
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "s0", "prompt": "p"}, {"story": "s1", "prompt": "p"}],
                "__conversation_id": "c-router",
            }))
        self.assertEqual(result["failures"][0]["blocked_by"], holder)
        self.assertIn("already listening on port 8188", result["failures"][0]["error"])
        self.assertEqual(result["pending"][0]["reason"], "not_started_after_failure")
        self.assertEqual(tmod.sleep.call_count, tools._FOREIGN_BACKEND_GRACE_ATTEMPTS - 1)


class StoryStillsReviewGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tools._STORY_STILLS_REVIEW_DIR = Path(self._tmp.name) / "review"

    def test_present_then_video_blocked_until_approve(self):
        present = json.loads(tools.present_story_stills_for_review({
            "__conversation_id": "chat-gate",
            "story": "clip15",
            "stills": [{"story": "clip15_start", "outputs": [{"path": "a.png"}]}],
        }))
        self.assertTrue(present["pending_review"])
        block = tools._stills_review_blocks_video("chat-gate")
        self.assertIsNotNone(block)
        ctx = remote_security.ToolContext(conversation_id="chat-gate")
        refused = tools.call("start_current_chat_render", {}, context=ctx)
        self.assertTrue(refused.startswith("ERROR:"))
        self.assertIn("awaiting operator review", refused)

        with self.assertRaises(tools.ToolError):
            tools.approve_story_stills({
                "__conversation_id": "chat-gate",
                "operator_confirmed": False,
            })

        approved = json.loads(tools.approve_story_stills({
            "__conversation_id": "chat-gate",
            "operator_confirmed": True,
        }))
        self.assertTrue(approved["approved"])
        self.assertIsNone(tools._stills_review_blocks_video("chat-gate"))

    def test_comfy_generate_video_blocked_while_pending(self):
        tools.present_story_stills_for_review({
            "__conversation_id": "chat-vid",
            "story": "s",
            "stills": [{"story": "s", "outputs": []}],
        })
        ctx = remote_security.ToolContext(conversation_id="chat-vid")
        refused = tools.call("comfy_generate", {"action": "video", "prompt": "x"}, context=ctx)
        self.assertTrue(refused.startswith("ERROR:"))
        self.assertIn("awaiting operator review", refused)


class ContinuationAndApprovalAgentTests(unittest.TestCase):
    def test_continue_is_not_stills_approval(self):
        self.assertFalse(agent._operator_approved_story_stills("continue"))
        self.assertFalse(agent._operator_approved_story_stills("go on to the next step"))
        self.assertTrue(agent._operator_approved_story_stills("looks good"))
        self.assertTrue(agent._operator_approved_story_stills("approved"))
        self.assertTrue(agent._operator_approved_story_stills("go ahead with video"))

    def test_batch_clears_unfinished_plan_flag(self):
        history = [
            {"role": "assistant", "content": "planned",
             "tool_evidence": [{"tool": "plan_story_image", "outcome": "ok"}]},
            {"role": "assistant", "content": "rendered batch",
             "tool_evidence": [{"tool": "render_story_image_batch", "outcome": "ok"}]},
        ]
        self.assertFalse(agent._history_has_unfinished_story_image_plan(history))

    def test_approve_story_stills_blocked_without_approval_utterance(self):
        # Exercise the run_one guard via a minimal answer path is heavy; call the
        # predicate + simulate the guard condition the agent uses.
        latest = "continue"
        self.assertFalse(agent._operator_approved_story_stills(latest))
        self.assertIn("approve_story_stills", agent._SPECIALIST_PROJECT_TOOLS)
        self.assertIn("render_story_image_batch", agent._SPECIALIST_PROJECT_TOOLS)


class ImageDirectSchemaTests(unittest.TestCase):
    def test_gpu_image_schema_includes_batch_and_review_tools(self):
        names = [item["function"]["name"] for item in tools.schemas(profile="gpu_image")]
        self.assertEqual(list(tools.IMAGE_DIRECT_TOOLS), names)
        for needed in (
            "render_story_image_batch",
            "await_story_image_job",
            "present_story_stills_for_review",
            "approve_story_stills",
            "story_stills_review_status",
        ):
            self.assertIn(needed, names)


REPO = HERE.parent
_OPERATOR_STORY_DIR = REPO / "outputs" / "stories" / "Backrooms-Sitcom-Audition-Prompt-Pack"
_OPERATOR_RENDERS = REPO / "outputs" / "stories" / "_comfy_output" / "stories" / \
    "Backrooms-Sitcom-Audition-Prompt-Pack" / "renders"
# 2026-09-24 operator failure: this plain empty living room was presented and
# then narrated as "processed through the QA pipeline... SELECTED".
_OPERATOR_BAD_STILL = _OPERATOR_RENDERS / "fd51e60dfcda49ef8ac0fa8c9b1c860f_00001_.png"
# The scene-1 render that does show the actor (same story, earlier manifest).
_OPERATOR_ACTOR_STILL = _OPERATOR_RENDERS / "7cb428fb3e834544bd799bcb04ee63a7_00001_.png"
_OPERATOR_SCENE1_MANIFEST = _OPERATOR_STORY_DIR / "manifests" / \
    "image_62e576a9-8cde-42ea-b744-786b6c53ba3c.json"


def _real_qa_available() -> bool:
    try:
        import cv2  # noqa: F401
    except Exception:
        return False
    return all(p.is_file() for p in (
        _OPERATOR_BAD_STILL, _OPERATOR_ACTOR_STILL, _OPERATOR_SCENE1_MANIFEST,
        REPO / "models" / "opencv_face" / "face_detection_yunet_2023mar.onnx"))


class StoryStillQATests(unittest.TestCase):
    """render_story_image(_batch) stills carry a real creative_still_qa verdict."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for p in (patch.object(tools, "ROOT", self.root),
                  patch.object(tools, "_STORY_STILLS_REVIEW_DIR", self.root / "review"),
                  patch.object(tools, "_pid_is_live", return_value=False),
                  patch.object(tools, "_image_owner_snapshot",
                               return_value={"pid": 0, "purpose": "released"}),
                  patch.dict(sys.modules, {"image_render": _FakeImageRender})):
            p.start()
            self.addCleanup(p.stop)
        _FakeImageRender.IMAGE_OWNER = self.root / "owner.json"

    def _complete_render(self, story: str, prompt: str, image: Path | None = None,
                         stem: str = "image_a") -> Path:
        """Lay down what image_render.py leaves behind: a complete manifest + PNG."""
        out_dir = self.root / "outputs" / "stories" / "_comfy_output" / "stories" / story / "renders"
        out_dir.mkdir(parents=True, exist_ok=True)
        png = out_dir / f"{stem}_00001_.png"
        png.write_bytes(image.read_bytes() if image else b"\x89PNG fake")
        manifests = self.root / "outputs" / "stories" / story / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        (manifests / f"{stem}.json").write_text(json.dumps({
            "status": "complete", "story": story, "prompt": prompt,
            "outputs": [{"filename": png.name, "subfolder": f"stories\\{story}\\renders",
                         "type": "output"}],
        }), encoding="utf-8")
        return png

    def _fake_qa(self, ok=True, reasons=()):
        fake = MagicMock()
        fake.creative_approve.return_value = (
            ok, list(reasons),
            {"ok": ok, "reject_reasons": list(reasons), "mode": "actor_visible",
             "metrics": {"candidate_face_count": 1 if ok else 0}})
        return fake

    def test_completed_status_runs_creative_approve_with_manifest_prompt(self):
        png = self._complete_render("s1", "an actor stands centered on a taped mark")
        fake = self._fake_qa(ok=False, reasons=["expected_actor_visible_but_no_face_detected"])
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            first = json.loads(tools.story_image_job_status({"story": "s1", "pid": 5}))
            second = json.loads(tools.story_image_job_status({"story": "s1", "pid": 5}))
        self.assertEqual("complete", first["state"])
        fake.creative_approve.assert_called_once_with(
            png, prompt="an actor stands centered on a taped mark",
            anchor=None, clip=None, kind="last")
        qa = first["qa"]
        self.assertEqual("fail", qa["verdict"])
        self.assertIs(False, qa["ok"])
        self.assertEqual(["expected_actor_visible_but_no_face_detected"], qa["reject_reasons"])
        self.assertEqual("actor_visible", qa["report"]["mode"])
        self.assertEqual("creative_still_qa.creative_approve", qa["checker"])
        self.assertIn("does NOT check that the scene", qa["scope"])
        # Repeat polls reuse the stored verdict instead of re-running QA.
        self.assertEqual(qa["reject_reasons"], second["qa"]["reject_reasons"])

    def test_batch_carries_qa_into_completed_review_payload_and_summary(self):
        self._complete_render("s2", "empty corridor, nobody in frame")

        def fake_render(args):
            return json.dumps({"started": True, "pid": 7, "story": args["story"], "log": "s2.log"})

        fake = self._fake_qa(ok=True)
        with patch.dict(sys.modules, {"creative_still_qa": fake}), \
             patch.object(tools, "render_story_image", side_effect=fake_render):
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "s2", "prompt": "empty corridor, nobody in frame"}],
                "poll_s": 1, "__conversation_id": "chat-qa-1",
            }))
        self.assertEqual(1, result["completed_count"])
        self.assertEqual("pass", result["completed"][0]["qa"]["verdict"])
        self.assertEqual({"pass": 1}, result["qa_summary"]["counts"])
        self.assertTrue(result["qa_summary"]["all_passed"])
        self.assertIn("state each still's QA verdict", result["next_step"])
        state = json.loads(tools.story_stills_review_status({"__conversation_id": "chat-qa-1"}))
        self.assertEqual("pending_review", state["status"])
        self.assertEqual("pass", state["stills"][0]["qa"]["verdict"])

    def test_qa_crash_is_reported_as_error_never_as_pass(self):
        self._complete_render("s3", "an actor smiles")
        fake = MagicMock()
        fake.creative_approve.side_effect = RuntimeError("onnx load failed")
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = json.loads(tools.story_image_job_status({"story": "s3", "pid": 5}))["qa"]
        self.assertEqual("error", qa["verdict"])
        self.assertIsNone(qa["ok"])
        self.assertIn("onnx load failed", qa["error"])
        self.assertFalse((self.root / "outputs" / "stories" / "s3" / "still_qa").exists())

    def test_missing_output_file_is_not_run_not_pass(self):
        png = self._complete_render("s4", "an actor smiles")
        png.unlink()
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = json.loads(tools.story_image_job_status({"story": "s4", "pid": 5}))["qa"]
        self.assertEqual("not_run", qa["verdict"])
        fake.creative_approve.assert_not_called()
        # The record says where it looked, so a mis-resolved path is visible.
        self.assertIn("looked for", qa["error"])
        self.assertIn(str(png), qa["error"])

    def test_manifest_without_outputs_is_not_run_with_distinct_reason(self):
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = tools._story_still_qa([], prompt="an actor smiles", story="s4")
        self.assertEqual("not_run", qa["verdict"])
        self.assertIn("lists no output file", qa["error"])
        fake.creative_approve.assert_not_called()

    def test_resolver_finds_still_from_windows_or_posix_subfolder(self):
        # image_render stores ComfyUI's subfolder verbatim: backslashes from a
        # Windows ComfyUI (every real manifest under outputs/stories/), forward
        # slashes from a Linux one. Both must land on the same file whatever
        # pathlib flavour the checker runs under (fails on Linux/WSL without
        # the separator split in _resolve_story_still_outputs).
        png = self._complete_render("s5", "an actor smiles")
        manifest = json.loads((self.root / "outputs" / "stories" / "s5" / "manifests" /
                               "image_a.json").read_text(encoding="utf-8"))
        self.assertEqual("stories\\s5\\renders", manifest["outputs"][0]["subfolder"])
        for subfolder in ("stories\\s5\\renders", "stories/s5/renders", "stories\\s5/renders/"):
            variant = {**manifest, "outputs": [{**manifest["outputs"][0], "subfolder": subfolder}]}
            resolved = tools._resolve_story_still_outputs(variant)
            self.assertEqual(str(png), resolved[0]["path"], subfolder)
            self.assertEqual(str(png), resolved[0]["expected_path"], subfolder)
            self.assertEqual(subfolder, resolved[0]["subfolder"])

    def test_resolver_under_posix_pathlib_splits_windows_subfolder(self):
        # Models the failing platform on any host: a POSIX-flavoured root joins
        # "stories\\s6\\renders" as one literal segment unless the resolver
        # splits it. This is what made every still through story_image_job_status
        # report verdict=not_run ("no rendered output file was found on disk")
        # when this suite ran under a POSIX Python (2026-09-24u), while the
        # same code passed on Windows.
        expected = ("/srv/agent/outputs/stories/_comfy_output/stories/s6/renders/"
                    "image_a_00001_.png")
        files = {expected}

        class _PosixRoot(PurePosixPath):
            def is_file(self):
                return str(self) in files

        manifest = {"status": "complete", "outputs": [
            {"filename": "image_a_00001_.png", "subfolder": "stories\\s6\\renders",
             "type": "output"}]}
        with patch.object(tools, "ROOT", _PosixRoot("/srv/agent")):
            resolved = tools._resolve_story_still_outputs(manifest)
        self.assertEqual(expected, resolved[0]["expected_path"], resolved)
        self.assertEqual(expected, resolved[0]["path"], resolved)
        # And a still that really is missing names the path it looked for.
        files.clear()
        with patch.object(tools, "ROOT", _PosixRoot("/srv/agent")):
            qa = tools._story_still_qa(tools._resolve_story_still_outputs(manifest),
                                       prompt="an actor smiles", story="s6")
        self.assertEqual("not_run", qa["verdict"])
        self.assertIn(expected, qa["error"])

    def test_operator_approval_sets_continuity_anchor_for_next_still(self):
        first = self._complete_render("story-x", "an actor stands", stem="image_1")
        tools.present_story_stills_for_review({
            "story": "story x", "__conversation_id": "chat-anchor",
            "stills": [{"story": "story x", "outputs": [{"path": str(first)}]}],
        })
        self.assertIsNone(tools._story_qa_anchor("story x"))   # generated != approved
        approved = json.loads(tools.approve_story_stills(
            {"operator_confirmed": True, "__conversation_id": "chat-anchor"}))
        self.assertEqual({"story-x": str(first)}, approved["qa_anchors_recorded"])

        second = self._complete_render("story-x", "the same actor turns", stem="image_2")
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = tools._story_still_qa([{"path": str(second)}], prompt="the same actor turns",
                                       story="story-x")
        self.assertEqual(first, fake.creative_approve.call_args.kwargs["anchor"])
        self.assertEqual(str(first), qa["anchor"])

    # ── continuity-anchor registry (work/runtime/story_qa_anchors.json) ─────

    def _approve(self, story: str, png: Path, chat: str) -> dict:
        """Operator approval as the chat path does it: present, then approve."""
        tools.present_story_stills_for_review({
            "story": story, "__conversation_id": chat,
            "stills": [{"story": story, "outputs": [{"path": str(png)}]}],
        })
        return json.loads(tools.approve_story_stills(
            {"operator_confirmed": True, "__conversation_id": chat}))

    @staticmethod
    def _fake_render(story_slug: str):
        def fake_render(args):
            return json.dumps({"started": True, "pid": 7, "story": story_slug, "log": "x.log"})
        return fake_render

    def _drop_manifest(self, story: str, stem: str) -> None:
        # Two manifests written within the same tick would tie on mtime; the
        # anchor PNG stays on disk, only the earlier manifest goes.
        (self.root / "outputs" / "stories" / story / "manifests" / f"{stem}.json").unlink()

    def test_batch_passes_story_anchor_to_creative_approve_after_prior_approval(self):
        first = self._complete_render("leo-audition", "Leo stands on the mark", stem="image_1")
        self._approve("leo audition", first, "chat-a")
        self._drop_manifest("leo-audition", "image_1")
        second = self._complete_render("leo-audition", "Leo turns to camera", stem="image_2")
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}), \
             patch.object(tools, "render_story_image", side_effect=self._fake_render("leo-audition")):
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "leo audition", "prompt": "Leo turns to camera"}],
                "poll_s": 1, "__conversation_id": "chat-a",
            }))
        fake.creative_approve.assert_called_once_with(
            second, prompt="Leo turns to camera", anchor=first, clip=None, kind="last")
        qa = result["completed"][0]["qa"]
        self.assertEqual(str(first), qa["anchor"])
        self.assertEqual("story", qa["anchor_source"])
        self.assertEqual("leo-audition", qa["anchor_story"])
        self.assertTrue(qa["anchor_approved_at"])
        self.assertIn("approved for this story", qa["anchor_note"])
        # The verdict that reaches the review state carries the anchor too.
        state = json.loads(tools.story_stills_review_status({"__conversation_id": "chat-a"}))
        self.assertEqual(str(first), state["stills"][0]["qa"]["anchor"])

    def test_first_still_for_story_runs_qa_with_anchor_none_without_error(self):
        self.assertFalse(tools._story_qa_anchors_path().exists())
        png = self._complete_render("fresh-story", "an actor smiles")
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = json.loads(tools.story_image_job_status(
                {"story": "fresh story", "pid": 5, "__conversation_id": "chat-new"}))["qa"]
        fake.creative_approve.assert_called_once_with(
            png, prompt="an actor smiles", anchor=None, clip=None, kind="last")
        self.assertEqual("pass", qa["verdict"])
        self.assertIsNone(qa["anchor"])
        self.assertIsNone(qa["anchor_source"])
        self.assertIsNone(qa["anchor_story"])
        self.assertIn("first still", qa["anchor_note"])
        self.assertNotIn("error", qa)
        # Nothing was written just because a still was generated.
        self.assertFalse(tools._story_qa_anchors_path().exists())

    def test_approval_writes_and_updates_anchor_registry(self):
        registry = tools._story_qa_anchors_path()
        first = self._complete_render("leo-audition", "shot one", stem="image_1")
        self.assertFalse(registry.exists())
        approved = self._approve("leo audition", first, "chat-a")
        self.assertEqual({"leo-audition": str(first)}, approved["qa_anchors_recorded"])
        data = json.loads(registry.read_text(encoding="utf-8"))
        self.assertEqual(str(first), data["leo-audition"]["path"])
        self.assertEqual("chat-a", data["leo-audition"]["conversation_id"])
        self.assertTrue(data["leo-audition"]["approved_at"])
        self.assertEqual({"path": str(first), "story": "leo-audition",
                          "approved_at": data["leo-audition"]["approved_at"]},
                         data["_conversations"]["chat-a"])
        self.assertEqual(first, tools._story_qa_anchor("leo audition"))
        # A later approval for the same story replaces the anchor (last human-approved wins).
        second = self._complete_render("leo-audition", "shot two", stem="image_2")
        self._approve("leo audition", second, "chat-a")
        data = json.loads(registry.read_text(encoding="utf-8"))
        self.assertEqual(str(second), data["leo-audition"]["path"])
        self.assertEqual(str(second), data["_conversations"]["chat-a"]["path"])
        self.assertEqual(second, tools._story_qa_anchor("leo audition"))
        # Approving a still whose file is gone records nothing and does not fail approval.
        ghost = self.root / "ghost.png"
        result = self._approve("leo audition", ghost, "chat-a")
        self.assertTrue(result["approved"])
        self.assertEqual({}, result["qa_anchors_recorded"])
        self.assertEqual(second, tools._story_qa_anchor("leo audition"))

    def test_per_image_story_labels_fall_back_to_last_still_approved_in_chat(self):
        # Live 2026-09-24: the chat labelled one character's stills "Scene Start
        # Image 1" then "Scene Start Image 2", so a slug-keyed anchor never linked
        # them and the second "Leo" was never compared with the first.
        first = self._complete_render("Scene-Start-Image-1", "Leo stands", stem="image_1")
        self._approve("Scene Start Image 1", first, "chat-149")
        second = self._complete_render("Scene-Start-Image-2", "Leo stares at the wall", stem="image_2")
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}), \
             patch.object(tools, "render_story_image",
                          side_effect=self._fake_render("Scene-Start-Image-2")):
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "Scene Start Image 2", "prompt": "Leo stares at the wall"}],
                "poll_s": 1, "__conversation_id": "chat-149",
            }))
        fake.creative_approve.assert_called_once_with(
            second, prompt="Leo stares at the wall", anchor=first, clip=None, kind="last")
        qa = result["completed"][0]["qa"]
        self.assertEqual(str(first), qa["anchor"])
        self.assertEqual("conversation", qa["anchor_source"])
        self.assertEqual("Scene-Start-Image-1", qa["anchor_story"])
        self.assertIn("last still the operator approved in this chat", qa["anchor_note"])
        # Another chat does not inherit this chat's approval.
        other = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": other}):
            qa_other = tools._story_still_qa([{"path": str(second)}], prompt="Leo stares",
                                             story="Scene-Start-Image-2",
                                             conversation_id="chat-other")
        self.assertIsNone(other.creative_approve.call_args.kwargs["anchor"])
        self.assertIsNone(qa_other["anchor_source"])

    def test_story_anchor_wins_over_chat_fallback(self):
        a = self._complete_render("story-a", "a", stem="image_1")
        self._approve("story a", a, "chat-m")
        b = self._complete_render("story-b", "b", stem="image_2")
        self._approve("story b", b, "chat-m")
        found = tools._story_qa_anchor_lookup("story a", "chat-m")
        self.assertEqual((a, "story", "story-a"), (found["path"], found["source"], found["story_key"]))
        found = tools._story_qa_anchor_lookup("story c", "chat-m")
        self.assertEqual((b, "conversation", "story-b"),
                         (found["path"], found["source"], found["story_key"]))
        self.assertIsNone(tools._story_qa_anchor_lookup("story c", "")["path"])

    def test_corrupt_or_stale_anchor_registry_degrades_to_no_anchor(self):
        png = self._complete_render("s9", "an actor smiles")
        registry = tools._story_qa_anchors_path()
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("{not json", encoding="utf-8")
        fake = self._fake_qa()
        with patch.dict(sys.modules, {"creative_still_qa": fake}):
            qa = json.loads(tools.story_image_job_status(
                {"story": "s9", "pid": 5, "__conversation_id": "chat-c"}))["qa"]
        self.assertEqual("pass", qa["verdict"])
        self.assertIsNone(qa["anchor"])
        self.assertIsNone(fake.creative_approve.call_args.kwargs["anchor"])
        # Entries whose files no longer exist are ignored, for story and chat alike.
        registry.write_text(json.dumps({
            "s9": {"path": str(self.root / "gone.png")},
            "_conversations": {"chat-c": {"path": str(self.root / "gone2.png"), "story": "s9"}},
        }), encoding="utf-8")
        self.assertIsNone(tools._story_qa_anchor("s9", "chat-c"))
        # Wrong shapes never raise.
        registry.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(tools._story_qa_anchor("s9", "chat-c"))
        registry.write_text(json.dumps({"s9": "not-a-dict", "_conversations": "nope"}),
                            encoding="utf-8")
        self.assertIsNone(tools._story_qa_anchor("s9", "chat-c"))
        self.assertEqual(png, Path(fake.creative_approve.call_args.args[0]))

    @unittest.skipUnless(_real_qa_available(), "operator stills / cv2 / QA models not present")
    def test_regression_operator_empty_room_fails_real_qa_and_reaches_review(self):
        # The real image the operator was shown, checked by the real, unmocked
        # creative_still_qa against the scene-1 prompt it was meant to depict
        # (an actor on the taped mark). It must fail, and that verdict must
        # reach the review payload the chat reply is built from.
        sys.path.insert(0, str(REPO))
        full_prompt = json.loads(_OPERATOR_SCENE1_MANIFEST.read_text(encoding="utf-8"))["prompt"]
        self._complete_render("Backrooms-Sitcom-Audition-Prompt-Pack", full_prompt,
                              image=_OPERATOR_BAD_STILL)

        def fake_render(args):
            return json.dumps({"started": True, "pid": 7,
                               "story": "Backrooms-Sitcom-Audition-Prompt-Pack", "log": "x.log"})

        with patch.object(tools, "render_story_image", side_effect=fake_render):
            result = json.loads(tools.render_story_image_batch({
                "jobs": [{"story": "Backrooms Sitcom Audition Prompt Pack", "prompt": full_prompt}],
                "poll_s": 1, "__conversation_id": "chat-regress",
            }))
        qa = result["completed"][0]["qa"]
        self.assertEqual("fail", qa["verdict"], qa)
        self.assertIn("expected_actor_visible_but_no_face_detected", qa["reject_reasons"])
        self.assertEqual("actor_visible", qa["report"]["mode"])
        self.assertEqual({"fail": 1}, result["qa_summary"]["counts"])
        state = json.loads(tools.story_stills_review_status({"__conversation_id": "chat-regress"}))
        self.assertIn("expected_actor_visible_but_no_face_detected",
                      state["stills"][0]["qa"]["reject_reasons"])

    @unittest.skipUnless(_real_qa_available(), "operator stills / cv2 / QA models not present")
    def test_regression_unexpected_person_in_empty_prompt_fails_real_qa(self):
        sys.path.insert(0, str(REPO))
        png = self._complete_render("empty-pov", "empty corridor, nobody in frame",
                                    image=_OPERATOR_ACTOR_STILL)
        qa = tools._story_still_qa([{"path": str(png)}], prompt="empty corridor, nobody in frame",
                                   story="empty-pov")
        self.assertEqual("fail", qa["verdict"], qa)
        self.assertEqual("empty_pov", qa["report"]["mode"])
        self.assertTrue(any(r.startswith(("unexpected_face_in_empty_pov",
                                          "unexpected_person_in_empty_pov"))
                            for r in qa["reject_reasons"]), qa["reject_reasons"])


if __name__ == "__main__":
    unittest.main()
