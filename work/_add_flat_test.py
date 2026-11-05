from pathlib import Path
# append flattened-pack test to test file
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\test_managed_prompt_pack.py")
t = p.read_text(encoding="utf-8")
extra = '''
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
        self.assertNotIn("\\n####", text)
        self.assertTrue(managed_prompt_pack.is_prompt_pack(text))
        clips = managed_prompt_pack.parse_clips(text)
        self.assertGreaterEqual(len(clips), 20)
        self.assertEqual("C001", clips[0]["id"])
        self.assertIn("Room C001", clips[0]["start_frame"])
        self.assertEqual(router.CAP_CREATIVE, router.classify_capability(text))
'''
if "test_flattened_inline_pack_still_detected_and_parsed" not in t:
    t = t.replace(
        "class PromptPackPersistTests(unittest.TestCase):",
        extra + "\n\nclass PromptPackPersistTests(unittest.TestCase):",
        1,
    )
    # Wait - that puts method outside class. Fix: put inside DetectionTests
    t = p.read_text(encoding="utf-8")
    needle = "        self.assertEqual(router.CAP_IMAGE, router.classify_capability(sheet))\n"
    method = '''        self.assertEqual(router.CAP_IMAGE, router.classify_capability(sheet))

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
'''
    if "test_flattened_inline_pack_still_detected_and_parsed" not in t:
        if needle not in t:
            raise SystemExit("needle missing")
        t = t.replace(needle, method, 1)
        p.write_text(t, encoding="utf-8")
        print("test added")
    else:
        print("already")
else:
    print("skip")
