#!/usr/bin/env python3
"""Managed creative/storyboard prompt-pack task regressions."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import action_resolver
import agentic_state
import managed_prompt_pack
import remote_security
import router
import tools


def _synthetic_pack(n: int = 102, title: str = "Backrooms Sitcom Audition Prompt Pack") -> str:
    lines = [
        f"# {title}",
        "",
        f"Target length: 17 minutes, {n} clips, approximately 10 seconds per clip.",
        "",
        "This package covers the story from the audition tape through the first "
        "conversation with the entity. Generate each clip from its Start Frame "
        "and Last Frame. Use the Video Prompt as the motion direction.",
        "",
        "## Clip Prompts",
        "",
    ]
    for i in range(1, n + 1):
        cid = f"C{i:03d}"
        lines.extend([
            f"#### {cid}, 0:00-0:10",
            f"Start Frame: Yellow corridor view for {cid} with actor centered.",
            f"Last Frame: Actor takes one step forward in {cid}.",
            f"Video Prompt: Handheld camcorder motion for {cid}; fluorescent hum.",
            "",
        ])
    # pad to ensure length threshold
    lines.append("## Notes\n" + ("Continuity matters. " * 80))
    return "\n".join(lines)


class PromptPackDetectionTests(unittest.TestCase):
    def test_backrooms_pack_is_creative_not_image_or_h3(self):
        text = _synthetic_pack(102)
        self.assertTrue(managed_prompt_pack.is_prompt_pack(text))
        self.assertTrue(router.prompt_pack_intent(text))
        self.assertEqual(router.CAP_CREATIVE, router.classify_capability(text))
        self.assertNotEqual(router.CAP_IMAGE, router.classify_capability(text))
        # short still sheet still CAP_IMAGE
        sheet = (
            "START FRAME: wide yard\nEND FRAME: close-up\n"
            "Generate these photos using flux"
        )
        self.assertFalse(managed_prompt_pack.is_prompt_pack(sheet))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(sheet))

    def test_flattened_inline_pack_still_detected_and_parsed(self):
        """Codex/attachment pastes sometimes collapse newlines to spaces."""
        parts = ["# Backrooms Sitcom Audition Prompt Pack",
                 "Target length: 17 minutes, 102 clips."]
        for i in range(1, 21):
            cid = f"C{i:03d}"
            parts.append(
                f"#### {cid}, 0:00-0:10  Start Frame: Room {cid}.  "
                f"Last Frame: Step {cid}.  Video Prompt: Move {cid}."
            )
        text = "  ".join(parts) + "  " + ("Continuity. " * 100)
        self.assertTrue(managed_prompt_pack.is_prompt_pack(text))
        clips = managed_prompt_pack.parse_clips(text)
        self.assertGreaterEqual(len(clips), 20)
        self.assertEqual("C001", clips[0]["id"])
        self.assertIn("Room C001", clips[0]["start_frame"])
        self.assertEqual(router.CAP_CREATIVE, router.classify_capability(text))


class PromptPackPersistTests(unittest.TestCase):
    def test_102_clip_pack_chunked_and_persisted(self):
        text = _synthetic_pack(102)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                progress = managed_prompt_pack.ingest("packchat1", text)
                self.assertEqual(102, progress["clip_count"])
                self.assertTrue(Path(progress["source_path"]).is_file())
                # chunked export
                first = managed_prompt_pack.export_chunk("packchat1", chunk_size=24)
                self.assertEqual(24, first["exported_count"])
                self.assertEqual(78, first["remaining"])
                self.assertTrue(Path(first["written"][0]["md"]).is_file())
                done = managed_prompt_pack.export_all("packchat1", chunk_size=24)
                self.assertEqual(0, done["remaining"])
                self.assertEqual(102, done["exported_count"])
                self.assertTrue((Path(done["output_dir"]) / "INDEX.json").is_file())
                self.assertTrue((Path(done["output_dir"]) / "C001.md").is_file())
                self.assertTrue((Path(done["output_dir"]) / "C102.md").is_file())


class PromptPackContinueTests(unittest.TestCase):
    def test_continue_resumes_same_task_after_compaction(self):
        text = _synthetic_pack(40)
        with tempfile.TemporaryDirectory() as td_pack, tempfile.TemporaryDirectory() as td_state:
            with patch.object(managed_prompt_pack, "DIR", Path(td_pack)), \
                 patch.object(agentic_state, "DIR", Path(td_state)):
                agentic_state.begin_turn("packcont1", text)
                managed_prompt_pack.export_chunk("packcont1", chunk_size=10)
                # Simulate compaction: only short continue message
                cont = agentic_state.begin_turn("packcont1", "continue")
                self.assertEqual("active", cont["status"])
                self.assertEqual("prompt_pack", cont.get("kind"))
                block = agentic_state.prompt_block("packcont1")
                self.assertIn("source.md", block)
                self.assertIn("Trusted managed prompt-pack", block)
                # Action resolver resumes export
                plan = action_resolver.classify(
                    "continue", [{"role": "user", "content": "continue"}],
                    "packcont1",
                    pending_calibration_path_fn=lambda *_: None,
                    specialist_scope=False,
                )
                self.assertIsNotNone(plan)
                self.assertEqual("prompt_pack_continue", plan.intent)
                self.assertEqual("export_prompt_pack_outputs", plan.steps[0][0])

    def test_agent_finds_saved_source_from_task_state(self):
        text = _synthetic_pack(20)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                managed_prompt_pack.ingest("packsrc1", text)
                path = managed_prompt_pack.active_source_path("packsrc1")
                self.assertTrue(path)
                self.assertTrue(Path(path).is_file())
                saved = Path(path).read_text(encoding="utf-8")
                self.assertIn("Backrooms Sitcom Audition Prompt Pack", saved)
                # status tool
                ctx = remote_security.ToolContext(source="desktop", conversation_id="packsrc1")
                result = json.loads(tools.call("prompt_pack_status", {}, context=ctx))
                self.assertTrue(result["exists"])
                self.assertEqual(path, result["source_path"])


class PromptPackOutputAndGuardsTests(unittest.TestCase):
    def test_writes_real_output_files_not_instructions(self):
        text = _synthetic_pack(12)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                ctx = remote_security.ToolContext(source="desktop", conversation_id="packout1")
                ingest = json.loads(tools.call(
                    "ingest_prompt_pack", {"text": text}, context=ctx))
                self.assertTrue(ingest["ingested"])
                exported = json.loads(tools.call(
                    "export_prompt_pack_outputs", {"chunk_size": 12}, context=ctx))
                self.assertEqual(0, exported["remaining"])
                md = Path(exported["output_dir"]) / "C005.md"
                self.assertTrue(md.is_file())
                body = md.read_text(encoding="utf-8")
                self.assertIn("Start Frame", body)
                self.assertIn("Yellow corridor view for C005", body)
                self.assertNotIn("please generate", body.lower())

    def test_refuses_placeholder_prompts(self):
        self.assertTrue(managed_prompt_pack.is_placeholder_prompt("apple"))
        self.assertTrue(managed_prompt_pack.is_placeholder_prompt("test"))
        self.assertFalse(managed_prompt_pack.is_placeholder_prompt(
            "Yellow corridor view for C001 with actor centered."))
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                managed_prompt_pack.ingest(
                    "packph1", _synthetic_pack(12), allow_render=True)
                ctx = remote_security.ToolContext(
                    source="desktop", conversation_id="packph1")
                # Direct gate check via call wrapper
                result = tools.call(
                    "render_story_image",
                    {"story": "x", "prompt": "apple", "__conversation_id": "packph1"},
                    context=ctx,
                )
                self.assertTrue(result.startswith("ERROR:"))
                self.assertIn("placeholder", result.lower())

    def test_does_not_call_render_during_dry_run_planning(self):
        text = _synthetic_pack(16)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                managed_prompt_pack.ingest("packdry1", text)  # allow_render false
                allowed, reason = managed_prompt_pack.render_allowed("packdry1")
                self.assertFalse(allowed)
                self.assertIn("dry-run", reason.lower())
                ctx = remote_security.ToolContext(
                    source="desktop", conversation_id="packdry1")
                result = tools.call(
                    "render_story_image_batch",
                    {"jobs": [{"story": "C001", "prompt": "Yellow corridor"}],
                     "__conversation_id": "packdry1"},
                    context=ctx,
                )
                self.assertTrue(result.startswith("ERROR:"))
                self.assertIn("export", result.lower())
                # Action plan for pack must be ingest/export, not render
                plan = action_resolver.classify(
                    text, [{"role": "user", "content": text}],
                    "packdry1",
                    pending_calibration_path_fn=lambda *_: None,
                    specialist_scope=False,
                )
                self.assertEqual("prompt_pack_ingest_export", plan.intent)
                tool_names = [step[0] for step in plan.steps]
                self.assertIn("ingest_prompt_pack", tool_names)
                self.assertIn("export_prompt_pack_outputs", tool_names)
                self.assertNotIn("render_story_image", tool_names)
                self.assertNotIn("render_story_image_batch", tool_names)

    def test_task_state_survives_reload(self):
        text = _synthetic_pack(18)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                managed_prompt_pack.ingest("packrl1", text)
                managed_prompt_pack.export_chunk("packrl1", chunk_size=6)
                # "restart": reload from disk only
                progress = managed_prompt_pack.load_progress("packrl1")
                self.assertEqual(6, progress["next_index"])
                self.assertEqual(18, progress["clip_count"])
                self.assertTrue(Path(progress["source_path"]).is_file())
                resumed = managed_prompt_pack.export_all("packrl1", chunk_size=6)
                self.assertEqual(0, resumed["remaining"])
                self.assertEqual(18, resumed["exported_count"])


_EDITOR_PREAMBLE = """## EDITOR OVERRIDES — APPLY THESE RULES TO ALL SHOTS

