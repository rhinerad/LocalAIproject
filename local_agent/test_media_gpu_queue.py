#!/usr/bin/env python3
"""Regression tests for media_queue state machine and vision/transcribe queue gates."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import media_queue as mq
import media_tools


class QueueStateTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir) / "q"
        self._patcher = patch.object(mq, "QUEUE_ROOT", self._root)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_enqueue_creates_pending_job(self):
        job = mq.enqueue("vision", {"images": ["a.png"], "question": "what?"})
        self.assertEqual("vision", job["kind"])
        self.assertIn("id", job)
        self.assertIn("queued_at", job)
        self.assertEqual("batch", job["priority"])
        self.assertEqual(1, len(list((self._root / "pending").glob("*.json"))))

    def test_claim_moves_to_processing(self):
        job = mq.enqueue("vision", {"question": "q"})
        claimed = mq.claim_next()
        self.assertIsNotNone(claimed)
        self.assertEqual(job["id"], claimed["id"])
        self.assertFalse((self._root / "pending" / f"{job['id']}.json").is_file())
        self.assertTrue((self._root / "processing" / f"{job['id']}.json").is_file())

    def test_complete_moves_to_done(self):
        job = mq.enqueue("vision", {})
        mq.claim_next()
        mq.complete(job["id"], '{"analysis": "done"}')
        self.assertFalse((self._root / "processing" / f"{job['id']}.json").is_file())
        done_file = self._root / "done" / f"{job['id']}.json"
        self.assertTrue(done_file.is_file())
        data = json.loads(done_file.read_text(encoding="utf-8"))
        self.assertEqual('{"analysis": "done"}', data["result"])
        self.assertIn("done_at", data)

    def test_fail_moves_to_failed(self):
        job = mq.enqueue("transcribe", {"path": "/x.wav"})
        mq.claim_next()
        mq.fail(job["id"], "GPU OOM")
        self.assertFalse((self._root / "processing" / f"{job['id']}.json").is_file())
        failed_file = self._root / "failed" / f"{job['id']}.json"
        self.assertTrue(failed_file.is_file())
        data = json.loads(failed_file.read_text(encoding="utf-8"))
        self.assertEqual("GPU OOM", data["error"])
        self.assertIn("failed_at", data)

    def test_claim_next_empty_returns_none(self):
        self.assertIsNone(mq.claim_next())

    def test_claim_next_kind_filter_leaves_other_kinds_pending(self):
        v_job = mq.enqueue("vision", {})
        t_job = mq.enqueue("transcribe", {})
        claimed = mq.claim_next(kind="transcribe")
        self.assertIsNotNone(claimed)
        self.assertEqual(t_job["id"], claimed["id"])
        # vision job must still be pending
        self.assertTrue((self._root / "pending" / f"{v_job['id']}.json").is_file())

    def test_recover_stale_restores_processing_to_pending(self):
        job = mq.enqueue("vision", {})
        mq.claim_next()
        self.assertTrue((self._root / "processing" / f"{job['id']}.json").is_file())
        n = mq.recover_stale()
        self.assertEqual(1, n)
        self.assertTrue((self._root / "pending" / f"{job['id']}.json").is_file())
        self.assertFalse((self._root / "processing" / f"{job['id']}.json").is_file())

    def test_recover_stale_returns_zero_when_nothing_stale(self):
        mq.enqueue("vision", {})
        self.assertEqual(0, mq.recover_stale())

    def test_clear_pending_preserves_cancelled_records_and_leaves_work_running(self):
        pending = mq.enqueue("vision", {"path": "a.png"})
        active = mq.enqueue("transcribe", {"path": "b.wav"})
        mq.claim_next(kind="transcribe")

        self.assertEqual(1, mq.clear_pending())
        self.assertFalse((self._root / "pending" / f"{pending['id']}.json").exists())
        cancelled = self._root / "cancelled" / f"{pending['id']}.json"
        self.assertTrue(cancelled.is_file())
        record = json.loads(cancelled.read_text(encoding="utf-8"))
        self.assertEqual({"path": "a.png"}, record["args"])
        self.assertEqual("operator cleared media queue", record["cancel_reason"])
        self.assertIn("cancelled_at", record)
        self.assertTrue((self._root / "processing" / f"{active['id']}.json").is_file())

    def test_enqueue_coalesces_identical_pending_work(self):
        first = mq.enqueue("transcribe", {"path": "same.wav"})
        second = mq.enqueue("transcribe", {"path": "same.wav"})
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(1, len(list((self._root / "pending").glob("*.json"))))

    def test_interactive_priority_is_fifo_and_precedes_batch(self):
        first_batch = mq.enqueue("vision", {"path": "batch-one"})
        first_live = mq.enqueue("transcribe", {"path": "live-one"}, priority="interactive")
        second_live = mq.enqueue("vision", {"path": "live-two"}, priority="interactive")
        second_batch = mq.enqueue("transcribe", {"path": "batch-two"})
        claimed = [mq.claim_next()["id"] for _ in range(4)]
        self.assertEqual([first_live["id"], second_live["id"],
                          first_batch["id"], second_batch["id"]], claimed)

    def test_live_duplicate_promotes_pending_batch(self):
        batch = mq.enqueue("vision", {"path": "same.png"})
        promoted = mq.enqueue("vision", {"path": "same.png"}, priority="interactive")
        self.assertEqual(batch["id"], promoted["id"])
        self.assertEqual("interactive", promoted["priority"])

    def test_invalid_priority_is_refused(self):
        with self.assertRaises(ValueError):
            mq.enqueue("vision", {}, priority="urgent")

    def test_cancel_pending_preserves_a_cancelled_record(self):
        job = mq.enqueue("vision", {"path": "cancel.png"})
        result = mq.cancel(job["id"])
        self.assertTrue(result["ok"])
        self.assertEqual("cancelled", result["state"])
        self.assertFalse((self._root / "pending" / f"{job['id']}.json").exists())
        saved = json.loads((self._root / "cancelled" / f"{job['id']}.json").read_text())
        self.assertEqual("operator cancelled", saved["cancel_reason"])

    def test_cancel_processing_sets_a_cooperative_flag(self):
        job = mq.enqueue("vision", {"path": "run.png"})
        mq.claim_next()
        result = mq.cancel(job["id"])
        self.assertTrue(result["ok"])
        self.assertEqual("cancelling", result["state"])
        self.assertTrue(mq.cancel_requested(job["id"]))
        self.assertTrue(mq.finish_cancel(job["id"]))
        self.assertTrue((self._root / "cancelled" / f"{job['id']}.json").exists())

    def test_cancel_unknown_and_completed_are_clean_noops(self):
        self.assertFalse(mq.cancel("not-a-job")["ok"])
        job = mq.enqueue("vision", {})
        mq.claim_next(); mq.complete(job["id"], "done")
        result = mq.cancel(job["id"])
        self.assertFalse(result["ok"])
        self.assertEqual("done", result["state"])

    def test_enriched_pending_listing_has_elapsed_progress_and_wait_reason(self):
        mq.enqueue("vision", {"path": "queued.png"}, priority="interactive")
        with patch.object(mq.router, "queue_owner", return_value=(True, "render")), \
             patch.object(mq.router, "comfy_listening", return_value=False), \
             patch.object(mq.router, "gpu_free_mb", return_value=12000):
            row = mq.list_queue()["pending"][0]
        self.assertEqual("queued.png", row["name"])
        self.assertIn("elapsed_seconds", row)
        self.assertIn("progress", row)
        self.assertIn("render is using it", row["waiting_reason"])

    def test_cancel_endpoint_helper_only_targets_media_queue_jobs(self):
        import server
        job = mq.enqueue("vision", {"path": "endpoint.png"})
        result, status = server.cancel_media_queue_job(job["id"])
        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        missing, missing_status = server.cancel_media_queue_job("not-a-job")
        self.assertEqual(404, missing_status)
        self.assertFalse(missing["ok"])
        empty, empty_status = server.cancel_media_queue_job("")
        self.assertEqual(400, empty_status)
        self.assertFalse(empty["ok"])

    def test_list_queue_counts_by_state(self):
        mq.enqueue("vision", {"path": "one.png"})
        mq.enqueue("transcribe", {"path": "two.wav"})
        mq.enqueue("vision", {"path": "three.png"})
        claimed = mq.claim_next()  # whichever is oldest
        self.assertIsNotNone(claimed)
        mq.complete(claimed["id"], "result")
        listing = mq.list_queue()
        self.assertEqual(2, len(listing["pending"]))
        self.assertEqual(0, len(listing["processing"]))
        self.assertEqual(1, len(listing["done"]))
        self.assertEqual(0, len(listing["failed"]))
        self.assertEqual(0, len(listing["cancelled"]))

    def test_each_listing_entry_has_required_keys(self):
        mq.enqueue("vision", {})
        listing = mq.list_queue()
        for entry in listing["pending"]:
            self.assertIn("id", entry)
            self.assertIn("kind", entry)
            self.assertIn("queued_at", entry)


class VisionQueueGateTests(unittest.TestCase):
    """Verify _vision() enqueues when VRAM is below every tier threshold."""

    def test_vision_queues_when_gpu_free_mb_is_zero(self):
        import types
        fake_tier = [{"label": "primary", "model": "qwen3-vl-abliterated:8b-q8_0",
                      "vram_need_mb": 11500, "task_strengths": "OCR"}]
        captured: list[dict] = []
        mock_mq = types.SimpleNamespace(
            enqueue=lambda kind, args, **kwargs: captured.append({"kind": kind, "args": args, **kwargs})
            or {"id": "q-test-001", "kind": kind})

        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")

        with patch.dict(sys.modules, {"media_queue": mock_mq}), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=0), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier):
            result = json.loads(media_tools.see_image({"path": str(sample), "question": "test"}))

        self.assertTrue(result["queued"])
        self.assertEqual("q-test-001", result["job_id"])
        self.assertEqual(1, len(captured))
        self.assertEqual("vision", captured[0]["kind"])

    def test_vision_queues_when_nvidia_smi_unavailable(self):
        import types
        fake_tier = [{"label": "primary", "model": "qwen3-vl-abliterated:8b-q8_0",
                      "vram_need_mb": 11500, "task_strengths": "OCR"}]
        mock_mq = types.SimpleNamespace(
            enqueue=lambda kind, args, **kwargs: {"id": "q-nosmi-001", "kind": kind})

        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")

        with patch.dict(sys.modules, {"media_queue": mock_mq}), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=None), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier):
            result = json.loads(media_tools.see_image({"path": str(sample), "question": "test"}))

        self.assertTrue(result["queued"])

    def test_vision_queues_even_when_vram_is_sufficient(self):
        fake_tier = [{"label": "primary", "model": "qwen3-vl-abliterated:8b-q8_0",
                      "vram_need_mb": 11500, "task_strengths": "OCR"}]
        import types
        captured: list[dict] = []
        mock_mq = types.SimpleNamespace(
            enqueue=lambda kind, args, **kwargs: captured.append({"kind": kind, "args": args, **kwargs})
            or {"id": "q-safe-window", "kind": kind})

        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")

        with patch.dict(sys.modules, {"media_queue": mock_mq}), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=14000), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier):
            result = json.loads(media_tools.see_image({"path": str(sample), "question": "test"}))

        self.assertTrue(result["queued"])
        self.assertEqual("q-safe-window", result["job_id"])
        self.assertEqual("vision", captured[0]["kind"])


class TranscribeQueueGateTests(unittest.TestCase):
    """Verify transcribe() enqueues when a render holds the GPU."""

    def test_transcribe_queues_when_render_active(self):
        import types
        mock_mq = types.SimpleNamespace(
            enqueue=lambda kind, args, **kwargs: {"id": "q-t-001", "kind": kind})

        sample = ROOT / "outputs/equal_shares/audio/_hybrid_parts/00C.wav"
        if not sample.is_file():
            self.skipTest(f"missing project sample {sample}")

        with patch.dict(sys.modules, {"media_queue": mock_mq}), \
             patch.object(media_tools.router, "queue_owner",
                          return_value=(True, "render queue claimed")), \
             patch.object(media_tools.router, "comfy_listening", return_value=False), \
             patch.object(media_tools.caps, "capability",
                          return_value={"available": True, "engine": "comfy_whisper_tiny",
                                        "model": "/some/model"}):
            result = json.loads(media_tools.transcribe({"path": str(sample)}))

        self.assertTrue(result["queued"])
        self.assertEqual("q-t-001", result["job_id"])

    def test_transcribe_does_not_queue_when_gpu_free(self):
        sample = ROOT / "outputs/equal_shares/audio/_hybrid_parts/00C.wav"
        if not sample.is_file():
            self.skipTest(f"missing project sample {sample}")

        fake_result = json.dumps({"available": True, "transcript": "hello world test"})
        with patch.object(media_tools.router, "queue_owner", return_value=(False, "released")), \
             patch.object(media_tools.router, "comfy_listening", return_value=False), \
             patch.object(media_tools.caps, "capability", return_value={"available": True}), \
             patch.object(media_tools, "_do_transcribe", return_value=fake_result):
            result = json.loads(media_tools.transcribe({"path": str(sample)}))

        self.assertFalse(result.get("queued", False))
        self.assertIn("transcript", result)

    def test_transcribe_does_not_queue_for_resident_vision_runtime(self):
        sample = ROOT / "outputs/equal_shares/audio/_hybrid_parts/00C.wav"
        if not sample.is_file():
            self.skipTest(f"missing project sample {sample}")

        fake_result = json.dumps({"available": True, "transcript": "hello world test"})
        with patch.object(media_tools.router, "queue_owner", return_value=(False, "released")), \
             patch.object(media_tools.router, "comfy_listening", return_value=False), \
             patch.object(media_tools.caps, "capability", return_value={"available": True}), \
             patch.object(media_tools, "_do_transcribe", return_value=fake_result):
            result = json.loads(media_tools.transcribe({"path": str(sample)}))

        self.assertFalse(result.get("queued", False))
        self.assertIn("transcript", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
