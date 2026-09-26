#!/usr/bin/env python3
"""Caption V4 score parser: markdown fences and prose must not collapse to 0.00."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "local_agent"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from media_accuracy_gate import parse_video_director_scores

EXACT = dict(model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp")


class MessyVlmParserTests(unittest.TestCase):
    def test_markdown_fenced_json_extracts_scores(self):
        caption = """Here is the rubric:

```json
{
  "text_video_alignment": 0.82,
  "temporal_consistency": 0.74,
  "aesthetic_quality": 0.80,
  "rationale": {
    "text_video_alignment": "drone and cliffs visible",
    "temporal_consistency": "motion holds",
    "aesthetic_quality": "golden hour"
  }
}
```
"""
        parsed = parse_video_director_scores(caption, "drone cliffs", **EXACT)
        self.assertEqual(parsed["status"], "pass", parsed["reasons"])
        self.assertEqual(parsed["scores"]["text_video_alignment"], 0.82)
        self.assertEqual(parsed["scores"]["temporal_consistency"], 0.74)
        self.assertEqual(parsed["scores"]["aesthetic_quality"], 0.80)
        self.assertNotEqual(parsed["minimum"], 0.0)

    def test_prose_axis_keywords_extract_instead_of_zeros(self):
        caption = (
            "The clip is a cinematic drone pass.\n"
            "text_video_alignment: 0.81\n"
            "temporal_consistency score 0.70\n"
            "aesthetic quality = 78%\n"
        )
        parsed = parse_video_director_scores(caption, "drone cliffs", **EXACT)
        self.assertEqual(parsed["scores"]["text_video_alignment"], 0.81)
        self.assertEqual(parsed["scores"]["temporal_consistency"], 0.70)
        self.assertEqual(parsed["scores"]["aesthetic_quality"], 0.78)
        self.assertGreater(parsed["minimum"], 0.0)

    def test_json_all_zeros_overridden_by_prose_ratings(self):
        caption = """```json
{"text_video_alignment": 0.0, "temporal_consistency": 0.0, "aesthetic_quality": 0.0}
```
Alignment: 0.66  temporal consistency: 0.71  aesthetic quality: 0.64
"""
        parsed = parse_video_director_scores(caption, "hallway", **EXACT)
        self.assertEqual(parsed["scores"]["text_video_alignment"], 0.66)
        self.assertEqual(parsed["scores"]["temporal_consistency"], 0.71)
        self.assertEqual(parsed["scores"]["aesthetic_quality"], 0.64)


if __name__ == "__main__":
    unittest.main()
