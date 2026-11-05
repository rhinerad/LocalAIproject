#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import character_library as lib


class CharacterLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photos = self.root / "photos"
        self.photos.mkdir()
        for index in range(3):
            (self.photos / f"photo{index}.jpg").write_bytes(b"test")
        self.reference = self.photos / "photo0.jpg"
        self.library = self.root / "character_library.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_is_read_only_and_does_not_require_gpu(self):
        plan = lib.training_plan("Avery Stone", "avery-token", self.photos)
        self.assertTrue(plan["planned"])
        self.assertFalse(plan["executes_training"])
        self.assertEqual("none", plan["gpu_action"])
        self.assertEqual(3, plan["training_images"])
        self.assertFalse(self.library.exists())

    def test_registration_requires_explicit_consent(self):
        with self.assertRaisesRegex(lib.CharacterLibraryError, "consenting adult"):
            lib.register_character("Avery", "avery", self.reference, "avery.safetensors",
                                   consent_confirmed=False, library_path=self.library)
        self.assertFalse(self.library.exists())

    def test_registration_redacts_source_path_and_rejects_duplicates(self):
        entry = lib.register_character("Avery", "avery", self.reference, "avery.safetensors",
                                       consent_confirmed=True, library_path=self.library)
        self.assertEqual("photo0.jpg", entry["reference_photo_filename"])
        saved = json.loads(self.library.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.root), json.dumps(saved))
        with self.assertRaisesRegex(lib.CharacterLibraryError, "already registered"):
            lib.register_character("Avery", "avery2", self.reference, "avery2.safetensors",
                                   consent_confirmed=True, library_path=self.library)

    def test_non_image_reference_is_refused(self):
        text = self.root / "not-image.txt"
        text.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(lib.CharacterLibraryError, "supported image"):
            lib.register_character("Avery", "avery", text, "avery.safetensors",
                                   consent_confirmed=True, library_path=self.library)


if __name__ == "__main__":
    unittest.main(verbosity=2)