This is an edited copy of the complete original prompt. All original clip-specific prompts remain below. The rules in this section take priority wherever the repeated prompts conflict with them.

0. Flux Image Generation Override
The still-image generator is Flux, not SDXL. Ignore every SDXL-specific instruction below.

1. Separate Flux Stills From Motion
For every Flux start frame and last frame, use a sharp static reference image. Do not ask Flux to show movement in a still.

2. Protect the Apartment Opening
For C001-C014, do not include Level 0, yellow Backrooms wallpaper, damp carpet, or fluorescent maze geometry.

3. Use the Backrooms Environment Only After the Fall
For frames after the fall, use sickly yellow patterned wallpaper and damp brown-beige carpet.

4. Diegetic Camera Lock
The viewer sees only through the story's physical camcorder. During C001-C014 it remains tripod-mounted.

5. Clean MiniMax Handoffs
Every video prompt is one continuous physical take between the supplied start frame and last frame.

6. Static Cut Exception
The only intentional cut is the brief static transition at C069.

## Story Rules
Preamble rules are not the pack appendix.

### Character Bible
Preamble notes about the actor must not be treated as the end of the pack.

## Generation Notes
Stills stay separate from motion.

## APPENDIX
This heading sits in the preamble, ahead of every clip.
"""


def _fully_merged_pack(n: int = 12, *, hashed: bool = True, titled: bool = True) -> str:
    """Minimal FULLY MERGED pack using the real '### Cxxx — … FRAME IMAGE' shape.

    hashed=False, titled=False is the shape of the 837,724-char paste that
    failed in chat a051127dca4b4a25: plain headers, no merged-title phrase.
    """
    lines = [
        "# Backrooms Sitcom Audition Prompt Pack — FULLY MERGED, CAMERA-LOGIC CORRECTED — 2026-09-08"
        if titled else "# Backrooms Sitcom Audition — clip prompts",
        "",
        "**Universal negative prompt (append to every still and video prompt):**",
        "",
        "No subtitles, extra limbs.",
        "",
        "**Universal continuity anchors (append to every still):**",
        "",
        "Use the same actor.",
        "",
        "## SECTION 1 — SDXL START/LAST FRAME IMAGE PROMPTS",
        "",
    ]

    def header(cid: str, kind: str) -> str:
        body = f"{cid} — {kind} — 0:00-0:10 — Camera Mode: A"
        return f"### {body}" if hashed else body

    for i in range(1, n + 1):
        cid = f"C{i:03d}"
        for kind, sentence in (
            ("START FRAME IMAGE", f"Static wide view of the apartment audition for {cid}."),
            ("LAST FRAME IMAGE", f"Actor facing the camcorder in {cid}."),
        ):
            lines.extend([
                header(cid, kind),
                "",
                "Positive prompt:",
                "",
                f"Authentic camcorder still. {sentence}",
                "",
                "Negative prompt: see Universal negative prompt above.",
                "",
            ])
    lines.extend(["## SECTION 2 — VIDEO GENERATION PROMPTS", ""])
    for i in range(1, n + 1):
        cid = f"C{i:03d}"
        lines.extend([
            header(cid, "VIDEO PROMPT"),
            "",
            "MiniMax first-last-frame prompt:",
            "",
            f"Beginning from Picture 1, the actor in {cid} holds still.",
            "",
        ])
    lines.extend([
        "## APPENDIX — GLOBAL CONTINUITY AND ASSEMBLY NOTES",
        "",
        "### Character Bible",
        "",
        "The actor.",
        "",
        "### Story Rules",
        "",
        "Apartment opening stays ordinary.",
        "",
    ])
    return "\n".join(lines)


class FullyMergedPreambleTests(unittest.TestCase):
    def test_prose_preamble_keeps_markdown_frame_headers(self):
        n = 12
        bare = _fully_merged_pack(n)
        text = _EDITOR_PREAMBLE + "\n" + bare
        bare_clips = managed_prompt_pack.parse_clips(bare)
        clips = managed_prompt_pack.parse_clips(text)
        self.assertEqual(n, len(bare_clips))
        self.assertEqual(n, len(clips))
        self.assertEqual([c["id"] for c in bare_clips], [c["id"] for c in clips])
        self.assertIn("apartment audition for C001", clips[0]["start_frame"])
        self.assertIn("apartment audition for C012", clips[-1]["start_frame"])
        self.assertIn("EDITOR OVERRIDES", clips[0]["production_instructions"])
        managed_prompt_pack.validate_clips(clips)

    def test_preamble_appendix_markers_do_not_drop_plain_headers(self):
        n = 12
        text = _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(n, hashed=False)
        clips = managed_prompt_pack.parse_clips(text)
        self.assertEqual(n, len(clips))
        self.assertEqual("C001", clips[0]["id"])
        self.assertEqual("C012", clips[-1]["id"])
        self.assertTrue(clips[0]["start_frame"].strip())
        self.assertTrue(clips[0]["video_prompt"].strip())

    def test_real_merged_pack_with_preamble_keeps_clip_count(self):
        pack_path = HERE.parent / "Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md"
        if not pack_path.is_file():
            self.skipTest(f"missing {pack_path}")
        bare = pack_path.read_text(encoding="utf-8")
        text = _EDITOR_PREAMBLE + "\n" + bare
        bare_clips = managed_prompt_pack.parse_clips(bare)
        clips = managed_prompt_pack.parse_clips(text)
        self.assertEqual(len(bare_clips), len(clips))
        self.assertGreaterEqual(len(clips), 102)
        self.assertEqual("C001", clips[0]["id"])
        self.assertEqual(bare_clips[-1]["id"], clips[-1]["id"])
        self.assertIn("EDITOR OVERRIDES", clips[0].get("production_instructions", ""))
        managed_prompt_pack.validate_clips(clips)

    def test_failed_ingest_persists_full_paste(self):
        good = _synthetic_pack(12)
        bad = (
            "# Backrooms Sitcom Audition Prompt Pack\n\n"
            "Target length: 17 minutes, 102 clips.\n\n"
            + "\n".join(
                f"Start Frame: ordinary apartment audition view {i} with the actor centered."
                for i in range(8)
            )
            + "\n"
            + ("Continuity matters for the handoff. " * 80)
        )
        self.assertGreater(len(bad), 1500)
        self.assertTrue(managed_prompt_pack.is_prompt_pack(bad))
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                managed_prompt_pack.ingest("packfail1", good)
                with self.assertRaises(ValueError) as raised:
                    managed_prompt_pack.ingest("packfail1", bad)
                self.assertIn("No clip prompts were parsed", str(raised.exception))
                task = Path(td) / "packfail1"
                self.assertEqual(bad, (task / "source.md").read_text(encoding="utf-8"))
                failed = list(task.glob("failed_ingest_*.md"))
                self.assertEqual(1, len(failed))
                self.assertEqual(bad, failed[0].read_text(encoding="utf-8"))
                snapshots = list(task.glob("source.*.md"))
                self.assertTrue(any(
                    snap.read_text(encoding="utf-8") == good for snap in snapshots
                ))


class UntitledPlainHeaderPackTests(unittest.TestCase):
    """Plain 'C001 — START FRAME IMAGE' headers with no FULLY MERGED title."""

    def _text(self, n: int = 12) -> str:
        text = _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(n, hashed=False, titled=False)
        self.assertNotIn("FULLY MERGED", text)
        self.assertNotIn("CAMERA-LOGIC CORRECTED", text)
        self.assertNotRegex(text, r"(?m)^#{2,4}\s*C\d")
        return text

    def test_untitled_plain_headers_detected_and_parsed(self):
        text = self._text(12)
        self.assertTrue(managed_prompt_pack.is_prompt_pack(text))
        clips = managed_prompt_pack.parse_clips(text)
        self.assertEqual([f"C{i:03d}" for i in range(1, 13)], [c["id"] for c in clips])
        self.assertIn("apartment audition for C001", clips[0]["start_frame"])
        self.assertTrue(clips[-1]["video_prompt"].strip())
        managed_prompt_pack.validate_clips(clips)

    def test_untitled_plain_headers_ingest(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                progress = managed_prompt_pack.ingest("packplain1", self._text(12))
        self.assertEqual(12, progress["clip_count"])
        self.assertEqual({"flux": 12}, progress["model_profiles"])

    def test_few_untitled_plain_headers_are_not_a_pack(self):
        # Without the title phrase, a handful of header-like lines is not enough.
        text = _fully_merged_pack(4, hashed=False, titled=False) + ("\nfiller " * 400)
        self.assertIsNone(managed_prompt_pack._parse_fully_merged_plain(text))


class EditorOverridesFluxTests(unittest.TestCase):
    """EDITOR OVERRIDES must yield model_profile == 'flux', not just a clip count."""

    def test_backrooms_compile_actually_loads(self):
        module = managed_prompt_pack._load_backrooms_compile()
        self.assertIsNotNone(
            module, f"backrooms_compile failed to load: {managed_prompt_pack._compile_error}")

    def _assert_all_flux(self, clips):
        self.assertTrue(clips)
        self.assertEqual({"flux"}, {c.get("model_profile") for c in clips})
        self.assertFalse(any("compile_fallback" in c for c in clips))

    def test_hashed_merged_pack_with_overrides_is_flux(self):
        self._assert_all_flux(managed_prompt_pack.parse_clips(
            _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(12)))

    def test_untitled_plain_pack_with_overrides_is_flux(self):
        self._assert_all_flux(managed_prompt_pack.parse_clips(
            _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(12, hashed=False, titled=False)))

    def test_real_merged_pack_with_overrides_is_flux(self):
        pack_path = HERE.parent / "Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md"
        if not pack_path.is_file():
            self.skipTest(f"missing {pack_path}")
        text = _EDITOR_PREAMBLE + "\n" + pack_path.read_text(encoding="utf-8")
        clips = managed_prompt_pack.parse_clips(text)
        self.assertGreaterEqual(len(clips), 102)
        self._assert_all_flux(clips)

    def test_pack_without_overrides_keeps_default_model(self):
        # Only an explicit Flux rule may switch the still model.
        clips = managed_prompt_pack.parse_clips(_fully_merged_pack(12))
        self.assertEqual(12, len(clips))
        self.assertNotIn("flux", {c.get("model_profile") for c in clips})

    def test_fallback_still_enforces_flux_and_says_so(self):
        text = _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(12, hashed=False, titled=False)
        with patch.object(managed_prompt_pack, "_load_backrooms_compile", return_value=None), \
                patch.object(managed_prompt_pack, "_compile_error", "ImportError: simulated"):
            clips = managed_prompt_pack.parse_clips(text)
        self.assertEqual({"flux"}, {c.get("model_profile") for c in clips})
        self.assertEqual({"ImportError: simulated"}, {c.get("compile_fallback") for c in clips})

    def test_import_does_not_leave_project_root_on_sys_path(self):
        cached = sys.modules.pop("backrooms_compile", None)
        try:
            with patch.object(managed_prompt_pack, "_compile_module", None), \
                    patch.object(managed_prompt_pack, "_compile_error", None):
                before = list(sys.path)
                self.assertIsNotNone(managed_prompt_pack._load_backrooms_compile())
                self.assertEqual(before, sys.path)
        finally:
            if cached is not None:
                sys.modules["backrooms_compile"] = cached


class IngestDiagnosticsAndReplyTests(unittest.TestCase):
    def test_failed_ingest_writes_diagnostics(self):
        # Clip IDs present but in a shape no parser reads (bold headers).
        bad = (
            "## EDITOR OVERRIDES — APPLY THESE RULES TO ALL SHOTS\n\n"
            "The still-image generator is Flux, not SDXL.\n\n"
            + "\n".join(
                f"**C{i:03d} — START FRAME IMAGE**\nStart Frame: apartment view {i}.\n"
                for i in range(1, 15)
            )
            + ("Continuity matters for the handoff. " * 60)
        )
        self.assertTrue(managed_prompt_pack.is_prompt_pack(bad))
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                with self.assertRaises(ValueError) as raised:
                    managed_prompt_pack.ingest("packdiag1", bad)
                message = str(raised.exception)
                self.assertIn("No clip prompts were parsed", message)
                self.assertIn("plain_frame_headers=0", message)
                diag_files = list((Path(td) / "packdiag1").glob("failed_ingest_*.diagnostics.json"))
                self.assertEqual(1, len(diag_files))
                diag = json.loads(diag_files[0].read_text(encoding="utf-8"))
        self.assertEqual("none", diag["branch"])
        self.assertEqual(0, diag["counts"]["plain_frame_headers"])
        self.assertEqual(14, diag["counts"]["lines_mentioning_clip_ids"])
        self.assertIn("**C001 — START FRAME IMAGE**", diag["sample_clip_id_lines"][0])
        self.assertTrue(diag["flux_required"])
        self.assertTrue(diag["head"].startswith("## EDITOR OVERRIDES"))

    def test_ingest_and_export_replies_tell_operator_what_is_next(self):
        text = _EDITOR_PREAMBLE + "\n" + _fully_merged_pack(12, hashed=False, titled=False)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(managed_prompt_pack, "DIR", Path(td)):
                ingested = json.loads(tools.ingest_prompt_pack(
                    {"__conversation_id": "packreply1", "text": text}))
                exported = json.loads(tools.export_prompt_pack_outputs(
                    {"__conversation_id": "packreply1"}))
        self.assertFalse(ingested["allow_render"])
        self.assertIn("12 clips parsed", ingested["operator_message"])
        self.assertIn("flux=12", ingested["operator_message"])
        self.assertIn("render it", ingested["operator_message"])
        self.assertIn("12 clips exported and ready", exported["operator_message"])
        self.assertIn("render it", exported["operator_message"])


if __name__ == "__main__":
    unittest.main()
