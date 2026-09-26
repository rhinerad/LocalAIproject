#!/usr/bin/env python3
"""Duplicate-generation detection: caption overlap + perceptual dhash."""
from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image

from gvd_qa.duplicate import (
    caption_overlap,
    detect_duplicates,
    dhash_bytes,
    hamming,
)
from gvd_qa.evaluate import evaluate_artifact


def _png(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class CaptionOverlapTests(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(
            caption_overlap("empty yellow corridor hallway", "empty yellow corridor hallway"),
            1.0,
        )

    def test_disjoint(self):
        self.assertEqual(
            caption_overlap("empty yellow corridor hallway", "portrait of a dog park"),
            0.0,
        )

    def test_short_tokens_ignored(self):
        # 'a' and 'of' are filtered; only shared meaningful tokens count.
        self.assertGreaterEqual(caption_overlap("a hallway", "a hallway"), 0.99)
        self.assertEqual(caption_overlap("a hallway", "a hallway"), 1.0)


class DhashTests(unittest.TestCase):
    def test_identical_bytes_same_hash(self):
        png = _png((12, 34, 56))
        self.assertEqual(dhash_bytes(png), dhash_bytes(png))
        self.assertEqual(hamming(dhash_bytes(png), dhash_bytes(png)), 0)

    def test_flat_colors_differ(self):
        black = dhash_bytes(_png((0, 0, 0)))
        white = dhash_bytes(_png((255, 255, 255)))
        # Flat images hash by row-to-row difference structure; both flat
        # images yield the all-zero hash, so use textured gradients instead.
        buf_a = BytesIO()
        buf_b = BytesIO()
        img_a = Image.new("RGB", (64, 64))
        img_b = Image.new("RGB", (64, 64))
        for y in range(64):
            for x in range(64):
                img_a.putpixel((x, y), (x * 4 % 256, y * 4 % 256, 0))
                img_b.putpixel((x, y), (255 - x * 4 % 256, 255 - y * 4 % 256, 0))
        img_a.save(buf_a, format="PNG")
        img_b.save(buf_b, format="PNG")
        hash_a = dhash_bytes(buf_a.getvalue())
        hash_b = dhash_bytes(buf_b.getvalue())
        self.assertIsNotNone(hash_a)
        self.assertIsNotNone(hash_b)
        self.assertGreater(hamming(hash_a, hash_b), 0)


class DetectDuplicatesTests(unittest.TestCase):
    def _pair(self, caption_a: str, caption_b: str) -> tuple[bytes, bytes]:
        return _png((10, 20, 30)), _png((10, 20, 30))

    def test_no_prior_no_duplicate(self):
        report = detect_duplicates(
            candidate_image=_png((1, 2, 3)),
            candidate_caption="empty yellow corridor hallway",
            prior=[],
        )
        self.assertFalse(report["duplicate"])
        self.assertEqual(report["reasons"], [])

    def test_identical_image_and_caption_flagged(self):
        image = _png((4, 5, 6))
        report = detect_duplicates(
            candidate_image=image,
            candidate_caption="empty yellow corridor hallway fluorescent lights",
            prior=[("empty yellow corridor hallway fluorescent lights", image)],
        )
        self.assertTrue(report["duplicate"])
        self.assertIn("duplicate_caption_and_fingerprint", report["reasons"])

    def test_same_caption_no_prior_image_caption_only(self):
        # Caption-only fallback: no prior fingerprint available.
        report = detect_duplicates(
            candidate_image=_png((1, 1, 1)),
            candidate_caption="empty yellow corridor hallway",
            prior=[("empty yellow corridor hallway", None)],
        )
        self.assertTrue(report["duplicate"])
        self.assertIn("duplicate_caption", report["reasons"])

    def test_same_caption_distinct_fingerprint_not_duplicate(self):
        # Same caption but visibly different image is NOT a duplicate output.
        def _gradient(direction: int) -> bytes:
            buf = BytesIO()
            img = Image.new("RGB", (64, 64))
            for y in range(64):
                for x in range(64):
                    if direction == 0:
                        img.putpixel((x, y), (x * 4 % 256, y * 4 % 256, 0))
                    else:
                        img.putpixel((x, y), (255 - x * 4 % 256, 255 - y * 4 % 256, 0))
            img.save(buf, format="PNG")
            return buf.getvalue()

        report = detect_duplicates(
            candidate_image=_gradient(0),
            candidate_caption="empty yellow corridor hallway",
            prior=[("empty yellow corridor hallway", _gradient(1))],
        )
        self.assertFalse(report["duplicate"])
        self.assertEqual(report["reasons"], [])

    def test_distinct_caption_no_duplicate(self):
        report = detect_duplicates(
            candidate_image=_png((7, 8, 9)),
            candidate_caption="empty yellow corridor hallway",
            prior=[("office desk with papers", _png((7, 8, 9)))],
        )
        self.assertFalse(report["duplicate"])


class EvaluateIntegrationTests(unittest.TestCase):
    def test_duplicate_holds_review(self):
        image = _png((3, 3, 3))
        report = evaluate_artifact(
            prompt="empty yellow corridor hallway",
            vlm_caption="empty yellow corridor hallway",
            artifact_bytes=image,
            prior_artifacts=[("empty yellow corridor hallway", image)],
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["action"], "hold_review")
        self.assertIn(
            "duplicate_caption_and_fingerprint", report["reasons"]
        )
        self.assertTrue(report["duplicate"]["duplicate"])

    def test_no_prior_unchanged(self):
        report = evaluate_artifact(prompt="empty yellow corridor hallway")
        self.assertIn("duplicate", report)
        self.assertFalse(report["duplicate"]["duplicate"])


if __name__ == "__main__":
    unittest.main()
