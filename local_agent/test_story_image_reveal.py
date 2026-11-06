#!/usr/bin/env python3
"""server.py's resolve_story_image / reveal_story_image — the "see it, open its
folder" feature added on top of render_story_image.

resolve_story_image is the single security boundary between a manifest's
{filename, subfolder} (which the model / a tool result could in principle
influence) and both serving raw file bytes over HTTP and spawning
`explorer.exe`. These tests exercise it directly rather than through a live
HTTP server, matching this codebase's existing style for server.py tests
(see test_yield_gpu.py).
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import server
import store


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _patch_story_tree(test, tmp: Path) -> None:
    """Point both allow-listed story roots at a throwaway tree."""
    stories = (tmp / "stories").resolve()
    comfy = (stories / "_comfy_output").resolve()
    comfy.mkdir(parents=True)
    test.stories = stories
    test.comfy = comfy
    p_out = patch.object(server, "STORY_OUTPUT_ROOT", stories)
    p_img = patch.object(server, "STORY_IMAGE_ROOT", comfy)
    p_out.start()
    p_img.start()
    test.addCleanup(p_out.stop)
    test.addCleanup(p_img.stop)


class ResolveStoryImageTests(unittest.TestCase):
    def setUp(self):
        # Build a throwaway tree instead of touching the real project output.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _patch_story_tree(self, Path(self._tmp.name))
        self.root = self.comfy

    def _write(self, rel_path: str, content: bytes = b"fake-png-bytes") -> Path:
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_valid_file_resolves(self):
        self._write("stories/s1/renders/20260831/img_00001_.png")
        result = server.resolve_story_image("stories/s1/renders/20260831", "img_00001_.png")
        self.assertIsNotNone(result)
        self.assertTrue(result.is_file())

    def test_empty_filename_is_rejected(self):
        self.assertIsNone(server.resolve_story_image("stories/s1", ""))

    def test_directory_traversal_in_filename_is_rejected(self):
        self._write("secret.txt", b"not an image")
        self.assertIsNone(server.resolve_story_image("stories/s1", "../secret.txt"))
        self.assertIsNone(server.resolve_story_image("stories/s1", "../../secret.txt"))

    def test_directory_traversal_in_subfolder_is_rejected(self):
        self._write("stories/s1/img.png")
        self.assertIsNone(server.resolve_story_image("../s1", "img.png"))
        self.assertIsNone(server.resolve_story_image("stories/../../s1", "img.png"))

    def test_absolute_path_escape_is_rejected(self):
        # A filename that is itself an absolute path must not escape the root
        # even though Path(...) / absolute collapses to the absolute path.
        outside = self.root.parent / "outside.png"
        outside.write_bytes(b"x")
        self.addCleanup(outside.unlink)
        self.assertIsNone(server.resolve_story_image("", str(outside)))

    def test_non_image_extension_is_rejected(self):
        self._write("stories/s1/notes.txt", b"hello")
        self.assertIsNone(server.resolve_story_image("stories/s1", "notes.txt"))

    def test_nonexistent_file_is_rejected(self):
        self.assertIsNone(server.resolve_story_image("stories/s1", "missing.png"))

    def test_empty_subfolder_is_allowed(self):
        self._write("top_level.png")
        result = server.resolve_story_image("", "top_level.png")
        self.assertIsNotNone(result)


class RevealStoryImageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _patch_story_tree(self, Path(self._tmp.name))
        self.root = self.comfy

    def test_missing_file_returns_404_and_never_spawns_a_process(self):
        with patch.object(server.subprocess, "Popen") as popen:
            result, code = server.reveal_story_image("stories/s1", "missing.png")
        self.assertEqual(404, code)
        popen.assert_not_called()

    def test_valid_file_spawns_explorer_with_the_resolved_path(self):
        p = self.root / "stories" / "s1"
        p.mkdir(parents=True)
        (p / "img.png").write_bytes(b"x")
        with patch.object(server, "_IS_WINDOWS", True), \
             patch.object(server.subprocess, "Popen") as popen:
            result, code = server.reveal_story_image("stories/s1", "img.png")
        self.assertEqual(200, code)
        self.assertTrue(result["opened"])
        popen.assert_called_once()
        argv = popen.call_args.args[0]
        self.assertEqual("explorer", argv[0])
        self.assertIn(str((p / "img.png").resolve()), argv)

    def test_non_windows_is_refused_without_spawning(self):
        p = self.root / "img.png"
        p.write_bytes(b"x")
        with patch.object(server, "_IS_WINDOWS", False), \
             patch.object(server.subprocess, "Popen") as popen:
            result, code = server.reveal_story_image("", "img.png")
        self.assertEqual(400, code)
        popen.assert_not_called()

    def test_traversal_attempt_is_refused_without_spawning(self):
        with patch.object(server.subprocess, "Popen") as popen:
            result, code = server.reveal_story_image("../../etc", "passwd.png")
        self.assertEqual(404, code)
        popen.assert_not_called()


class GeneratedMediaAllowListTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name).resolve()
        _patch_story_tree(self, base)
        self.uploads = (base / "uploads").resolve()
        self.chats = (base / "chats").resolve()
        self.equal_shares = (base / "equal_shares").resolve()
        self.uploads.mkdir()
        self.chats.mkdir()
        self.equal_shares.mkdir()
        for attr, value in (("UPLOADS", self.uploads),
                            ("CHATS_ROOT", self.chats),
                            ("EQUAL_SHARES_ROOT", self.equal_shares)):
            p = patch.object(server, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def test_unknown_root_id_is_rejected(self):
        (self.comfy / "ok.png").write_bytes(b"png")
        self.assertIsNone(server.resolve_generated_media("uploads", "", "ok.png"))
        self.assertIsNone(server.resolve_generated_media(str(self.uploads), "", "ok.png"))
        # shared_output is a v2 allow-listed id, but this file is under the
        # story tree, not SHARED_OUTPUT_ROOT.
        self.assertIsNone(server.resolve_generated_media("shared_output", "", "ok.png"))

    def test_uploads_chats_and_equal_shares_are_rejected(self):
        (self.uploads / "evil.png").write_bytes(b"upload-bytes")
        (self.chats / "leak.png").write_bytes(b"chat-bytes")
        (self.equal_shares / "clip.png").write_bytes(b"eq-bytes")
        # Even if the allow-listed *parent* is widened to the temp dir, the
        # forbidden-tree check must still fail closed.
        with patch.object(server, "STORY_OUTPUT_ROOT", Path(self._tmp.name).resolve()):
            self.assertIsNone(server.resolve_generated_media(
                "story_output", "uploads", "evil.png"))
            self.assertIsNone(server.resolve_generated_media(
                "story_output", "chats", "leak.png"))
            self.assertIsNone(server.resolve_generated_media(
                "story_output", "equal_shares", "clip.png"))

    def test_story_output_root_does_not_serve_equal_shares(self):
        (self.equal_shares / "clip.png").write_bytes(b"eq-bytes")
        self.assertIsNone(server.resolve_generated_media(
            "story_output", "", "clip.png"))
        self.assertIsNone(server.resolve_generated_media(
            "story_comfy", "", "clip.png"))

    def test_story_root_rejects_video_suffix(self):
        (self.comfy / "clip.mp4").write_bytes(b"fake-mp4")
        self.assertIsNone(server.resolve_generated_media(
            "story_comfy", "", "clip.mp4", kinds="media"))
        self.assertIsNone(server.resolve_generated_media(
            "story_comfy", "", "clip.mp4", kinds="video"))


class GeneratedMediaHashAndCollectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _patch_story_tree(self, Path(self._tmp.name))

    def _complete_payload(self, filename="img_00001_.png", subfolder="stories/s1/renders",
                          body=b"original-png-bytes") -> tuple[str, Path]:
        dest = self.comfy / Path(subfolder) / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        payload = json.dumps({
            "state": "complete",
            "story": "s1",
            "manifest": {
                "status": "complete",
                "prompt_id": "prompt-abc",
                "outputs": [{"filename": filename, "subfolder": subfolder, "type": "output"}],
            },
        })
        return payload, dest

    def test_collects_complete_story_manifest_and_hashes_bytes(self):
        payload, dest = self._complete_payload()
        arts = server.collect_story_media_artifacts("story_image_job_status", payload)
        self.assertEqual(1, len(arts))
        art = arts[0]
        self.assertEqual("story_comfy", art["root"])
        self.assertEqual("img_00001_.png", art["filename"])
        self.assertEqual("stories/s1/renders", art["subfolder"])
        self.assertEqual(_sha256(b"original-png-bytes"), art["sha256"])
        self.assertEqual(dest.stat().st_size, art["bytes"])
        self.assertEqual("prompt-abc", art["prompt_id"])
        self.assertNotIn("path", art)
        dumped = json.dumps(art)
        self.assertNotIn(str(self.comfy), dumped)
        self.assertNotIn(str(dest), dumped)

    def test_started_render_without_outputs_is_not_collected(self):
        payload = json.dumps({"started": True, "pid": 1, "story": "s1",
                              "manifest_glob": "outputs/stories/s1/manifests/image_*.json"})
        self.assertEqual([], server.collect_story_media_artifacts("render_story_image", payload))

    def test_comfy_generate_enqueue_is_not_collected(self):
        payload = json.dumps({"status": "enqueued", "prompt_id": "8182b9d1",
                              "queue_remaining": 1})
        self.assertEqual([], server.collect_story_media_artifacts("comfy_generate", payload))

    def test_hash_mismatch_returns_409_and_not_the_new_bytes(self):
        payload, dest = self._complete_payload()
        arts = server.collect_story_media_artifacts("story_image_job_status", payload)
        original = arts[0]["sha256"]
        dest.write_bytes(b"regenerated-or-truncated-bytes")
        body, code, ctype = server.generated_media_payload(
            "story_comfy", "stories/s1/renders", "img_00001_.png", original)
        self.assertEqual(409, code)
        self.assertEqual("application/json", ctype)
        self.assertEqual("hash_mismatch", body["status"])
        self.assertNotIn(b"regenerated-or-truncated-bytes", json.dumps(body).encode())

    def test_missing_file_returns_404_json_not_bytes(self):
        body, code, ctype = server.generated_media_payload(
            "story_comfy", "stories/s1/renders", "gone.png", "abc")
        self.assertEqual(404, code)
        self.assertEqual("application/json", ctype)
        self.assertEqual("missing", body["status"])

    def test_matching_hash_serves_bytes(self):
        payload, dest = self._complete_payload(body=b"png-ok")
        arts = server.collect_story_media_artifacts("story_image_job_status", payload)
        body, code, ctype = server.generated_media_payload(
            arts[0]["root"], arts[0]["subfolder"], arts[0]["filename"], arts[0]["sha256"])
        self.assertEqual(200, code)
        self.assertEqual("image/png", ctype)
        self.assertEqual(b"png-ok", body)


def _patch_shared_tree(test, tmp: Path) -> None:
    shared = (tmp / "ComfyUI-Shared").resolve()
    output = (shared / "output").resolve()
    incoming = (shared / "input").resolve()
    output.mkdir(parents=True)
    incoming.mkdir(parents=True)
    test.shared_out = output
    test.shared_in = incoming
    for attr, value in (
        ("SHARED_OUTPUT_ROOT", output),
        ("SHARED_INPUT_ROOT", incoming),
    ):
        p = patch.object(server, attr, value)
        p.start()
        test.addCleanup(p.stop)


class SharedOutputMediaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name).resolve()
        _patch_story_tree(self, base)
        _patch_shared_tree(self, base)
        self.uploads = (base / "uploads").resolve()
        self.chats = (base / "chats").resolve()
        self.equal_shares = (base / "equal_shares").resolve()
        self.uploads.mkdir()
        self.chats.mkdir()
        self.equal_shares.mkdir()
        for attr, value in (("UPLOADS", self.uploads),
                            ("CHATS_ROOT", self.chats),
                            ("EQUAL_SHARES_ROOT", self.equal_shares)):
            p = patch.object(server, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def _complete_job(self, filename="ComfyUI_00214_.png", body=b"mug-png",
                      subfolder="") -> tuple[str, Path]:
        dest = self.shared_out / Path(subfolder) / filename if subfolder else self.shared_out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        payload = json.dumps({
            "state": "complete",
            "prompt_id": "8182b9d1-e080-4d9e-9f85-bc5bccdb4be6",
            "outputs": [{"filename": filename, "subfolder": subfolder, "type": "output"}],
        })
        return payload, dest

    def test_completed_comfy_generate_resolves_to_shared_artifact(self):
        payload, dest = self._complete_job()
        arts = server.collect_comfy_media_artifacts("comfy_job_status", payload)
        self.assertEqual(1, len(arts))
        art = arts[0]
        self.assertEqual("shared_output", art["root"])
        self.assertEqual("image", art["kind"])
        self.assertEqual("ready", art["status"])
        self.assertEqual("ComfyUI_00214_.png", art["filename"])
        self.assertEqual(_sha256(b"mug-png"), art["sha256"])
        self.assertEqual(dest.stat().st_size, art["bytes"])
        self.assertNotIn("path", art)
        dumped = json.dumps(art)
        self.assertNotIn(str(self.shared_out), dumped)
        body, code, ctype = server.generated_media_payload(
            art["root"], art["subfolder"], art["filename"], art["sha256"])
        self.assertEqual(200, code)
        self.assertEqual("image/png", ctype)
        self.assertEqual(b"mug-png", body)

    def test_still_running_job_is_pending_not_a_broken_card(self):
        payload = json.dumps({
            "state": "pending",
            "prompt_id": "8182b9d1-e080-4d9e-9f85-bc5bccdb4be6",
            "timeout": True,
            "timeout_s": 90,
            "note": "still running after 90s bounded poll; call comfy_job_status again",
            "outputs": [],
        })
        arts = server.collect_comfy_media_artifacts("comfy_job_status", payload)
        self.assertEqual(1, len(arts))
        art = arts[0]
        self.assertEqual("pending", art["status"])
        self.assertEqual("", art["filename"])
        self.assertEqual("", art["sha256"])
        # No filename → GET would 404; the GUI must not fetch.
        body, code, _ctype = server.generated_media_payload(
            art["root"], art["subfolder"], art["filename"] or "missing.png")
        self.assertEqual(404, code)
        self.assertEqual("missing", body["status"])

    def test_comfy_generate_enqueue_still_not_collected(self):
        payload = json.dumps({"status": "enqueued", "prompt_id": "8182b9d1",
                              "queue_remaining": 1})
        self.assertEqual([], server.collect_comfy_media_artifacts("comfy_generate", payload))
        self.assertEqual([], server.collect_story_media_artifacts("comfy_generate", payload))
        self.assertEqual([], server.collect_media_artifacts("comfy_generate", payload))

    def test_video_on_shared_output_resolves_and_hash_mismatch_is_409(self):
        dest = self.shared_out / "clip_00001_.mp4"
        dest.write_bytes(b"fake-mp4-bytes")
        payload = json.dumps({
            "state": "complete",
            "prompt_id": "vid-prompt-1",
            "outputs": [{"filename": "clip_00001_.mp4", "subfolder": "", "type": "output",
                         "media_key": "gifs"}],
        })
        arts = server.collect_comfy_media_artifacts("comfy_job_status", payload)
        self.assertEqual(1, len(arts))
        self.assertEqual("video", arts[0]["kind"])
        self.assertEqual("ready", arts[0]["status"])
        original = arts[0]["sha256"]
        body, code, ctype = server.generated_media_payload(
            "shared_output", "", "clip_00001_.mp4", original)
        self.assertEqual(200, code)
        self.assertEqual("video/mp4", ctype)
        self.assertEqual(b"fake-mp4-bytes", body)
        dest.write_bytes(b"replaced-mp4-bytes")
        body, code, ctype = server.generated_media_payload(
            "shared_output", "", "clip_00001_.mp4", original)
        self.assertEqual(409, code)
        self.assertEqual("application/json", ctype)
        self.assertEqual("hash_mismatch", body["status"])
        self.assertNotIn(b"replaced-mp4-bytes", json.dumps(body).encode())

    def test_shared_output_rejects_uploads_chats_equal_shares_and_input(self):
        (self.uploads / "evil.mp4").write_bytes(b"upload")
        (self.chats / "leak.mp4").write_bytes(b"chat")
        (self.equal_shares / "clip.mp4").write_bytes(b"eq")
        (self.shared_in / "ref.png").write_bytes(b"input-ref")
        self.assertIsNone(server.resolve_generated_media(
            "shared_output", "", "evil.mp4", kinds="media"))
        self.assertIsNone(server.resolve_generated_media(
            "shared_output", "", "clip.mp4", kinds="media"))
        self.assertIsNone(server.resolve_generated_media(
            "shared_output", "", "ref.png", kinds="media"))
        with patch.object(server, "SHARED_OUTPUT_ROOT", Path(self._tmp.name).resolve()):
            self.assertIsNone(server.resolve_generated_media(
                "shared_output", "uploads", "evil.mp4", kinds="media"))
            self.assertIsNone(server.resolve_generated_media(
                "shared_output", "chats", "leak.mp4", kinds="media"))
            self.assertIsNone(server.resolve_generated_media(
                "shared_output", "equal_shares", "clip.mp4", kinds="media"))
            self.assertIsNone(server.resolve_generated_media(
                "shared_output", "input", "ref.png", kinds="media"))

    def test_error_job_is_not_collected_as_a_card(self):
        payload = json.dumps({
            "state": "error", "prompt_id": "bad-id", "status_str": "error",
            "outputs": [],
        })
        self.assertEqual([], server.collect_comfy_media_artifacts("comfy_job_status", payload))

    def test_refresh_restores_video_locator_and_truncate_drops_it(self):
        dest = self.shared_out / "clip_00001_.mp4"
        dest.write_bytes(b"vid-bytes")
        payload = json.dumps({
            "state": "complete",
            "prompt_id": "vid-1",
            "outputs": [{"filename": "clip_00001_.mp4", "subfolder": "", "type": "output"}],
        })
        arts = server.collect_comfy_media_artifacts("comfy_job_status", payload)
        chats = Path(self._tmp.name) / "chats"
        chats.mkdir(exist_ok=True)
        with patch.object(store, "DIR", chats):
            conv = store.create("make a clip", model="test-model")
            store.append(conv["id"], "user", "make a clip")
            store.append(conv["id"], "assistant", "here is the clip",
                         meta={"media_artifacts": arts})
            loaded = store.load(conv["id"])
            art = loaded["messages"][-1]["media_artifacts"][0]
            self.assertEqual("video", art["kind"])
            self.assertEqual("shared_output", art["root"])
            self.assertNotIn("path", art)
            store.truncate_after(conv["id"], 0)
            after = store.load(conv["id"])
            self.assertFalse(any("media_artifacts" in m for m in after["messages"]))


class GeneratedMediaPersistRestoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        _patch_story_tree(self, Path(self._tmp.name))
        self.chats = Path(self._tmp.name) / "chats"
        self.chats.mkdir()
        self._store_dir = patch.object(store, "DIR", self.chats)
        self._store_dir.start()
        self.addCleanup(self._store_dir.stop)

    def test_refresh_restores_locator_without_rerender_and_truncate_drops_it(self):
        dest = self.comfy / "stories" / "s1" / "renders" / "img.png"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"still-png")
        payload = json.dumps({
            "state": "complete",
            "story": "s1",
            "manifest": {
                "status": "complete",
                "prompt_id": "p1",
                "outputs": [{"filename": "img.png", "subfolder": "stories/s1/renders",
                             "type": "output"}],
            },
        })
        arts = server.collect_story_media_artifacts("story_image_job_status", payload)
        self.assertEqual(1, len(arts))
        conv = store.create("show me the still", model="test-model")
        store.append(conv["id"], "user", "show me the still")
        store.append(conv["id"], "assistant", "here is the image",
                     meta={"media_artifacts": arts})
        loaded = store.load(conv["id"])
        self.assertEqual(1, len(loaded["messages"][-1]["media_artifacts"]))
        self.assertEqual(arts[0]["sha256"], loaded["messages"][-1]["media_artifacts"][0]["sha256"])
        self.assertNotIn("path", loaded["messages"][-1]["media_artifacts"][0])
        # Regenerating truncates after the user turn; the locator goes with
        # the assistant message. Nothing re-runs a render.
        store.truncate_after(conv["id"], 0)
        after = store.load(conv["id"])
        self.assertEqual(1, len(after["messages"]))
        self.assertEqual("user", after["messages"][0]["role"])
        self.assertFalse(any("media_artifacts" in m for m in after["messages"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
