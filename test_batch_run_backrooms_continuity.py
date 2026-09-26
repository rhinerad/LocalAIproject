#!/usr/bin/env python3
"""Offline tests for clip-to-clip continuity chaining in batch_run_backrooms_gvd.

2026-09-23: the batch used to render a fresh FLUX still for every clip. With
--continuity live it chains the previous clip's actual last frame when
work/scene_reasoner.py says context_video and the deterministic guards
(camera-mode change, CHAIN_MAX_CONSECUTIVE) allow; every other outcome must
fall back to the fresh still. Past the ceiling, a context_video clip is a
refine checkpoint (low-denoise FLUX img2img of the previous clip's last frame)
that restarts the chain count. Also locks in that --dry-run no longer
overwrites real progress.json clip entries.

No ComfyUI, GPU, Ollama, VLM or network: the reasoner, generate_video,
frame extraction and upload are all faked.
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "local_agent"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import batch_run_backrooms_gvd as batch  # noqa: E402
import video_chain  # noqa: E402


def _clip(cid: str, mode: str, action: str = "the view holds on the wallpaper.", speakers=("ACTOR",)) -> dict:
    return {
        "id": cid,
        "body": f"### {cid} — START FRAME IMAGE — 0:00-0:10 — Camera Mode: {mode}\n\nFilename: x",
        "start_frame": (
            "Shared boilerplate.\n\nA hand rests on yellow wallpaper.\n\n"
            "Preserve all character identity, clothing, camera defects."
        ),
        "start_frame_negative": "",
        "video_prompt": (
            "alignment line\n\nintegrated_multimodal_description: [Shot 1] boilerplate. "
            f"Beginning from Picture 1, {action} The action develops continuously in one take."
        ),
        "dialogue_lines": [{"speaker": s, "text": "hi"} for s in speakers],
    }


def _decided(source: str = "context_video", *, confidence=0.9, blocked=False, reason="same room") -> dict:
    return {
        "status": "blocked_awaiting_operator" if blocked else "decided",
        "decision": {
            "continuity_source": source,
            "continuity_reason": reason,
            "reference_character_ids": [],
            "confidence": confidence,
            "needs_operator_input": blocked,
            "question_for_operator": "which?" if blocked else "",
            "reasoning": "r",
            "parse_error": False,
        },
        "decision_log": None,
        "eviction": {"verified": True},
    }


def _args(**kw) -> types.SimpleNamespace:
    ns = types.SimpleNamespace(
        continuity=batch.CONTINUITY_LIVE,
        stills_only=False,
        dry_run=False,
        chain_max_consecutive=batch.CHAIN_MAX_CONSECUTIVE,
        continuity_story="test-story",
    )
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def selected_entry(self, name: str = "prev.mp4") -> dict:
        video = self.tmp / name
        video.write_bytes(b"\0" * 20_000)
        return {"status": "selected", "pipeline_state": "SELECTED", "video_path": str(video)}


class ContinuityPolicyTests(unittest.TestCase):
    def _p(self, reasoner, camera_changed=False, prev_depth=0, max_consecutive=4):
        return batch.continuity_policy(
            reasoner, camera_changed=camera_changed, prev_depth=prev_depth, max_consecutive=max_consecutive
        )

    def test_clean_context_video_chains(self):
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(self._p(summary), ("chain", "reasoner_context_video"))

    def test_reference_image_is_fresh(self):
        summary = batch._summarize_reasoner(_decided("reference_image"))
        self.assertEqual(self._p(summary), ("fresh_still", "reasoner_reference_image"))

    def test_none_is_fresh(self):
        summary = batch._summarize_reasoner(_decided("none"))
        self.assertEqual(self._p(summary), ("fresh_still", "reasoner_none"))

    def test_blocked_or_low_confidence_is_fresh_even_if_it_said_context_video(self):
        summary = batch._summarize_reasoner(_decided("context_video", confidence=0.3, blocked=True))
        self.assertEqual(self._p(summary), ("fresh_still", "reasoner_needs_operator_input"))

    def test_reasoner_error_or_missing_is_fresh(self):
        self.assertEqual(self._p({"status": "error"}), ("fresh_still", "reasoner_unavailable"))
        self.assertEqual(self._p(None), ("fresh_still", "reasoner_unavailable"))

    def test_camera_mode_change_overrides_context_video(self):
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(self._p(summary, camera_changed=True), ("fresh_still", "camera_mode_change"))

    def test_ceiling_routes_context_video_to_refine_checkpoint_by_default(self):
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(self._p(summary, prev_depth=4, max_consecutive=4),
                         ("refine_checkpoint", "chain_ceiling_refine"))
        self.assertEqual(self._p(summary, prev_depth=3, max_consecutive=4)[0], "chain")
        self.assertEqual(self._p(summary, prev_depth=0, max_consecutive=0),
                         ("refine_checkpoint", "chain_ceiling_refine"))

    def test_ceiling_with_fresh_still_reset_is_a_hard_cut(self):
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(
            batch.continuity_policy(summary, camera_changed=False, prev_depth=4, max_consecutive=4,
                                    reset=batch.CHAIN_RESET_FRESH),
            ("fresh_still", "chain_ceiling"),
        )

    def test_real_cuts_beat_the_ceiling(self):
        """A scene/camera change or re-entry past the ceiling is a fresh still, never a refine."""
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(self._p(summary, camera_changed=True, prev_depth=9), ("fresh_still", "camera_mode_change"))
        self.assertEqual(
            batch.continuity_policy(summary, camera_changed=False, prev_depth=9, max_consecutive=4,
                                    reentering=["ENTITY"]),
            ("fresh_still", "character_reentry"),
        )
        ref = batch._summarize_reasoner(_decided("reference_image"))
        self.assertEqual(self._p(ref, prev_depth=9), ("fresh_still", "reasoner_reference_image"))


class CharacterReentryTests(_Tmp):
    """Deterministic floor for the drift case the reasoner never flagged in shadow."""

    E = dict(action="the entity stands at the end of the hall.", speakers=("ACTOR",))
    NO_E = dict(action="the view holds on the wallpaper.", speakers=("ACTOR",))

    def _pack(self, *specs, mode="C"):
        clips = [_clip(f"C{40 + i:03d}", mode, **spec) for i, spec in enumerate(specs)]
        clips.append(_clip("C099", mode, speakers=("ENTITY",)))  # puts ENTITY in the cast
        return clips

    def test_reentry_after_absence_is_flagged(self):
        clips = self._pack(self.E, self.NO_E, self.E)
        self.assertEqual(batch.character_reentries(clips, 2), ["ENTITY"])

    def test_first_appearance_and_continuous_presence_are_not(self):
        clips = self._pack(self.NO_E, self.E, self.E)
        self.assertEqual(batch.character_reentries(clips, 1), [])
        self.assertEqual(batch.character_reentries(clips, 2), [])

    def test_speaking_counts_as_present(self):
        clips = self._pack(self.E, self.NO_E, dict(action="a voice calls out.", speakers=("ENTITY",)))
        self.assertEqual(batch.character_reentries(clips, 2), ["ENTITY"])

    def test_pov_camera_holder_never_reenters_in_pov_mode(self):
        silent = dict(action="the view holds on the wallpaper.", speakers=())
        clips = self._pack(dict(action="hi", speakers=("ACTOR",)), silent,
                           dict(action="hi", speakers=("ACTOR",)), mode="B")
        self.assertEqual(batch.character_reentries(clips, 2), [])
        clips_c = self._pack(dict(action="hi", speakers=("ACTOR",)), silent,
                             dict(action="hi", speakers=("ACTOR",)), mode="C")
        self.assertEqual(batch.character_reentries(clips_c, 2), ["ACTOR"])

    def test_reentry_forces_fresh_still_in_live(self):
        clips = self._pack(self.E, self.NO_E, self.E)
        extract = MagicMock()
        rec = batch.decide_continuity(
            _args(), clips, 2, prior=lambda pid: None, prev_entry=self.selected_entry(),
            reasoner=MagicMock(return_value=_decided("context_video")), ref2vid=lambda cid: False,
            extract=extract, upload=MagicMock(),
        )
        extract.assert_not_called()
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "character_reentry"))
        self.assertEqual(rec["reentering_characters"], ["ENTITY"])

    def test_policy_order(self):
        summary = batch._summarize_reasoner(_decided("context_video"))
        self.assertEqual(
            batch.continuity_policy(summary, camera_changed=False, prev_depth=0, max_consecutive=4,
                                    reentering=["ENTITY"]),
            ("fresh_still", "character_reentry"),
        )


class DecideContinuityTests(_Tmp):
    clips = [_clip("C010", "A"), _clip("C011", "A"), _clip("C012", "B")]

    def _decide(self, index=1, *, args=None, reasoner=None, prev_entry=None, prior=None, **kw):
        extract = kw.pop("extract", MagicMock(return_value=self.tmp / "prev_abc_last.png"))
        upload = kw.pop("upload", MagicMock(side_effect=lambda frame, url, name: name))
        rec = batch.decide_continuity(
            args or _args(),
            self.clips,
            index,
            prior=prior or (lambda pid: None),
            prev_entry=prev_entry,
            reasoner=reasoner or MagicMock(return_value=_decided("context_video")),
            ref2vid=kw.pop("ref2vid", lambda cid: False),
            extract=extract,
            upload=upload,
            comfy_url="http://fake:8188",
        )
        return rec, extract, upload

    def test_off_never_calls_reasoner(self):
        reasoner = MagicMock()
        rec, extract, _ = self._decide(args=_args(continuity="off"), reasoner=reasoner)
        reasoner.assert_not_called()
        extract.assert_not_called()
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "continuity_off"))

    def test_first_clip_is_fresh_and_skips_reasoner(self):
        reasoner = MagicMock()
        rec, _, _ = self._decide(index=0, reasoner=reasoner)
        reasoner.assert_not_called()
        self.assertEqual(rec["reason_code"], "first_clip")

    def test_stills_only_is_fresh(self):
        rec, _, _ = self._decide(args=_args(stills_only=True))
        self.assertEqual(rec["reason_code"], "stills_only")

    def test_live_context_video_chains_previous_clips_last_frame(self):
        prev = self.selected_entry()
        rec, extract, upload = self._decide(prev_entry=prev)
        extract.assert_called_once_with(Path(prev["video_path"]))
        self.assertEqual(rec["mode_used"], "chained")
        self.assertEqual(rec["source_clip_id"], "C010")
        self.assertEqual(rec["source_video_path"], prev["video_path"])
        self.assertEqual(rec["start_frame_path"], "chain_c011_prev_abc_last.png")
        self.assertEqual(upload.call_args.kwargs["url"], "http://fake:8188")
        self.assertEqual(rec["chain_depth"], 1)
        self.assertEqual(rec["continuity_reason"], "same room")

    def test_reasoner_gets_pack_context_and_history(self):
        reasoner = MagicMock(return_value=_decided("context_video"))
        self._decide(index=2, reasoner=reasoner, prev_entry=self.selected_entry())
        kw = reasoner.call_args.kwargs
        self.assertEqual(kw["shot_id"], "C012")
        self.assertTrue(kw["is_video_shot"])
        self.assertIn("camera mode B", kw["prompt_text"])
        self.assertIn("A hand rests on yellow wallpaper.", kw["prompt_text"])
        self.assertEqual([r["shot_id"] for r in kw["history"]], ["C010", "C011"])
        self.assertEqual(kw["history"][0]["camera_mode"], "A")
        self.assertFalse(kw["skip_eviction"], "live render runs must evict before each render")

    def test_camera_mode_change_falls_back(self):
        rec, extract, _ = self._decide(index=2, prev_entry=self.selected_entry())
        extract.assert_not_called()
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "camera_mode_change"))

    def test_reference_image_none_and_blocked_fall_back(self):
        for result, code in (
            (_decided("reference_image"), "reasoner_reference_image"),
            (_decided("none"), "reasoner_none"),
            (_decided("context_video", confidence=0.2, blocked=True), "reasoner_needs_operator_input"),
        ):
            with self.subTest(code=code):
                rec, extract, _ = self._decide(reasoner=MagicMock(return_value=result),
                                               prev_entry=self.selected_entry())
                extract.assert_not_called()
                self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", code))
                self.assertNotIn("start_frame_path", rec)

    def test_reasoner_exception_falls_back_and_is_recorded(self):
        rec, _, _ = self._decide(reasoner=MagicMock(side_effect=RuntimeError("ollama down")),
                                 prev_entry=self.selected_entry())
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "reasoner_unavailable"))
        self.assertIn("ollama down", rec["continuity_reason"])

    def test_prev_not_selected_falls_back(self):
        legacy = self.selected_entry()
        legacy.update(status="done", pipeline_state="")
        for entry in (None, legacy, {**self.selected_entry(), "stills_only": True}):
            with self.subTest(entry=bool(entry)):
                rec, extract, _ = self._decide(prev_entry=entry)
                extract.assert_not_called()
                self.assertEqual(rec["reason_code"], "prev_clip_not_selected")

    def test_extraction_or_upload_error_falls_back(self):
        rec, _, _ = self._decide(prev_entry=self.selected_entry(),
                                 extract=MagicMock(side_effect=video_chain.ChainFrameError("no frame")))
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "chain_frame_error"))
        self.assertIn("no frame", rec["chain_error"])
        rec, _, _ = self._decide(prev_entry=self.selected_entry(),
                                 upload=MagicMock(side_effect=video_chain.ChainFrameError("503")))
        self.assertEqual(rec["reason_code"], "chain_frame_error")

    def test_ref2vid_clip_falls_back(self):
        rec, extract, _ = self._decide(prev_entry=self.selected_entry(), ref2vid=lambda cid: True)
        extract.assert_not_called()
        self.assertEqual(rec["reason_code"], "ref2vid_path_has_no_first_frame")

    def test_shadow_records_would_chain_but_never_extracts(self):
        rec, extract, upload = self._decide(args=_args(continuity="shadow"), prev_entry=self.selected_entry())
        extract.assert_not_called()
        upload.assert_not_called()
        self.assertEqual(rec["mode_used"], "fresh_still")
        self.assertEqual(rec["policy"], "chain")
        self.assertTrue(rec["shadow_would_chain"])
        self.assertEqual(rec["policy_chain_depth"], 1)

    def test_live_refine_checkpoint_refines_previous_clips_last_frame(self):
        prev = self.selected_entry()
        rec, extract, upload = self._decide(
            prev_entry=prev,
            args=_args(refine_denoise=0.22, refine_sharpen=0.4),
            prior=lambda pid: {"chain_depth": 4, "policy_chain_depth": 4},
        )
        extract.assert_called_once_with(Path(prev["video_path"]))
        self.assertEqual((rec["policy"], rec["reason_code"]), ("refine_checkpoint", "chain_ceiling_refine"))
        self.assertEqual(rec["mode_used"], "refine_checkpoint")
        self.assertEqual(rec["refine_frame_path"], "refine_c011_prev_abc_last.png")
        self.assertEqual((rec["refine_denoise"], rec["refine_sharpen_alpha"]), (0.22, 0.4))
        self.assertEqual(rec["source_clip_id"], "C010")
        self.assertEqual(rec["source_video_path"], prev["video_path"])
        self.assertEqual((rec["chain_depth"], rec["policy_chain_depth"]), (0, 0), "refine is the new anchor")
        self.assertNotIn("start_frame_path", rec, "a refine must not bypass FLUX via first_frame")

    def test_refine_failures_fall_back_to_fresh_still(self):
        at_ceiling = lambda pid: {"chain_depth": 4, "policy_chain_depth": 4}  # noqa: E731
        rec, _, _ = self._decide(prev_entry=self.selected_entry(), prior=at_ceiling,
                                 extract=MagicMock(side_effect=video_chain.ChainFrameError("no frame")))
        self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", "chain_frame_error"))
        self.assertNotIn("refine_frame_path", rec)
        for kw, code in (
            (dict(prev_entry=None), "prev_clip_not_selected"),
            (dict(prev_entry=self.selected_entry(), ref2vid=lambda cid: True), "ref2vid_path_has_no_first_frame"),
        ):
            with self.subTest(code=code):
                rec, extract, _ = self._decide(prior=at_ceiling, **kw)
                extract.assert_not_called()
                self.assertEqual((rec["mode_used"], rec["reason_code"]), ("fresh_still", code))

    def test_shadow_records_would_refine_but_never_extracts(self):
        rec, extract, _ = self._decide(args=_args(continuity="shadow"), prev_entry=self.selected_entry(),
                                       prior=lambda pid: {"policy_chain_depth": 4})
        extract.assert_not_called()
        self.assertEqual(rec["mode_used"], "fresh_still")
        self.assertTrue(rec["shadow_would_refine"])
        self.assertFalse(rec["shadow_would_chain"])
        self.assertEqual(rec["policy_chain_depth"], 0)

    def test_dry_run_skips_per_shot_eviction(self):
        reasoner = MagicMock(return_value=_decided("context_video"))
        self._decide(args=_args(continuity="shadow", dry_run=True), reasoner=reasoner)
        self.assertTrue(reasoner.call_args.kwargs["skip_eviction"])


class ChainCeilingSequenceTests(_Tmp):
    """The ceiling must actually force a reset after N consecutive chained clips."""

    def _run(self, setting: str, max_consecutive: int, n: int = 8, reset: str = batch.CHAIN_RESET_REFINE) -> list[str]:
        clips = [_clip(f"C{i:03d}", "B") for i in range(20, 20 + n)]
        records: dict[str, dict] = {}
        entry = self.selected_entry()
        out = []
        for i in range(n):
            rec = batch.decide_continuity(
                _args(continuity=setting, chain_max_consecutive=max_consecutive, chain_reset=reset),
                clips, i,
                prior=records.get,
                prev_entry=entry,
                reasoner=MagicMock(return_value=_decided("context_video")),
                ref2vid=lambda cid: False,
                extract=MagicMock(return_value=self.tmp / "f_last.png"),
                upload=MagicMock(side_effect=lambda frame, url, name: name),
            )
            records[str(clips[i]["id"])] = rec
            out.append(rec["reason_code"] if setting == "shadow" else rec["mode_used"])
        return out

    def test_live_ceiling_of_two_refines_and_restarts_the_count(self):
        R = "refine_checkpoint"
        self.assertEqual(
            self._run("live", 2),
            ["fresh_still", "chained", "chained", R, "chained", "chained", R, "chained"],
        )

    def test_live_ceiling_of_two_with_fresh_still_reset(self):
        self.assertEqual(
            self._run("live", 2, reset=batch.CHAIN_RESET_FRESH),
            ["fresh_still", "chained", "chained", "fresh_still", "chained", "chained", "fresh_still", "chained"],
        )

    def test_live_default_ceiling(self):
        modes = self._run("live", batch.CHAIN_MAX_CONSECUTIVE, n=12)
        run = longest = 0
        for m in modes:
            run = run + 1 if m == "chained" else 0
            longest = max(longest, run)
        self.assertEqual(longest, batch.CHAIN_MAX_CONSECUTIVE)
        self.assertEqual(modes[batch.CHAIN_MAX_CONSECUTIVE + 1], "refine_checkpoint")
        self.assertEqual(modes.count("fresh_still"), 1, "only clip 0; a long scene never hard-cuts")

    def test_shadow_simulates_the_same_ceiling(self):
        codes = self._run("shadow", 2, n=5)
        self.assertEqual(
            codes,
            ["first_clip", "reasoner_context_video", "reasoner_context_video", "chain_ceiling_refine",
             "reasoner_context_video"],
        )


class MainLoopIntegrationTests(_Tmp):
    """Drive main() end to end with ComfyUI/reasoner/voice faked."""

    def setUp(self):
        super().setUp()
        self.submits: list[dict] = []

        def fake_submit(pred, hparams, **kw):
            self.submits.append(kw)
            out = self.tmp / f"{kw['clip_id']}.mp4"
            out.write_bytes(b"\0" * 20_000)
            return out

        self.fake_gv = types.SimpleNamespace(
            submit_comfy=fake_submit, DEFAULT_COMFY="http://fake:8188",
            caption_v4_listening=lambda: True,
        )
        self.fake_dv = types.SimpleNamespace(
            extract_dialogue_array=lambda src: [],
            dialogue_to_speech_text=lambda lines: "",
            extract_raw_dialogue=lambda src: "",
            is_c001=lambda cid: False,
            lock_c001_master_voice=MagicMock(),
        )
        self.fake_rules = types.SimpleNamespace(
            write_rules_lock=lambda pack: self.tmp / "lock.json",
            apply_immutable_rules=lambda merged: merged,
        )
        self.reasoner_mod = types.SimpleNamespace(
            reason_about_shot=MagicMock(return_value=_decided("context_video")),
            evict_reasoning_model=MagicMock(return_value={"verified": True}),
        )
        self.uploads: list[str] = []

        def fake_upload(frame, *, url, name=None):
            self.uploads.append(name)
            return name

        self.patches = [
            patch.dict(sys.modules, {
                "generate_video": self.fake_gv,
                "dynamic_voice": self.fake_dv,
                "gvd_pipeline_rules": self.fake_rules,
            }),
            patch.object(batch, "PROGRESS_DIR", self.tmp),
            patch.object(batch, "PROGRESS_PATH", self.tmp / "progress.json"),
            patch.object(batch, "DRY_RUN_REPORT_PATH", self.tmp / "dry_run_report.json"),
            patch.object(batch, "load_clip_override", return_value={}),
            patch.object(batch, "gate_before_video_submit", return_value=None),
            patch.object(batch, "_wants_ref2vid", return_value=False),
            patch.object(batch, "_load_scene_reasoner", return_value=self.reasoner_mod),
            patch.object(video_chain, "extract_last_frame",
                         side_effect=lambda v: self.tmp / f"{Path(v).stem}_d1g3st_last.png"),
            patch.object(video_chain, "upload_to_comfy_input", side_effect=fake_upload),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        super().tearDown()

    def _main(self, clips, *extra):
        with patch.object(batch, "ingest_pack", return_value=clips):
            return batch.main(["--sleep", "0", *extra])

    def test_live_run_chains_within_scene_and_refreshes_at_camera_change(self):
        clips = [_clip("C010", "A"), _clip("C011", "A"), _clip("C012", "A"), _clip("C013", "B")]
        self.assertEqual(self._main(clips, "--continuity", "live"), 0)
        starts = [kw.get("start_frame_path") for kw in self.submits]
        self.assertEqual(starts[0], None, "clip 0 renders a fresh FLUX still")
        self.assertEqual(starts[1], "chain_c011_br_c010_d1g3st_last.png")
        self.assertEqual(starts[2], "chain_c012_br_c011_d1g3st_last.png")
        self.assertEqual(starts[3], None, "camera-mode change renders a fresh FLUX still")

        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        c12 = prog["C012"]
        self.assertEqual(c12["status"], "selected")
        self.assertEqual(c12["start_frame_source"], "chained_from:C011")
        self.assertEqual(c12["continuity"]["mode_used"], "chained")
        self.assertEqual(c12["continuity"]["source_clip_id"], "C011")
        self.assertEqual(c12["continuity"]["chain_depth"], 2)
        self.assertEqual(c12["continuity"]["reasoner"]["continuity_source"], "context_video")
        self.assertEqual(c12["continuity"]["continuity_reason"], "same room")
        self.assertTrue(c12["continuity"]["source_video_path"].endswith("br_c011.mp4"))
        self.assertEqual(prog["C013"]["start_frame_source"], "fresh_flux_still")
        self.assertEqual(prog["C013"]["continuity"]["reason_code"], "camera_mode_change")
        self.assertEqual(prog["C010"]["continuity"]["reason_code"], "first_clip")

    def test_live_ceiling_in_main_submits_refine_checkpoint(self):
        clips = [_clip(f"C{i:03d}", "B") for i in range(30, 34)]
        self._main(clips, "--continuity", "live", "--chain-max-consecutive", "1", "--refine-denoise", "0.25")
        starts = [kw.get("start_frame_path") for kw in self.submits]
        refines = [kw.get("refine_frame_path") for kw in self.submits]
        self.assertEqual(starts, [None, "chain_c031_br_c030_d1g3st_last.png", None, "chain_c033_br_c032_d1g3st_last.png"])
        self.assertEqual(refines, [None, None, "refine_c032_br_c031_d1g3st_last.png", None])
        self.assertEqual(self.submits[2]["refine_denoise"], 0.25)
        self.assertEqual(self.submits[2]["refine_sharpen_alpha"], 0.0)
        self.assertNotIn("refine_denoise", self.submits[1], "plain chains/stills get no refine kwargs")
        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        c32 = prog["C032"]
        self.assertEqual(c32["start_frame_source"], "refined_from:C031")
        self.assertEqual(c32["continuity"]["mode_used"], "refine_checkpoint")
        self.assertEqual(c32["continuity"]["reason_code"], "chain_ceiling_refine")
        self.assertEqual(c32["continuity"]["chain_depth"], 0)
        self.assertTrue(c32["continuity"]["source_video_path"].endswith("br_c031.mp4"))
        self.assertEqual(prog["C033"]["continuity"]["chain_depth"], 1, "chain restarts from the refined anchor")
        self.assertEqual(prog["C033"]["start_frame_source"], "chained_from:C032")

    def test_live_ceiling_in_main_with_fresh_still_reset(self):
        clips = [_clip(f"C{i:03d}", "B") for i in range(30, 34)]
        self._main(clips, "--continuity", "live", "--chain-max-consecutive", "1", "--chain-reset", "fresh_still")
        self.assertEqual([kw.get("start_frame_path") is not None for kw in self.submits], [False, True, False, True])
        self.assertEqual([kw.get("refine_frame_path") for kw in self.submits], [None] * 4)
        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(prog["C032"]["continuity"]["reason_code"], "chain_ceiling")
        self.assertEqual(prog["C032"]["start_frame_source"], "fresh_flux_still")

    def test_invalid_refine_args_are_rejected_before_anything_runs(self):
        for bad in (["--refine-denoise", "0"], ["--refine-denoise", "1.2"], ["--refine-sharpen", "-1"]):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                with patch("sys.stderr"):
                    self._main([_clip("C010", "A")], "--continuity", "live", *bad)
        self.assertEqual(self.submits, [])

    def test_default_is_off_and_never_chains_or_calls_reasoner(self):
        clips = [_clip("C010", "A"), _clip("C011", "A")]
        self._main(clips)
        self.assertEqual([kw.get("start_frame_path") for kw in self.submits], [None, None])
        self.reasoner_mod.reason_about_shot.assert_not_called()
        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(prog["C011"]["continuity"]["reason_code"], "continuity_off")

    def test_render_error_still_records_the_continuity_decision(self):
        clips = [_clip("C010", "A"), _clip("C011", "A")]
        calls = {"n": 0}
        original = self.fake_gv.submit_comfy

        def flaky(pred, hparams, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("comfy fell over")
            return original(pred, hparams, **kw)

        self.fake_gv.submit_comfy = flaky
        self.assertEqual(self._main(clips, "--continuity", "live"), 1)
        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(prog["C011"]["status"], "error")
        self.assertEqual(prog["C011"]["continuity"]["mode_used"], "chained")

    def test_shadow_dry_run_leaves_progress_clips_untouched(self):
        real = {"status": "selected", "pipeline_state": "SELECTED", "video_path": "X:/real.mp4"}
        (self.tmp / "progress.json").write_text(
            json.dumps({"pack": "p", "created": "t", "clips": {"C010": real}}), encoding="utf-8"
        )
        clips = [_clip("C010", "A"), _clip("C011", "A"), _clip("C012", "B")]
        self.assertEqual(self._main(clips, "--dry-run", "--continuity", "shadow", "--force"), 0)
        prog = json.loads((self.tmp / "progress.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(prog, {"C010": real}, "dry run must not overwrite real clip entries")
        report = json.loads((self.tmp / "dry_run_report.json").read_text(encoding="utf-8"))["clips"]
        self.assertEqual(sorted(report), ["C010", "C011", "C012"])
        self.assertTrue(report["C011"]["continuity"]["shadow_would_chain"])
        self.assertEqual(report["C012"]["continuity"]["reason_code"], "camera_mode_change")
        self.assertEqual(self.submits, [])
        for call in self.reasoner_mod.reason_about_shot.call_args_list:
            self.assertTrue(call.kwargs["skip_eviction"])
        self.reasoner_mod.evict_reasoning_model.assert_called_once()
        review = (self.tmp / "continuity_shadow_review.md").read_text(encoding="utf-8")
        self.assertIn("| C011 | A | ACTOR |  | context_video | 0.9 | chain | reasoner_context_video |", review)


class RefineCheckpointGraphTests(unittest.TestCase):
    """The real flux_minimax_i2v_api.json template, rewired offline for a refine checkpoint."""

    HP = {"cfg_scale": 3.5, "step_count": 20, "denoise": 1.0}

    @classmethod
    def setUpClass(cls):
        import dspy_orchestrator
        cls.o = dspy_orchestrator
        if not cls.o.MINIMAX_GRAPH_TEMPLATE.exists():
            raise unittest.SkipTest("graph template missing")

    def _build(self, **kw):
        with patch("sys.stdout"):
            return self.o.build_minimax_graph(
                "a yellow hallway", "the camera drifts", self.HP, clip_id="br_c013", enable_f5_voice=False, **kw
            )

    @staticmethod
    def _dangling(body: dict) -> list:
        return [
            (nid, key) for nid, node in body.items() for key, v in node["inputs"].items()
            if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int) and str(v[0]) not in body
        ]

    def test_refine_rewires_flux_to_img2img_and_feeds_minimax(self):
        g = self._build(refine_frame_path=r"A:\x\chain_frames\refine_c013_f_last.png", refine_denoise=0.3)
        body = self.o._comfy_prompt_graph(g)
        self.assertNotIn("5", body, "EmptyFlux2LatentImage must be gone")
        self.assertEqual(body["1003"], {"class_type": "LoadImage", "inputs": {"image": "refine_c013_f_last.png"}})
        self.assertEqual(body["1004"]["class_type"], "ImageScale")
        self.assertEqual((body["1004"]["inputs"]["width"], body["1004"]["inputs"]["height"]), (1280, 704))
        self.assertEqual(body["1005"], {"class_type": "VAEEncode",
                                        "inputs": {"pixels": ["1004", 0], "vae": ["10", 0]}})
        k = body["3"]["inputs"]
        self.assertEqual((k["latent_image"], k["denoise"]), (["1005", 0], 0.3))
        self.assertEqual((k["positive"], k["negative"], k["model"]), (["12", 0], ["7", 0], ["41", 0]))
        self.assertEqual(body["6"]["inputs"]["text"], "a yellow hallway", "same start_prompt conditioning")
        self.assertEqual(body["20"]["inputs"]["first_frame"], ["8", 0])
        self.assertNotIn("1001", body)
        self.assertEqual(self._dangling(body), [])
        self.assertFalse(g["_meta"]["flux_still_skipped"])
        self.assertEqual(g["_meta"]["refine_checkpoint"]["denoise"], 0.3)

    def test_sharpen_is_opt_in_and_feeds_both_minimax_and_stills_preview(self):
        body = self.o._comfy_prompt_graph(self._build(refine_frame_path="f.png", refine_denoise=0.3))
        self.assertNotIn("1006", body)
        body = self.o._comfy_prompt_graph(
            self._build(refine_frame_path="f.png", refine_denoise=0.3, refine_sharpen_alpha=0.5)
        )
        self.assertEqual(body["1006"]["inputs"]["image"], ["8", 0])
        self.assertEqual(body["20"]["inputs"]["first_frame"], ["1006", 0])
        stills = self._build(refine_frame_path="f.png", refine_denoise=0.3, refine_sharpen_alpha=0.5,
                             stills_only=True, prefix="t/refine")
        save = [n for n in stills.values() if isinstance(n, dict) and n.get("class_type") == "SaveImage"]
        self.assertEqual(save[0]["inputs"]["images"], ["1006", 0])
        self.assertNotIn("20", stills)
        self.assertEqual(self._dangling(self.o._comfy_prompt_graph(stills)), [])

    def test_no_refine_leaves_the_t2i_graph_unchanged(self):
        body = self.o._comfy_prompt_graph(self._build())
        self.assertEqual(body["3"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(body["3"]["inputs"]["denoise"], 1.0)
        self.assertFalse({"1003", "1004", "1005", "1006"} & set(body))

    def test_invalid_refine_requests_raise(self):
        with self.assertRaises(ValueError):
            self._build(refine_frame_path="f.png", refine_denoise=0.3, start_frame_path="chain.png")
        with self.assertRaises(ValueError):
            self._build(refine_frame_path="f.png")
        for bad in (0.0, 1.0, 1.5):
            with self.subTest(denoise=bad), self.assertRaises(ValueError):
                self._build(refine_frame_path="f.png", refine_denoise=bad)
        with self.assertRaises(RuntimeError):
            self.o.bind_refine_checkpoint({"3": {"class_type": "KSampler", "inputs": {}}},
                                          frame_path="f.png", denoise=0.3)


@unittest.skipUnless(__import__("shutil").which("ffmpeg") and __import__("shutil").which("ffprobe"),
                     "ffmpeg/ffprobe not on PATH")
class ExtractLastFrameTests(_Tmp):
    """Real ffmpeg on a synthetic clip: red for 1.5 s, then blue for the last 0.5 s."""

    def _make_video(self) -> Path:
        import subprocess
        out = self.tmp / "synthetic.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=24:d=1.5",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=24:d=0.5",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1,noise=alls=30:allf=t,format=yuv420p",
            "-c:v", "libx264", "-y", str(out),
        ], check=True, capture_output=True, timeout=60)
        return out

    @staticmethod
    def _mean_rgb(png: Path) -> tuple[float, float, float]:
        import subprocess
        raw = subprocess.check_output(
            ["ffmpeg", "-v", "error", "-i", str(png), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], timeout=30
        )
        n = len(raw) // 3
        return tuple(sum(raw[c::3]) / n for c in range(3))  # type: ignore[return-value]

    def test_extracts_the_final_frame_with_content_digest_name(self):
        video = self._make_video()
        frame = video_chain.extract_last_frame(video, out_dir=self.tmp / "frames")
        self.assertEqual(frame.name, f"synthetic_{video_chain.file_digest(video)}_last.png")
        r, g, b = self._mean_rgb(frame)
        self.assertGreater(b, r + 50, f"last frame should be blue, got rgb=({r:.0f},{g:.0f},{b:.0f})")
        self.assertEqual(video_chain.extract_last_frame(video, out_dir=self.tmp / "frames"), frame)

    def test_missing_or_non_video_source_raises(self):
        with self.assertRaises(video_chain.ChainFrameError):
            video_chain.extract_last_frame(self.tmp / "nope.mp4", out_dir=self.tmp)
        png = self.tmp / "still.png"
        png.write_bytes(b"x")
        with self.assertRaises(video_chain.ChainFrameError):
            video_chain.extract_last_frame(png, out_dir=self.tmp)

    def test_corrupt_video_raises_instead_of_guessing(self):
        bad = self.tmp / "bad.mp4"
        bad.write_bytes(b"not a video" * 100)
        with self.assertRaises(video_chain.ChainFrameError):
            video_chain.extract_last_frame(bad, out_dir=self.tmp)


if __name__ == "__main__":
    unittest.main()
