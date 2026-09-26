#!/usr/bin/env python3
"""Inline review cards for story stills, and announcing renders that land late.

Two production gaps these cover (2026-09-24):

1. render_story_image_batch returns an aggregate shape that
   collect_story_media_artifacts did not understand, and every tool_result
   reaching server.push is clipped to 4000 chars — shorter than one real
   Flux manifest — so no story still ever produced an inline card.
2. A render launched by render_story_image / comfy_generate can finish after
   the turn ended; /api/render_watch now resolves it and saves the card.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import file_edit_gate
import gpu_gate
import server
import store


def _big_graph() -> dict:
    # A real realpro_flux manifest carries the full ComfyUI graph and is
    # ~4.4 KB on disk on its own; pad to the same order of magnitude.
    return {str(i): {"class_type": "CLIPTextEncodeFlux",
                     "inputs": {"clip_l": "wide interior of a modest apartment " * 4,
                                "t5xxl": "wide interior of a modest apartment " * 4,
                                "guidance": 3.5}} for i in range(12)}


class _StoryTree:
    """Throwaway allow-listed story roots, patched onto server."""

    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.stories = self.base / "stories"
        self.comfy = self.stories / "_comfy_output"
        self.comfy.mkdir(parents=True)
        for attr, value in (("STORY_OUTPUT_ROOT", self.stories),
                            ("STORY_IMAGE_ROOT", self.comfy)):
            p = patch.object(server, attr, value)
            p.start()
            test.addCleanup(p.stop)

    def still(self, name: str, body: bytes, subfolder: str = "stories/s1/renders") -> dict:
        dest = self.comfy / subfolder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return {"filename": name, "subfolder": subfolder, "type": "output"}


def _manifest(prompt_id: str, output: dict) -> dict:
    return {"story": "s1", "model_profile": "realpro_flux", "status": "complete",
            "prompt_id": prompt_id, "graph": _big_graph(), "outputs": [output]}


def _batch_result(tree: _StoryTree) -> str:
    """Same shape tools.render_story_image_batch returns: 2 done, 1 failed, 1 not started."""
    a = tree.still("c001_start_00001_.png", b"still-a")
    b = tree.still("c001_end_00001_.png", b"still-b")
    completed = [
        {"index": 0, "story": "s1", "prompt_preview": "start", "pid": 101, "log": "x.log",
         "manifest": _manifest("p-a", a), "outputs": [dict(a, path="ignored")]},
        {"index": 1, "story": "s1", "prompt_preview": "end", "pid": 102, "log": "y.log",
         "manifest": _manifest("p-b", b), "outputs": [dict(b, path="ignored")]},
    ]
    failures = [{"index": 2, "story": "s1", "prompt_preview": "mid", "pid": 103,
                 "phase": "await", "error": "finished_without_manifest",
                 "status": {"state": "finished_or_crashed", "manifest": None,
                            "log_tail": "loading model\nCUDA out of memory"}}]
    pending = [{"index": 3, "story": "s1", "reason": "not_started_after_failure"}]
    return json.dumps({
        "batch": True, "total": 4, "completed_count": 2, "failure_count": 1,
        "pending_count": 1, "completed": completed, "failures": failures,
        "pending": pending, "review": None, "next_step": "Some stills failed.",
    }, indent=2)


def _ready(arts: list[dict]) -> list[dict]:
    return [a for a in arts if a.get("filename")]


def _foreign_blocked_batch() -> str:
    """All-launch-failure batch: short enough that the clipped tool_result parses too."""
    blocked_by = {"kind": "foreign_backend", "port": 8188,
                  "summary": "port 8188 is held by pid 4242 (started 2026-09-24 00:10). "
                             "The stills renderer only runs on its own private ComfyUI."}
    return json.dumps({
        "batch": True, "total": 3, "completed_count": 0, "failure_count": 1, "pending_count": 2,
        "completed": [],
        "failures": [{"index": 0, "story": "s1", "prompt_preview": "opening wide shot",
                      "phase": "launch", "blocked_by": blocked_by,
                      "error": "port 8188 busy: " + blocked_by["summary"]}],
        "pending": [{"index": 1, "story": "s1", "reason": "not_started_after_failure"},
                    {"index": 2, "story": "s1", "reason": "not_started_after_failure"}],
    })


class BatchArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tree = _StoryTree(self)

    def test_batch_result_yields_one_card_per_completed_output(self):
        arts = _ready(server.collect_media_artifacts("render_story_image_batch",
                                                     _batch_result(self.tree)))
        self.assertEqual(["c001_start_00001_.png", "c001_end_00001_.png"],
                         [a["filename"] for a in arts])
        self.assertEqual(["p-a", "p-b"], [a["prompt_id"] for a in arts])
        self.assertTrue(all(a["status"] == "ready" and a["root"] == "story_comfy" for a in arts))
        self.assertEqual("outputs/stories/s1/manifests/image_p-a.json", arts[0]["manifest_relpath"])

    def test_half_failed_batch_cards_follow_ready_ones_in_order(self):
        arts = server.collect_media_artifacts("render_story_image_batch", _batch_result(self.tree))
        self.assertEqual(["ready", "ready", "error", "not_started"], [a["status"] for a in arts])

    def test_await_failure_card_names_the_frame_and_why(self):
        arts = server.collect_media_artifacts("render_story_image_batch", _batch_result(self.tree))
        err = arts[2]
        self.assertEqual("", err["filename"])
        self.assertEqual("batch item 2: mid", err["label"])
        self.assertEqual(2, err["batch_index"])
        self.assertEqual("await", err["phase"])
        self.assertEqual("finished_without_manifest (pid 103) \u2014 CUDA out of memory", err["note"])

    def test_timed_out_failure_note(self):
        payload = json.dumps({"batch": True, "completed": [], "pending": [],
                              "failures": [{"index": 0, "story": "s1", "prompt_preview": "x",
                                            "phase": "await", "pid": 7, "error": "timed_out",
                                            "status": {"state": "running"}}]})
        arts = server.collect_media_artifacts("render_story_image_batch", payload)
        self.assertEqual(["timed_out (pid 7)"], [a["note"] for a in arts])

    def test_launch_failure_card_summarises_foreign_port_owner(self):
        arts = server.collect_media_artifacts("render_story_image_batch", _foreign_blocked_batch())
        err = arts[0]
        self.assertEqual("error", err["status"])
        self.assertEqual("batch item 0: opening wide shot", err["label"])
        self.assertTrue(err["note"].startswith("foreign_backend: port 8188 is held by pid 4242"))
        self.assertLessEqual(len(err["note"]), 240)

    def test_not_started_jobs_share_one_summary_card(self):
        arts = server.collect_media_artifacts("render_story_image_batch", _foreign_blocked_batch())
        self.assertEqual(["error", "not_started"], [a["status"] for a in arts])
        pending = arts[1]
        self.assertEqual("2 batch items (1, 2)", pending["label"])
        self.assertEqual([1, 2], pending["batch_indexes"])
        self.assertEqual("not started after failure \u2014 story s1", pending["note"])
        one = server.collect_media_artifacts("render_story_image_batch", _batch_result(self.tree))[3]
        self.assertEqual("batch item 3", one["label"])

    def test_batch_with_malformed_failure_still_yields_a_card(self):
        payload = json.dumps({"batch": True, "completed": [], "failures": [{"error": "x"}, "junk"],
                              "pending": []})
        arts = server.collect_media_artifacts("render_story_image_batch", payload)
        self.assertEqual([("error", "batch item ?", "x")],
                         [(a["status"], a["label"], a["note"]) for a in arts])

    def test_clipped_result_is_why_the_full_result_is_needed(self):
        # What server.push used to receive. Documents the second root cause.
        full = _batch_result(self.tree)
        self.assertGreater(len(full), 4000)
        self.assertEqual([], server.collect_media_artifacts("render_story_image_batch", full[:4000]))

    def test_extend_unique_artifacts_drops_repeat_files_keeps_error_locators(self):
        arts = _ready(server.collect_media_artifacts("render_story_image_batch",
                                                     _batch_result(self.tree)))
        target: list[dict] = []
        self.assertEqual(2, len(server.extend_unique_artifacts(target, arts)))
        self.assertEqual([], server.extend_unique_artifacts(target, [dict(arts[0])]))
        err = {"status": "error", "filename": ""}
        self.assertEqual([err], server.extend_unique_artifacts(target, [err]))
        self.assertEqual([err], server.extend_unique_artifacts(target, [dict(err)]))
        self.assertEqual(4, len(target))

    def test_extend_unique_artifacts_keeps_one_card_per_batch_failure(self):
        batch = _batch_result(self.tree)
        target: list[dict] = []
        first = server.collect_media_artifacts("render_story_image_batch", batch)
        self.assertEqual(4, len(server.extend_unique_artifacts(target, first)))
        again = server.collect_media_artifacts("render_story_image_batch", batch)
        self.assertEqual([], server.extend_unique_artifacts(target, again))
        # A different failure (other frame, or a new pid on retry) is a new card.
        other = json.loads(batch)
        other["completed"], other["pending"] = [], []
        other["failures"][0]["pid"] = 104
        added = server.extend_unique_artifacts(
            target, server.collect_media_artifacts("render_story_image_batch", json.dumps(other)))
        self.assertEqual(["finished_without_manifest (pid 104) \u2014 CUDA out of memory"],
                         [a["note"] for a in added])


class EmitToolResultTests(unittest.TestCase):
    def test_media_tool_gets_clipped_result_plus_full_internal_event(self):
        events = []
        full = "{" + "x" * 9000 + "}"
        agent._emit_tool_result(lambda k, p: events.append((k, p)), "render_story_image_batch", full)
        self.assertEqual(["tool_result", agent.MEDIA_SOURCE_EVENT], [k for k, _ in events])
        self.assertEqual(4000, len(events[0][1]))
        self.assertEqual({"tool": "render_story_image_batch", "result": full},
                         json.loads(events[1][1]))

    def test_other_tools_and_errors_get_no_internal_event(self):
        events = []
        agent._emit_tool_result(lambda k, p: events.append(k), "search_docs", "{}")
        agent._emit_tool_result(lambda k, p: events.append(k), "render_story_image", "ERROR: busy")
        self.assertEqual(["tool_result", "tool_result"], events)


class _TurnHarness(unittest.TestCase):
    def setUp(self):
        self.tree = _StoryTree(self)
        chats = self.tree.base / "chats"
        chats.mkdir()
        for obj, attr, value in (
                (store, "DIR", chats),
                (server, "RENDER_WATCH_PATH", self.tree.base / "render_watch.json"),
                (server.learning, "record", lambda *a, **k: None),
                (server.memory_extractor, "enqueue_turn", lambda *a, **k: None)):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)
        gate_dir = tempfile.TemporaryDirectory()
        self.addCleanup(gate_dir.cleanup)
        for mod in (gpu_gate, file_edit_gate):
            p = patch.object(mod, "STATE_FILE", Path(gate_dir.name) / f"{mod.__name__}.json")
            p.start()
            self.addCleanup(p.stop)
        os.environ["LOCAL_AGENT_TRACING"] = "0"
        self.conv = store.create("render stills", model="stub-model", workspace="general")

    def _turn(self, tool_calls: list[tuple[str, str]]) -> list[dict]:
        def fake_answer(history, push, **kwargs):
            for name, result in tool_calls:
                push("tool", json.dumps({"tool": name, "args": {}}))
                agent._emit_tool_result(push, name, result)
            return "done"

        h = object.__new__(server.Handler)
        h.wfile = io.BytesIO()
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda: None
        h._csrf_cookie = lambda: None
        with patch.object(agent, "answer", fake_answer):
            h._send_turn({"id": self.conv["id"], "message": "go", "prefer": "auto"})
        out = []
        for block in h.wfile.getvalue().decode().split("\n\n"):
            if block.startswith("data: "):
                out.append(json.loads(block[6:]))
        return out


class TurnMediaCardTests(_TurnHarness):
    def test_batch_turn_streams_and_stores_one_card_per_still(self):
        events = self._turn([("render_story_image_batch", _batch_result(self.tree))])
        kinds = [e["kind"] for e in events]
        self.assertNotIn(agent.MEDIA_SOURCE_EVENT, kinds)  # internal only
        media = [json.loads(e["data"]) for e in events if e["kind"] == "media"]
        self.assertEqual(["c001_start_00001_.png", "c001_end_00001_.png", "", ""],
                         [m["filename"] for m in media])
        self.assertEqual(["ready", "ready", "error", "not_started"], [m["status"] for m in media])
        # Cards follow their tool_result so the GUI mounts them under it.
        self.assertLess(kinds.index("tool_result"), kinds.index("media"))
        stored = store.load(self.conv["id"])["messages"][-1]
        self.assertEqual(4, len(stored["media_artifacts"]))
        self.assertEqual("batch item 2: mid", stored["media_artifacts"][2]["label"])

    def test_same_still_reported_twice_in_one_turn_is_one_card(self):
        batch = _batch_result(self.tree)
        one = json.loads(batch)["completed"][0]
        status = json.dumps({"state": "complete", "story": "s1", "manifest": one["manifest"],
                             "log_tail": "z" * 3000})
        events = self._turn([("render_story_image_batch", batch),
                             ("story_image_job_status", status)])
        self.assertEqual(4, sum(1 for e in events if e["kind"] == "media"))

    def test_short_failed_batch_parsed_twice_is_one_card_each(self):
        # Under 4000 chars, so the clipped tool_result AND the full internal
        # event both parse; the failure and not-started cards must not double.
        batch = _foreign_blocked_batch()
        self.assertLess(len(batch), 4000)
        events = self._turn([("render_story_image_batch", batch)])
        media = [json.loads(e["data"]) for e in events if e["kind"] == "media"]
        self.assertEqual(["error", "not_started"], [m["status"] for m in media])
        stored = store.load(self.conv["id"])["messages"][-1]
        self.assertEqual(2, len(stored["media_artifacts"]))

    def test_batch_re_reported_in_one_turn_does_not_pile_up_error_cards(self):
        batch = _batch_result(self.tree)
        events = self._turn([("render_story_image_batch", batch),
                             ("render_story_image_batch", batch)])
        self.assertEqual(4, sum(1 for e in events if e["kind"] == "media"))


class RenderWatchTests(_TurnHarness):
    def _launch(self) -> None:
        started = json.dumps({"started": True, "pid": 4242, "story": "s1",
                              "log": "s1_20260924_010203.log"})
        self._turn([("render_story_image", started)])

    def _status(self, state: str, output: dict | None = None, log_tail: str = "") -> str:
        manifest = _manifest("p-late", output) if output else None
        return json.dumps({"state": state, "story": "s1", "manifest": manifest,
                           "log_tail": log_tail})

    def test_launch_registers_a_watch_for_this_chat(self):
        self._launch()
        watches = json.loads(server.RENDER_WATCH_PATH.read_text(encoding="utf-8"))
        self.assertEqual(1, len(watches))
        self.assertEqual(("story_image", self.conv["id"], "running", 4242),
                         (watches[0]["kind"], watches[0]["cid"], watches[0]["status"],
                          watches[0]["pid"]))

    def test_late_completion_is_saved_onto_the_reply_and_reported_once(self):
        self._launch()
        out = self.tree.still("late_00001_.png", b"late-bytes")
        with patch.object(server.tools, "story_image_job_status",
                          return_value=self._status("running")):
            first = server.poll_render_watches(force=True)
        self.assertEqual("running", first["watches"][0]["status"])
        with patch.object(server.tools, "story_image_job_status",
                          return_value=self._status("complete", out)):
            done = server.poll_render_watches(force=True)
        watch = done["watches"][0]
        self.assertEqual("complete", watch["status"])
        self.assertEqual(["late_00001_.png"], [a["filename"] for a in watch["artifacts"]])
        self.assertEqual(store.load(self.conv["id"])["title"], watch["title"])
        reply = store.load(self.conv["id"])["messages"][-1]
        self.assertEqual("assistant", reply["role"])
        self.assertEqual(1, len(reply["media_artifacts"]))
        self.assertTrue(reply["media_artifacts"][0]["late"])
        self.assertEqual(watch["id"], reply["media_artifacts"][0]["watch_id"])
        # Resolved once: a later poll does not re-check or re-attach.
        with patch.object(server.tools, "story_image_job_status") as status:
            server.poll_render_watches(force=True)
        status.assert_not_called()
        self.assertEqual(1, len(store.load(self.conv["id"])["messages"][-1]["media_artifacts"]))

    def test_file_the_turn_already_showed_is_not_added_again(self):
        out = self.tree.still("late_00001_.png", b"late-bytes")
        started = json.dumps({"started": True, "pid": 4242, "story": "s1", "log": "s1.log"})
        self._turn([("render_story_image", started),
                    ("await_story_image_job", self._status("complete", out))])
        with patch.object(server.tools, "story_image_job_status",
                          return_value=self._status("complete", out)):
            watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual("complete", watch["status"])
        self.assertEqual([], watch["artifacts"])
        self.assertEqual(1, len(store.load(self.conv["id"])["messages"][-1]["media_artifacts"]))

    def test_crashed_render_is_reported_as_a_failure_card(self):
        self._launch()
        with patch.object(server.tools, "story_image_job_status",
                          return_value=self._status("finished_or_crashed",
                                                    log_tail="loading\nCUDA out of memory")):
            watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual("failed", watch["status"])
        self.assertEqual("CUDA out of memory", watch["note"])
        card = store.load(self.conv["id"])["messages"][-1]["media_artifacts"][0]
        self.assertEqual(("error", ""), (card["status"], card["filename"]))

    def test_watch_waits_while_its_chat_has_an_active_turn(self):
        self._launch()
        with server._active_turns_lock:
            server._active_turns.add(self.conv["id"])
        self.addCleanup(server._active_turns.discard, self.conv["id"])
        with patch.object(server.tools, "story_image_job_status") as status:
            watch = server.poll_render_watches(force=True)["watches"][0]
        status.assert_not_called()
        self.assertEqual("running", watch["status"])

    def test_comfy_generate_registers_and_resolves_via_comfy_job_status(self):
        shared = self.tree.base / "ComfyUI-Shared" / "output"
        shared.mkdir(parents=True)
        (shared / "clip_00001.mp4").write_bytes(b"mp4")
        with patch.object(server, "SHARED_OUTPUT_ROOT", shared.resolve()):
            self._turn([("comfy_generate", json.dumps({"status": "enqueued",
                                                       "prompt_id": "8182b9d1-aa"}))])
            complete = json.dumps({"state": "complete", "prompt_id": "8182b9d1-aa",
                                   "outputs": [{"filename": "clip_00001.mp4", "subfolder": ""}]})
            with patch.object(server.tools, "comfy_job_status", return_value=complete) as st:
                watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual({"prompt_id": "8182b9d1-aa", "timeout_s": 0}, st.call_args.args[0])
        self.assertEqual("complete", watch["status"])
        self.assertEqual("video", watch["artifacts"][0]["kind"])

    def test_old_finished_records_are_pruned(self):
        self._launch()
        watches = json.loads(server.RENDER_WATCH_PATH.read_text(encoding="utf-8"))
        watches[0].update({"status": "complete", "finished_at": 1.0})
        server.RENDER_WATCH_PATH.write_text(json.dumps(watches), encoding="utf-8")
        self.assertEqual([], server.poll_render_watches(force=True)["watches"])


class ChatRenderWatchTests(_TurnHarness):
    """start_current_chat_render video batches announce their mp4s late (2026-09-24d).

    The job is chat_render_jobs' <jobs>/<cid>/render_<stamp>/ folder; the
    runner (work/batch_render_folder.py) writes <job>/renders/<key>.mp4,
    records it in <job>/batch_manifest.json and logs "Batch complete:" last.
    """

    def setUp(self):
        super().setUp()
        self.jobs = (self.tree.base / "render_jobs").resolve()
        self.job = self.jobs / self.conv["id"] / "render_20260924_013000"
        for sub in ("renders", "img0", "video_refs", "batch_runtime/logs",
                    "batch_runtime/output"):
            (self.job / sub).mkdir(parents=True)
        # Copies of the chat's uploads and the runner's Comfy scratch: never served.
        (self.job / "img0" / "character.png").write_bytes(b"upload-copy")
        (self.job / "video_refs" / "0001.mp4").write_bytes(b"source-chunk")
        (self.job / "batch_runtime" / "output" / "batch_0001_00001.mp4").write_bytes(b"raw")
        self.log = self.job / "batch_runtime" / "logs" / "agent_batch_20260924_013000.log"
        self.log.write_text("[2026-09-24T01:30:01] render plan\n", encoding="utf-8")
        self.live = True
        for obj, attr, value in (
                (server, "CHAT_RENDER_JOBS_ROOT", self.jobs),
                (server.tools, "_pid_is_live", lambda pid: self.live)):
            p = patch.object(obj, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def _result(self, planned: int = 2, limit: int | None = None) -> str:
        # Same shape tools.start_current_chat_render returns. Skipped-prompt
        # provenance pushes "launch" past the 4000-char tool_result clip.
        prepared = {"job_folder": str(self.job), "prompt_count": planned, "provenance": {
            "conversation_id": self.conv["id"],
            "skipped_incomplete_or_invalid_prompts": [{"prompt": 3, "errors": ["e" * 4200]}]}}
        launch = {"started": True, "pid": 5150, "job_folder": str(self.job),
                  "planned_renders": planned, "limit": limit, "log": str(self.log),
                  "note": "The runner owns its queue lock."}
        return json.dumps({"prepared": prepared, "launch": launch}, indent=2)

    def _done(self, key: str, body: bytes) -> dict:
        out = self.job / "renders" / f"{key}.mp4"
        out.write_bytes(body)
        return {"status": "done", "output_path": str(out), "seed": 7, "attempt": 1}

    def _finish(self, renders: dict, log_lines: str = "", *, exited: bool = True) -> None:
        (self.job / "batch_manifest.json").write_text(
            json.dumps({"job": str(self.job), "renders": renders}), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(log_lines)
        self.live = not exited

    def _watches(self) -> list[dict]:
        return json.loads(server.RENDER_WATCH_PATH.read_text(encoding="utf-8"))

    def test_only_the_renders_folder_of_a_job_is_servable(self):
        good = self._done("0001", b"mp4-a")
        rel = f"{self.conv['id']}/render_20260924_013000"
        self.assertEqual(Path(good["output_path"]).resolve(), server.resolve_generated_media(
            "chat_render", f"{rel}/renders", "0001.mp4", kinds="video"))
        body, code, ctype = server.generated_media_payload("chat_render", f"{rel}/renders",
                                                           "0001.mp4")
        self.assertEqual((b"mp4-a", 200, "video/mp4"), (body, code, ctype))
        (self.job / "renders" / "still.png").write_bytes(b"png")
        for subfolder, name in ((f"{rel}/img0", "character.png"),
                                (f"{rel}/video_refs", "0001.mp4"),
                                (f"{rel}/batch_runtime/output", "batch_0001_00001.mp4"),
                                (f"{rel}/renders", "still.png"),
                                (f"{rel}/renders/..", "chat_render_provenance.json"),
                                ("", "0001.mp4")):
            self.assertIsNone(server.resolve_generated_media(
                "chat_render", subfolder, name, kinds="media"), (subfolder, name))
        # The jobs root never widens the forbidden set.
        with patch.object(server, "EQUAL_SHARES_ROOT", self.jobs):
            self.assertIsNone(server.resolve_generated_media(
                "chat_render", f"{rel}/renders", "0001.mp4", kinds="video"))

    def test_native_launch_registers_a_chat_render_watch(self):
        result = self._result()
        self.assertGreater(len(result), 4000)
        events = self._turn([("start_current_chat_render", result)])
        self.assertNotIn(agent.MEDIA_SOURCE_EVENT, [e["kind"] for e in events])
        self.assertEqual([], [e for e in events if e["kind"] == "media"])
        [watch] = self._watches()
        self.assertEqual(("chat_render", self.conv["id"], "running", 5150),
                         (watch["kind"], watch["cid"], watch["status"], watch["pid"]))
        self.assertEqual(f"{self.conv['id']}/render_20260924_013000", watch["job"])
        self.assertEqual(self.log.name, watch["log"])
        self.assertEqual(2, watch["expected"])

    def test_folderless_start_render_registers_the_same_watch(self):
        import agentic_state
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        h = object.__new__(server.Handler)
        h.wfile = io.BytesIO()
        h.send_response = lambda *a, **k: None
        h.send_header = lambda *a, **k: None
        h.end_headers = lambda: None
        h._csrf_cookie = lambda: None
        with patch.object(agentic_state, "DIR", Path(state_dir.name)), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for start render")), \
             patch.object(agent.tools, "call", return_value=self._result()) as call:
            h._send_turn({"id": self.conv["id"], "message": "start render", "prefer": "auto"})
        call.assert_called_once()
        self.assertEqual("start_current_chat_render", call.call_args.args[0])
        [watch] = self._watches()
        self.assertEqual(("chat_render", 5150), (watch["kind"], watch["pid"]))
        self.assertIn("Batch render started", store.load(self.conv["id"])["messages"][-1]["content"])

    def test_waits_for_the_runner_then_attaches_its_videos_once(self):
        self._turn([("start_current_chat_render", self._result())])
        self._finish({}, exited=False)
        self.assertEqual("running", server.poll_render_watches(force=True)["watches"][0]["status"])
        self._finish({"0001": self._done("0001", b"mp4-a"), "0002": self._done("0002", b"mp4-b")},
                     "[..] Batch complete: 2/2 renders done\n")
        watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual(("complete", ""), (watch["status"], watch["note"]))
        self.assertEqual(["0001.mp4", "0002.mp4"], [a["filename"] for a in watch["artifacts"]])
        self.assertTrue(all(a["kind"] == "video" and a["root"] == "chat_render"
                            and a["label"].startswith("render 000") for a in watch["artifacts"]))
        reply = store.load(self.conv["id"])["messages"][-1]
        self.assertEqual(2, len(reply["media_artifacts"]))
        self.assertTrue(all(a["late"] and a["watch_id"] == watch["id"]
                            for a in reply["media_artifacts"]))
        art = reply["media_artifacts"][0]
        body, code, ctype = server.generated_media_payload(
            art["root"], art["subfolder"], art["filename"], art["sha256"])
        self.assertEqual((b"mp4-a", 200, "video/mp4"), (body, code, ctype))
        with patch.object(server, "_check_chat_render_watch") as check:
            server.poll_render_watches(force=True)
        check.assert_not_called()

    def test_log_marker_resolves_even_if_the_pid_was_reused(self):
        self._turn([("start_current_chat_render", self._result(planned=1))])
        self._finish({"0001": self._done("0001", b"mp4-a")},
                     "[..] Batch complete: 1/1 renders done\n", exited=False)
        self.assertEqual("complete", server.poll_render_watches(force=True)["watches"][0]["status"])

    def test_runner_crash_before_any_render_is_a_video_failure_card(self):
        self._turn([("start_current_chat_render", self._result())])
        self._finish({}, "Traceback (most recent call last):\n"
                         "RuntimeError: ComfyUI exited during startup rc=1\n")
        watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual("failed", watch["status"])
        self.assertEqual("RuntimeError: ComfyUI exited during startup rc=1", watch["note"])
        card = store.load(self.conv["id"])["messages"][-1]["media_artifacts"][0]
        self.assertEqual(("video", "error", ""), (card["kind"], card["status"], card["filename"]))

    def test_partial_batch_shows_its_videos_plus_one_summary_card(self):
        self._turn([("start_current_chat_render", self._result(planned=3))])
        self._finish({"0001": self._done("0001", b"mp4-a"),
                      "0002": {"status": "failed", "error": "2 attempts failed: timed out"}},
                     "[..] Batch complete: 1/3 renders done\n")
        watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual("complete", watch["status"])
        self.assertEqual("1 of 3 renders done; 0002 failed: 2 attempts failed: timed out",
                         watch["note"])
        self.assertEqual([("0001.mp4", "ready"), ("", "error")],
                         [(a["filename"], a["status"]) for a in watch["artifacts"]])

    def test_limit_sets_the_expected_count(self):
        self._turn([("start_current_chat_render", self._result(planned=5, limit=1))])
        self._finish({"0001": self._done("0001", b"mp4-a")}, "[..] Batch complete: 1/5\n")
        watch = server.poll_render_watches(force=True)["watches"][0]
        self.assertEqual(("complete", ""), (watch["status"], watch["note"]))

    def test_batches_outside_the_chat_jobs_root_are_not_watched(self):
        elsewhere = self.tree.base / "operator_job"
        elsewhere.mkdir()
        foreign = json.dumps({"started": True, "pid": 77, "job_folder": str(elsewhere),
                              "planned_renders": 1, "log": str(elsewhere / "x.log")})
        nested = json.dumps({"started": True, "pid": 78, "job_folder": str(self.job / "renders"),
                             "planned_renders": 1})
        self._turn([("start_batch_render", foreign), ("start_batch_render", nested),
                    ("start_current_chat_render", "ERROR: render preflight refused: busy"),
                    ("prepare_chat_render", json.dumps({"prepared": True,
                                                        "job_folder": str(self.job)}))])
        self.assertFalse(server.RENDER_WATCH_PATH.exists())
        # A bare start_batch_render on a chat job folder is the same job.
        self._turn([("start_batch_render", json.dumps(json.loads(self._result())["launch"]))])
        self.assertEqual(["chat_render"], [w["kind"] for w in self._watches()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
