from __future__ import annotations

import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class GuiRenderHintTests(unittest.TestCase):
    def test_dynamic_hint_matches_guarded_desktop_render_capability(self):
        page = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Desktop chats can start a guarded general render; phone chats cannot.", page)
        self.assertNotIn("It can\\'t start a render.", page)

    def test_coding_mode_is_a_picker_label(self):
        page = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Coding mode — ", page)
        self.assertIn("free the GPU for the 14B coder", page)

    def test_stream_restores_send_on_every_terminal_path(self):
        """Send must not stick on Stop after done/error/exception/Stop."""
        page = (HERE / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("let streamEpoch=0;", page)
        self.assertIn("function setBusy(on)", page)
        self.assertIn("}finally{", page)
        self.assertIn("if(epoch===streamEpoch){", page)
        self.assertIn("streamEpoch++;", page)
        self.assertIn("const orphaned=epoch!==streamEpoch;", page)
        # Stop unlocks immediately without aborting the drain.
        self.assertIn("Unlock Send immediately", page)
        self.assertIn("setBusy(false);", page)


if __name__ == "__main__":
    unittest.main()