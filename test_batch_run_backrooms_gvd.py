#!/usr/bin/env python3
"""Offline unit tests for batch_run_backrooms_gvd.gate_before_video_submit.

Fix 2026-09-23 (readiness-audit finding 1.1): batch_run_backrooms_gvd.py
previously had zero QA/approval code anywhere in the file before submitting
video jobs. These tests lock in the fail-closed gate added in front of
gv.submit_comfy() so a future edit can't silently reopen that gap.

No ComfyUI, no GPU, no live Ollama/VLM connection, no network.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "local_agent") not in sys.path:
    sys.path.insert(0, str(ROOT / "local_agent"))

import batch_run_backrooms_gvd as batch  # noqa: E402


def _fake_gv(*, listening: bool) -> types.SimpleNamespace:
    return types.SimpleNamespace(caption_v4_listening=lambda: listening)


class GateBeforeVideoSubmitTests(unittest.TestCase):
    def _args(self, **overrides):
        ns = types.SimpleNamespace(
            skip_visual_qa=False,
            allow_ungated_i2v=False,
            require_qa_receipt=True,
            qa_receipt=None,
            qa_candidate=None,
            qa_job_dir=None,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def _patched_gate(self, return_value=(None, None)):
        """Patch the file-loaded apply_qa_gate without touching real sys.path/import
        resolution (see _load_apply_qa_gate's docstring for why that's fragile here)."""
        fake_apply_qa_gate = MagicMock(return_value=return_value)
        return patch.object(batch, "_load_apply_qa_gate", return_value=fake_apply_qa_gate), fake_apply_qa_gate

    def test_refuses_when_vlm_down_and_no_explicit_override(self):
        """VLM offline + no operator override must block, not silently continue."""
        args = self._args()
        gv = _fake_gv(listening=False)
        patcher, fake_gate = self._patched_gate()
        with patcher:
            with self.assertRaises(RuntimeError):
                batch.gate_before_video_submit(
                    args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
                )
            fake_gate.assert_not_called()

    def test_allow_ungated_i2v_explicit_override_proceeds(self):
        """Explicit --allow-ungated-i2v is the only thing that may bypass an offline VLM."""
        args = self._args(allow_ungated_i2v=True)
        gv = _fake_gv(listening=False)
        patcher, fake_gate = self._patched_gate(return_value=(None, None))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()
        self.assertTrue(args.skip_visual_qa)

    def test_explicit_skip_visual_qa_still_goes_through_the_gate(self):
        args = self._args(skip_visual_qa=True)
        gv = _fake_gv(listening=True)
        patcher, fake_gate = self._patched_gate(return_value=(None, None))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()

    def test_gate_block_code_raises(self):
        """apply_qa_gate returning a non-None exit code must block the clip."""
        args = self._args(skip_visual_qa=True)
        gv = _fake_gv(listening=True)
        patcher, _fake_gate = self._patched_gate(return_value=(4, None))
        with patcher:
            with self.assertRaises(RuntimeError):
                batch.gate_before_video_submit(
                    args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
                )

    def test_vlm_up_no_flags_defers_to_receipt_gate(self):
        """VLM reachable and no skip flag: still routes through apply_qa_gate (receipt-based)."""
        args = self._args()
        gv = _fake_gv(listening=True)
        patcher, fake_gate = self._patched_gate(return_value=(None, "accepted.png"))
        with patcher:
            batch.gate_before_video_submit(
                args, gv, "C001", root=batch.ROOT, local_agent=batch.LOCAL_AGENT
            )
            fake_gate.assert_called_once()
        self.assertFalse(args.skip_visual_qa)

    def test_load_apply_qa_gate_resolves_the_real_function(self):
        """End-to-end (no mocking): the file-based loader must actually resolve
        gvd_qa/i2v_gate.py's real apply_qa_gate, proving the fix for the
        `import gvd_qa` name collision (ROOT's gvd_qa.py vs. the gvd_qa/
        package under local_agent/) actually works in this process."""
        fn = batch._load_apply_qa_gate(batch.LOCAL_AGENT)
        self.assertTrue(callable(fn))
        self.assertEqual(fn.__name__, "apply_qa_gate")
        # And a real call, with no receipt/candidate and no explicit skip,
        # must fail closed (matches i2v_gate.py's own documented default).
        args = self._args()
        code, still = fn(args, root=batch.ROOT, local_agent=batch.LOCAL_AGENT)
        self.assertEqual(code, 4)
        self.assertIsNone(still)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Audit 2026-11-02 fixes: shared finished-clip vocabulary, evidence-preserving
# progress entries, atomic writes, codemod residue, timeouts, fail-closed VRAM.
# ---------------------------------------------------------------------------
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402


class _TmpVideo(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.video = self.tmp / "clip.mp4"
        self.video.write_bytes(b"\0" * 20_000)

    def tearDown(self):
        self._td.cleanup()


class AlreadyDoneVocabularyTests(_TmpVideo):
    def test_selected_and_legacy_done_count_as_done(self):
        v = str(self.video)
        for entry in (
            {"status": "selected", "pipeline_state": "SELECTED", "video_path": v},
            {"status": "selected", "video_path": v},
            {"status": "qa_passed", "video_path": v},
            {"status": "done", "video_path": v},
            {"status": "ok", "video_path": v},
            {"status": "success", "video_path": v},
            {"ok": True, "video_path": v},
            {"status": "rendered", "pipeline_state": "SELECTED", "video_path": v},
        ):
            with self.subTest(entry=entry):
                self.assertTrue(batch.already_done(entry))

    def test_not_done(self):
        v = str(self.video)
        for entry in (
            None, {}, "x",
            {"status": "running", "video_path": v},
            {"status": "error", "video_path": v, "pipeline_state": "SELECTED"},
            {"status": "qa_failed", "video_path": v},
            {"status": "rendered", "video_path": v},
            {"status": "qa_pending", "video_path": v},
            {"status": "selected", "video_path": str(self.tmp / "gone.mp4")},
            {"status": "done"},
        ):
            with self.subTest(entry=entry):
                self.assertFalse(batch.already_done(entry))

    def test_legacy_done_is_not_a_chain_source(self):
        legacy = {"status": "done", "video_path": str(self.video)}
        self.assertTrue(batch.already_done(legacy))
        self.assertFalse(batch.is_selected(legacy))
        self.assertTrue(batch.is_selected({"status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video)}))

    def test_is_failed(self):
        self.assertTrue(batch.is_failed({"status": "error"}))
        self.assertTrue(batch.is_failed({"status": "qa_failed"}))
        self.assertTrue(batch.is_failed({"status": "x", "pipeline_state": "QA_FAILED"}))
        self.assertFalse(batch.is_failed({"status": "selected"}))
        self.assertFalse(batch.is_failed(None))


class EvidencePreservationTests(_TmpVideo):
    def _selected(self):
        return {
            "status": "selected", "pipeline_state": "SELECTED", "video_path": str(self.video),
            "at": "t1", "elapsed_sec": 10.0, "verified": True,
            "vlm_qa": {"pass": True, "text_video_alignment": 0.9, "dump": "d1.json"},
            "continuity": {"mode_used": "fresh"},
        }

    def test_begin_attempt_keeps_prior_evidence_and_records_it(self):
        entry = batch.begin_attempt(self._selected(), at="t2", continuity={"mode_used": "chained"})
        self.assertEqual(entry["status"], "running")
        self.assertEqual(entry["video_path"], str(self.video))
        self.assertEqual(entry["vlm_qa"]["dump"], "d1.json")
        self.assertEqual(entry["continuity"], {"mode_used": "chained"})
        self.assertEqual(len(entry["attempts"]), 1)
        self.assertEqual(entry["attempts"][0]["status"], "selected")
        self.assertEqual(entry["attempts"][0]["video_path"], str(self.video))
        self.assertEqual(entry["attempts"][0]["vlm_qa"]["dump"], "d1.json")

    def test_error_never_drops_video_path_or_vlm_qa(self):
        entry = batch.begin_attempt(self._selected(), at="t2", continuity=None)
        entry = batch.fail_entry(entry, "RuntimeError: comfy fell over", at="t3", continuity=None)
        self.assertEqual(entry["status"], "error")
        self.assertEqual(entry["error"], "RuntimeError: comfy fell over")
        self.assertEqual(entry["video_path"], str(self.video))
        self.assertEqual(entry["vlm_qa"]["pass"], True)
        self.assertEqual([a["status"] for a in entry["attempts"]], ["selected", "error"])
        self.assertEqual(entry["attempts"][-1]["error"], "RuntimeError: comfy fell over")
        self.assertEqual(set(batch.ATTEMPT_FIELDS) <= set(entry["attempts"][-1]), True)

    def test_new_render_supersedes_but_remembers_previous_video(self):
        new_video = self.tmp / "new.mp4"
        entry = batch.begin_attempt(self._selected(), at="t2", continuity=None)
        entry = batch.finish_render(entry, status="rendered", video_path=str(new_video), at="t3", elapsed_sec=12.0)
        self.assertEqual(entry["video_path"], str(new_video))
        self.assertEqual(entry["previous_video_path"], str(self.video))
        self.assertNotIn("vlm_qa", entry, "old QA judged the old video; it lives in attempts[]")
        self.assertTrue(any(a.get("vlm_qa") for a in entry["attempts"]))

    def test_record_attempt_dedupes_and_is_uncapped(self):
        entry = {"status": "error", "error": "e", "at": "t"}
        batch.record_attempt(entry)
        batch.record_attempt(entry)
        self.assertEqual(len(entry["attempts"]), 1)
        for i in range(10):
            entry["at"] = f"t{i}"
            batch.record_attempt(entry)
        self.assertEqual(len(entry["attempts"]), 11)

    def test_main_loop_error_merges_into_existing_entry(self):
        """End to end through main(): an error on rerun keeps the old video_path."""
        import types as _types

        prior = self._selected()
        prog_path = self.tmp / "progress.json"
        prog_path.write_text(json.dumps({"pack": "p", "created": "t", "clips": {"C001": prior}}), encoding="utf-8")
        clips = [{"id": "C001", "start_frame": "s", "video_prompt": "v", "camera_mode": "A"}]

        def boom(pred, hparams, **kw):
            raise RuntimeError("comfy fell over")

        fake_gv = _types.SimpleNamespace(submit_comfy=boom, DEFAULT_COMFY="http://fake:8188",
                                         caption_v4_listening=lambda: True)
        fake_dv = _types.SimpleNamespace(extract_dialogue_array=lambda s: [], dialogue_to_speech_text=lambda l: "",
                                         extract_raw_dialogue=lambda s: "", is_c001=lambda c: False)
        fake_rules = _types.SimpleNamespace(write_rules_lock=lambda pack: self.tmp / "lock.json",
                                            apply_immutable_rules=lambda m: m)
        with patch.dict(sys.modules, {"generate_video": fake_gv, "dynamic_voice": fake_dv,
                                      "gvd_pipeline_rules": fake_rules}), \
                patch.object(batch, "PROGRESS_DIR", self.tmp), patch.object(batch, "PROGRESS_PATH", prog_path), \
                patch.object(batch, "load_clip_override", return_value={}), \
                patch.object(batch, "gate_before_video_submit", return_value=None), \
                patch.object(batch, "_wants_ref2vid", return_value=False), \
                patch.object(batch, "ingest_pack", return_value=clips):
            rc = batch.main(["--sleep", "0", "--force"])
        self.assertEqual(rc, 1)
        entry = json.loads(prog_path.read_text(encoding="utf-8"))["clips"]["C001"]
        self.assertEqual(entry["status"], "error")
        self.assertEqual(entry["video_path"], str(self.video), "prior evidence survived the error")
        self.assertEqual(entry["vlm_qa"]["dump"], "d1.json")
        self.assertEqual([a["status"] for a in entry["attempts"]], ["selected", "error"])
        self.assertFalse(list(self.tmp.glob("progress.json.tmp*")), "atomic write leaves no temp file")


class VlmDumpTests(_TmpVideo):
    def test_dump_is_timestamped_with_latest_pointer(self):
        with patch.object(batch, "PROGRESS_DIR", self.tmp):
            d1, latest = batch.vlm_qa_dump_paths("C001", stamp="20260101T000000")
            d2, latest2 = batch.vlm_qa_dump_paths("C001", stamp="20260101T000001")
        self.assertNotEqual(d1, d2)
        self.assertEqual(latest, latest2)
        self.assertEqual(d1.name, "vlm_qa_C001_20260101T000000.json")
        self.assertEqual(latest.name, "vlm_qa_C001_latest.json")


class AtomicProgressTests(_TmpVideo):
    def test_save_progress_uses_shared_atomic_writer(self):
        from local_agent import atomic_io

        self.assertIs(batch.atomic_write_json, atomic_io.atomic_write_json)
        prog_path = self.tmp / "progress.json"
        with patch.object(batch, "PROGRESS_DIR", self.tmp), patch.object(batch, "PROGRESS_PATH", prog_path):
            batch.save_progress({"clips": {}})
        self.assertIn("updated", json.loads(prog_path.read_text(encoding="utf-8")))
        self.assertFalse(list(self.tmp.glob("*.tmp*")))

    def test_backrooms_compile_imports_local_agent_atomic_io(self):
        from local_agent import atomic_io
        import backrooms_compile

        self.assertIs(backrooms_compile.atomic_write_json, atomic_io.atomic_write_json)


class CodemodResidueTests(unittest.TestCase):
    def test_wants_literal_and_override_negatives(self):
        self.assertTrue(batch.wants_literal({"literal_prompt": True}))
        self.assertTrue(batch.wants_literal({"bypass_director": True}))
        self.assertFalse(batch.wants_literal({}))
        clip = {"id": "C001", "start_frame": "S", "video_prompt": "V", "start_frame_negative": "NEG"}
        pred, hp = batch.pred_from_override({"literal_prompt": True, "negative_prompt": ""}, clip)
        self.assertEqual(pred.negative_prompt, "", "explicit empty negative must not fall through")
        pred, _ = batch.pred_from_override({"literal_prompt": True, "negative_prompt": "no cables"}, clip)
        self.assertEqual(pred.negative_prompt, "no cables")
        pred, _ = batch.pred_from_override({"start_prompt": "X", "video_prompt": "Y"}, clip)
        self.assertEqual((pred.start_prompt, pred.video_prompt, pred.negative_prompt), ("X", "Y", "NEG"))
        self.assertFalse(pred.literal_prompt)

    def test_generate_video_aliases_and_print_plan(self):
        import generate_video as gv

        self.assertEqual(set(gv.CATEGORY_ALIASES), set(gv.CATEGORIES))
        self.assertEqual(gv.resolve_category("Backrooms"), "backrooms")
        src = (ROOT / "generate_video.py").read_text(encoding="utf-8")
        self.assertNotIn("\\n    if bool(getattr(pred", src, "patched-into-comment residue removed")
        self.assertEqual(src.count('or getattr(pred, "bypass_director", False)'), 0)
        with patch("builtins.print"):
            gv.print_plan(types.SimpleNamespace(start_prompt="a", video_prompt="b", negative_prompt=""), {})


class SubprocessTimeoutTests(unittest.TestCase):
    def test_build_long_distinct_master_passes_timeouts(self):
        import build_long_distinct_master as bl

        with patch.object(bl.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, stdout="8.0\n", stderr="")) as run:
            self.assertEqual(bl.duration_s(Path("x.mp4")), 8.0)
        self.assertEqual(run.call_args.kwargs["timeout"], bl.FFPROBE_TIMEOUT_S)
        self.assertGreater(bl.FFMPEG_TIMEOUT_S, 0)
        src = (ROOT / "build_long_distinct_master.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("timeout="), 2)

    def test_auto_boot_live_test_has_timeout(self):
        import auto_boot_and_test as ab

        with patch.object(ab.subprocess, "call", return_value=0) as call:
            self.assertEqual(ab.run_live_test(), 0)
        self.assertEqual(call.call_args.kwargs["timeout"], ab.LIVE_TEST_TIMEOUT_S)
        with patch.object(ab.subprocess, "call", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            self.assertEqual(ab.run_live_test(), 124)


class VramHeadroomFailClosedTests(unittest.TestCase):
    def test_probe_failure_raises_instead_of_returning_free(self):
        from local_agent import vram_controller as vc

        with patch.object(subprocess, "check_output", side_effect=FileNotFoundError("nvidia-smi")):
            with self.assertRaises(vc.VramProbeError):
                vc.wait_for_vram_headroom(timeout=1.0)
        with patch.object(subprocess, "check_output", return_value="garbage\n"):
            with self.assertRaises(vc.VramProbeError):
                vc.wait_for_vram_headroom(timeout=1.0)

    def test_headroom_confirmed_returns_true_and_timeout_still_raises(self):
        from local_agent import vram_controller as vc

        with patch.object(subprocess, "check_output", return_value="1000, 15000\n"):
            self.assertTrue(vc.wait_for_vram_headroom(timeout=1.0))
        with patch.object(subprocess, "check_output", return_value="15000, 1000\n"):
            with self.assertRaises(TimeoutError):
                vc.wait_for_vram_headroom(timeout=0.2, interval=0.05)

    def test_release_after_comfyui_propagates_and_marks_unverified(self):
        from local_agent import vram_controller as vc

        owners = []
        with patch.object(vc, "comfy_free_memory", return_value={}), \
                patch.object(vc, "set_vram_owner", lambda o, r: owners.append(o)), \
                patch.object(vc, "wait_for_vram_headroom", side_effect=vc.VramProbeError("no smi")):
            with self.assertRaises(vc.VramProbeError):
                vc.release_after_comfyui(reason="t")
        self.assertIn("comfyui_unverified", owners)

    def test_generate_video_caller_does_not_swallow_silently(self):
        src = (ROOT / "generate_video.py").read_text(encoding="utf-8")
        self.assertNotIn('release_after_comfyui(reason="CLI clip saved")\n        except Exception:\n            pass', src)
        self.assertIn("VRAM release/headroom NOT verified", src)


class PortabilityEnvTests(unittest.TestCase):
    def test_gvd_root_defaults_to_checkout(self):
        self.assertEqual(batch.ROOT, ROOT)
        import gvd_watcher
        self.assertEqual(gvd_watcher.ROOT, ROOT)

    def test_flux_still_batch_honours_comfy_shared_env(self):
        import importlib

        # flux_still_batch pulls creative_still_qa -> cv2 at import; stub those so
        # the env-var contract can be checked on a box without OpenCV.
        stubs = {
            "creative_still_qa": types.SimpleNamespace(
                empty_pov_prompt_boost=lambda *a, **k: "", infer_visibility_expectation=lambda *a, **k: None),
            "backrooms_still_contract": types.SimpleNamespace(),
        }
        with patch.dict(sys.modules, stubs), \
                patch.dict(os.environ, {"COMFY_SHARED_INPUT": "/in", "COMFY_SHARED_OUTPUT": "/out"}):
            sys.modules.pop("flux_still_batch", None)
            mod = importlib.import_module("flux_still_batch")
            self.assertEqual((mod.SHARED_INPUT, mod.SHARED_OUTPUT), (Path("/in"), Path("/out")))
        with patch.dict(sys.modules, stubs), patch.dict(os.environ, {"COMFY_INPUT": "/legacy"}):
            os.environ.pop("COMFY_SHARED_INPUT", None)
            sys.modules.pop("flux_still_batch", None)
            mod = importlib.import_module("flux_still_batch")
            self.assertEqual(mod.SHARED_INPUT, Path("/legacy"), "old COMFY_INPUT spelling still honoured")
        sys.modules.pop("flux_still_batch", None)
