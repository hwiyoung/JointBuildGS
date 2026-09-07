"""Regression for a completed training run after an older failed attempt."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
VIEWER = ROOT / 'scripts/phd/geogs_mvs_pgsr_v1/viewer'
SPEC = importlib.util.spec_from_file_location('surface_viewer_build', VIEWER / 'build.py')
builder = importlib.util.module_from_spec(SPEC)
with patch.object(sys, 'path', [str(VIEWER), str(ROOT / 'src/phd/geogs_mvs_pgsr_v1'), *sys.path]):
    SPEC.loader.exec_module(builder)


class PendingStateRegression(unittest.TestCase):
    def test_completed_run_after_failed_attempt_without_surface_is_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task, base = root / 'task', root / 'base'
            input_manifest = base / 'inputs/P1/input_manifest.json'
            input_manifest.parent.mkdir(parents=True)
            input_manifest.write_text('{}')
            failed = task / 'train/P1/mvs_0.005/attempt.a_failed'
            complete = task / 'train/P1/mvs_0.005/attempt.b_complete'
            failed.mkdir(parents=True); complete.mkdir()
            (failed / 'receipt.json').write_text(json.dumps({'status': 'FAIL'}))
            receipt = dict(status='PASS', completed=True, phase='train', final_iteration=30000,
                           region='P1', mode='mvs', prior=.005, config_sha256='config',
                           source_provenance_sha256='source', scientific_verdict=None,
                           complete_state_receipt=dict(ply_sha256='final-ply'))
            (complete / 'receipt.json').write_text(json.dumps(receipt))
            publisher = builder.Publisher.__new__(builder.Publisher)
            publisher.args = SimpleNamespace(new=task, base=base)
            publisher.experiment_sha, publisher.source_sha = 'config', 'source'
            publisher.cfg = {'runtime_image_id': 'frozen-image'}
            publisher.seal = {'candidates': [dict(region='P1', condition='D005_Pnative',
                iteration=30000, mesh_res=512, mesh_kind='raw', realized_extraction={'mesh_res': 512})]}
            with patch.object(builder, 'resolve_surface', return_value=None) as resolver:
                candidate, completed = publisher.new_candidate('P1', 'mvs', .005,
                    {'min': [0, 0, 0], 'max': [1, 1, 1]})
            resolver.assert_called_once()
            self.assertEqual(resolver.call_args.kwargs['training_relative'], str(complete.relative_to(task)))
            self.assertTrue(completed)
            self.assertEqual(candidate['status'], 'pending')
            self.assertEqual(candidate['representation_policy'], 'surface_only')
            self.assertIn('표면 추출 대기', candidate['stage'])
            self.assertNotIn('mesh', candidate)
            self.assertNotIn('points', candidate)


if __name__ == '__main__':
    unittest.main()
