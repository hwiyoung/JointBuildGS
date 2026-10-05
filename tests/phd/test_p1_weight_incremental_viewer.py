"""Display correctness: out-of-order finals, missing arms, and frozen identities."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts/phd/geogs_mvs_pgsr_v1/viewer'))
spec = importlib.util.spec_from_file_location('p1viewer', REPO / 'scripts/phd/p1_single_view_weight_v1/viewer_publish.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class IncrementalViewer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        v.ROOT, v.EXP, v.INPUT = [root / s for s in ['display', 'experiment', 'input']]
        for p in [v.ROOT, v.EXP, v.INPUT / 'scene/images']:
            p.mkdir(parents=True)
        (v.EXP / 'status.txt').write_text('TRAINING_ALPHA_0_1')
        self.cfg = json.loads((REPO / 'configs/phd/p1_single_view_weight_v1/viewer_v1.json').read_text())
        self.cfg['point_cap'] = 32
        self.photo = np.arange(12*12*3, dtype=np.uint8).reshape(12, 12, 3)
        for role, name in v.VIEWS:
            Image.fromarray(self.photo).save(v.INPUT / 'scene/images' / name, format='PNG')
        v.write(v.INPUT / 'scene/split_manifest_da3_v2.json', {role:[{'name': name}] for role, name in v.VIEWS})

    def training(self, alpha, finished=100):
        value = dict(status='PASS', completed=True, phase='train', alpha=alpha,
                     final_iteration=30000, config_sha256=self.cfg['config_sha256'],
                     mask_sha256=self.cfg['mask_sha256'], fixed_visual_weight=.05,
                     scientific_verdict=None, started_unix=finished-10, wall_seconds=10)
        v.write(v.EXP / 'train' / f'alpha_{alpha}' / 'receipt.json', value)
        return value

    def extraction(self, alpha):
        self.training(alpha)
        folder = v.ROOT / f'alpha_{alpha}' / 'extraction'
        model = folder / 'model'
        model.mkdir(parents=True)
        (model / 'cfg_args').write_text('fixture only')
        mesh = model / 'surface.ply'
        mesh.write_text('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n-10 -10 -42 255 0 0\n-5 -10 -42 0 255 0\n-10 -5 -42 0 0 255\n3 0 1 2\n')
        job = dict(alpha=alpha, training_receipt_sha256=v.sha(v.EXP / 'train' / f'alpha_{alpha}' / 'receipt.json'),
                   staged_cfg_sha256=v.sha(model / 'cfg_args'))
        v.write(folder / 'job.json', job)
        v.write(folder / 'receipt.json', dict(status='PASS', job=job,
                realized_extraction=self.cfg['expected_extraction'],
                surfaces={'raw': {'path':'model/surface.ply', 'sha256':v.sha(mesh)}}))
        for sub in ['train', 'test']:
            base = model / sub / 'ours_30000'
            for name in ['renders', 'gt', 'vis']:
                (base / name).mkdir(parents=True)
            Image.fromarray(self.photo).save(base / 'renders/00000.png')
            Image.fromarray(self.photo).save(base / 'gt/00000.png')
            Image.fromarray(np.full((12, 12), 60, dtype=np.float32)).save(base / 'vis/depth_00000.tiff')
        return folder

    def test_each_final_is_published_without_waiting_for_other_arms(self):
        self.extraction(4)
        v.publish(self.cfg, 4)
        manifest = v.read(v.ROOT / 'manifest.json')
        self.assertEqual(manifest['run_status']['completed'], 1)
        for region in manifest['regions']:
            self.assertEqual([c['status'] for c in region['conditions']], ['pending','pending','available'])
            self.assertEqual(region['conditions'][2]['provenance']['checkpoint_iteration'], 30000)
            self.assertGreater(region['conditions'][2]['mesh']['triangle_count'], 0)
            for view in region['views']:
                self.assertEqual(view['conditions']['alpha_0']['status'], 'pending')
                self.assertEqual(view['conditions']['alpha_4']['status'], 'available')
                self.assertEqual(view['depth_range_m'], [50,85])
        original = (v.ROOT / 'alpha_4/publication.json').read_bytes()
        self.extraction(0)
        v.publish(self.cfg, 0)
        self.assertEqual((v.ROOT / 'alpha_4/publication.json').read_bytes(), original)
        self.assertEqual(v.read(v.ROOT / 'manifest.json')['run_status']['completed'], 2)

    def test_completion_order_not_numeric_alpha_order(self):
        self.training(0, finished=200)
        self.training(1, finished=100)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            v.next_alpha(self.cfg)
        self.assertEqual(capture.getvalue().strip(), '1')

    def test_nonfinal_wrong_mask_and_wrong_arm_are_rejected(self):
        good = self.training(0)
        for field, value in [('final_iteration', 8200), ('mask_sha256', 'wrong'), ('alpha', 4), ('completed', False)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.validate_training(dict(good, **{field: value}), self.cfg, 0)

    def test_parameter_mismatch_never_becomes_available(self):
        folder = self.extraction(0)
        receipt = v.read(folder / 'receipt.json')
        receipt['realized_extraction']['mesh_res'] = 1024
        (folder / 'receipt.json').write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            v.publish(self.cfg, 0)
        self.assertFalse((v.ROOT / 'alpha_0/publication.json').exists())

    def test_corrupted_surface_never_becomes_available(self):
        folder = self.extraction(0)
        with (folder / 'model/surface.ply').open('a') as f:
            f.write('corrupted')
        with self.assertRaises(ValueError):
            v.publish(self.cfg, 0)
        self.assertFalse((v.ROOT / 'alpha_0/publication.json').exists())


if __name__ == '__main__':
    unittest.main()
