import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import batch_generate_backrooms as b

class RecoveryTests(unittest.TestCase):
    def test_phase4_failure_keeps_source_checkpoint_and_never_calls_earlier_phases(self):
        clip = b.load_clips(b.CLIPS_PATH)[0]
        source = b.FLF_DIR / 'br24_C016_00001.mp4'
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'OUT_DIR', Path(directory)), \
             patch.object(b, 'run_phase4', side_effect=RuntimeError('simulated sampling failure')), \
             patch.object(b, '_submit_still') as still, \
             patch.object(b.tp, 'runtime_inject_temporal_physics') as inject:
            with self.assertRaisesRegex(RuntimeError, 'simulated sampling failure'):
                b.process_clip(SimpleNamespace(watch=Mock()), clip, phase4_only=True)
            state = b.json.loads((Path(directory)/'checkpoint_C016.json').read_text())
            self.assertEqual(state['stage'], 'phase3_complete')
            self.assertEqual(Path(state['mp4']), source)
            still.assert_not_called()
            inject.assert_not_called()

    def test_legacy_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Legacy spatial'):
            b.verify_generative(b.FLF_DIR / 'photoreal_video_C016_00001.mp4')

    def test_metadata_cannot_hide_output_bypass(self):
        graph = b.build_tile_upscale_graph('source.mp4', 'test', 'test')
        graph['42']['inputs']['images'] = ['30', 0]
        fake = {'streams':[{'codec_type':'video','width':1280,'height':720,'nb_frames':'17','r_frame_rate':'8/1'}],
                'format':{'tags':{'prompt':b.json.dumps(graph)}}}
        with patch.object(b, 'probe', return_value=fake), self.assertRaisesRegex(ValueError, 'Broken generative path'):
            b.verify_generative(Path('fake.mp4'))

    def test_complete_checkpoint_skips_every_render(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'OUT_DIR', Path(directory)), \
             patch.object(b, 'valid_video', return_value=True), \
             patch.object(b, 'verify_generative', return_value={'sha256':'hash'}), \
             patch.object(b, 'run_phase4') as phase4, patch.object(b, '_submit_still') as still:
            b.atomic_json(Path(directory)/'checkpoint_C016.json', {'id':'C016','photoreal_mp4':'test.mp4','sha256':'hash','stage':'complete'})
            b.process_clip(SimpleNamespace(watch=Mock()), {'id':'C016'})
            phase4.assert_not_called()
            still.assert_not_called()

if __name__ == '__main__':
    unittest.main()
