#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image
from gvd_qa.caption_v4 import parse_criterion_payload, caption_v4_checklist, png_to_jpeg_b64


class CaptionV4ParseTests(unittest.TestCase):
    def test_json_and_prose(self):
        self.assertEqual(parse_criterion_payload('{"verdict":"pass","evidence":"yellow walls"}')["verdict"], "pass")
        self.assertEqual(parse_criterion_payload("The criterion is unknown because of blur.")["verdict"], "unknown")
        self.assertEqual(parse_criterion_payload("```json\n{\"verdict\":\"fail\",\"evidence\":\"no person\"}\n```")["verdict"], "fail")

    def test_injected_chat(self):
        buf = BytesIO()
        Image.new("RGB", (8, 8), (9, 9, 9)).save(buf, format="PNG")
        png = buf.getvalue()
        self.assertTrue(png_to_jpeg_b64(png))
        def chat(messages, **kwargs):
            return json.dumps({"verdict": "fail", "evidence": "injected"}), {}
        checks = caption_v4_checklist(
            png, [{"id": "person_visible", "criterion": "A person is visible."}],
            chat_fn=chat,
        )
        self.assertEqual(checks[0]["verdict"], "fail")
        self.assertEqual(checks[0]["id"], "person_visible")


if __name__ == "__main__":
    unittest.main()
