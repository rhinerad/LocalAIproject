import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from sdxl_lora_readiness import inspect_dataset


class ReadinessTests(unittest.TestCase):
    def test_identity_requires_images_and_captions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(20):
                (root / f"{index}.png").write_bytes(b"not-decoded-by-preflight")
                (root / f"{index}.txt").write_text("trigger adult portrait", encoding="utf-8")
            result = inspect_dataset(root, "identity")
        self.assertTrue(result["ready_for_controlled_run"])
        self.assertEqual(result["images"], 20)

    def test_missing_caption_warns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(20): (root / f"{index}.jpg").write_bytes(b"x")
            result = inspect_dataset(root, "identity")
        self.assertFalse(result["ready_for_controlled_run"])
        self.assertIn("missing", " ".join(result["warnings"]))


if __name__ == "__main__": unittest.main()
