"""Regression for the actual frame-first layout that falsely exported empty videos."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import managed_prompt_pack as pack


def source():
    text = '# Storyboard Prompt Pack\n## EDITOR OVERRIDES\nApartment first; preserve this rule.\n'
    for i in range(1, 13):
        for kind in ('START', 'LAST'):
            text += f'\n### C{i:03d} — {kind} FRAME IMAGE — 0:00-0:10\nFilename: `clip.png`\nPositive prompt:\nReadable {kind.lower()} pose for actor {i}.\nNegative prompt:\nNo extra hands.\nContinuity anchors:\nKeep actor.\n'
    text += '\n## SECTION 2 — VIDEOS\n'
    for i in range(1, 13):
        text += f'\n### C{i:03d} — VIDEO PROMPT — 0:00-0:10\nUses start frame: `clip.png`\nUses last frame: `end.png`\nMiniMax first-last-frame prompt:\nThe actor in clip {i} raises a hand slowly.\n'
    return text


class Sections(unittest.TestCase):
    def test_render_typo_uses_saved_frame_and_repeat_checks_job(self):
        import action_resolver
        with tempfile.TemporaryDirectory() as td, patch.object(pack, 'DIR', Path(td)):
            pack.ingest('sections1', source())
            pack.export_all('sections1')
            classify = lambda text: action_resolver.classify(text, [], 'sections1',
                pending_calibration_path_fn=lambda *_: None, specialist_scope=False)
            plan = classify('redner')
            self.assertEqual(plan.steps[-1][0], 'render_story_image')
            self.assertEqual(plan.steps[-1][1]['prompt'], 'Readable start pose for actor 1.')
            pack.record_anchor_receipt('sections1', json.dumps({'started': True, 'pid': 123, 'story': 'anchor', 'log': 'test.log'}))
            for text in ('render', 'continue'):
                self.assertEqual(classify(text).steps[0][0], 'story_image_job_status')

    def test_three_sections_merge_and_keep_overrides(self):
        clips = pack.parse_clips(source())
        pack.validate_clips(clips)
        self.assertEqual(len(clips), 12)
        self.assertEqual(clips[0]['start_frame'], 'Readable start pose for actor 1.')
        self.assertEqual(clips[0]['last_frame'], 'Readable last pose for actor 1.')
        self.assertEqual(clips[0]['video_prompt'], 'The actor in clip 1 raises a hand slowly.')
        self.assertIn('Apartment first', clips[0]['production_instructions'])

    def test_empty_video_and_filename_are_not_complete(self):
        for invalid in ('', '`clip_001_start.png` Uses'):
            clips = pack.parse_clips(source())
            clips[0]['video_prompt'] = invalid
            with self.assertRaises(ValueError):
                pack.validate_clips(clips)

    def test_same_ids_revised_content_resets_without_overwriting_evidence(self):
        with tempfile.TemporaryDirectory() as td, patch.object(pack, 'DIR', Path(td)):
            pack.ingest('sections1', source())
            original = pack.export_all('sections1')
            old_file = Path(original['output_dir']) / 'C001.json'
            old_bytes = old_file.read_bytes()
            revised = source().replace('Apartment first', 'Apartment only until the fall')
            progress = pack.ingest('sections1', revised)
            self.assertEqual(progress['next_index'], 0)
            done = pack.export_all('sections1')
            self.assertNotEqual(original['output_dir'], done['output_dir'])
            self.assertEqual(old_file.read_bytes(), old_bytes)
            output = json.loads((Path(done['output_dir']) / 'C001.json').read_text())
            self.assertIn('Apartment only until the fall', output['production_instructions'])


if __name__ == '__main__':
    unittest.main()
