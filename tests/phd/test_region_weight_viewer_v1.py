"""Two same-split source cameras and independent per-condition publication."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/phd/geogs_mvs_pgsr_v1/viewer'))
spec=importlib.util.spec_from_file_location('regional_viewer',REPO/'scripts/phd/region_weight_v1/viewer_publish.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class RegionalViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        v.ROOT,v.EXP,v.INPUT=[root/p for p in ('viewer','experiment','input')]
        for p in [v.ROOT,v.EXP,v.INPUT/'scene/images']:p.mkdir(parents=True)
        v.VIEWS=[('source_b','train','B.JPG'),('source_a','train','A.JPG')]
        self.photos={name:np.full((12,12,3),level,np.uint8) for name,level in [('A.JPG',20),('B.JPG',200)]}
        for name,photo in self.photos.items():Image.fromarray(photo).save(v.INPUT/'scene/images'/name,format='PNG')
        v.write(v.INPUT/'scene/split_manifest_da3_v2.json',dict(train=[dict(name=n) for n in self.photos],evaluation=[]))
        (v.EXP/'status.txt').write_text('TRAINING_ALPHA_1')
        self.cfg=dict(region='P2',task_id='test',config_sha256='config',mask_sha256='mask',url_prefix='/data/test/',point_cap=32,
            depth_range_m=[50,85],expected_extraction={'mesh_res':512},regions=[dict(id='P2',label='P2',bounds=dict(min=[-20,-20,-50],max=[20,20,0]))])

    def extraction(self,alpha):
        v.write(v.EXP/'train'/f'alpha_{alpha}'/'receipt.json',dict(status='PASS',completed=True,phase='train',alpha=alpha,region='P2',
            final_iteration=30000,config_sha256='config',mask_sha256='mask',fixed_visual_weight=.05,scientific_verdict=None,started_unix=1,wall_seconds=10))
        folder=v.ROOT/f'alpha_{alpha}'/'extraction';model=folder/'model';model.mkdir(parents=True)
        (model/'cfg_args').write_text('fixture')
        mesh=model/'surface.ply';mesh.write_text('ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n-10 -10 -42 255 0 0\n-5 -10 -42 0 255 0\n-10 -5 -42 0 0 255\n3 0 1 2\n')
        job=dict(alpha=alpha,training_receipt_sha256=v.sha(v.EXP/'train'/f'alpha_{alpha}'/'receipt.json'),staged_cfg_sha256=v.sha(model/'cfg_args'))
        v.write(folder/'job.json',job);v.write(folder/'receipt.json',dict(status='PASS',job=job,realized_extraction=self.cfg['expected_extraction'],surfaces={'raw':dict(path='model/surface.ply',sha256=v.sha(mesh))}))
        base=model/'train/ours_30000'
        for child in ['renders','gt','vis']:(base/child).mkdir(parents=True)
        for i,name in enumerate(sorted(self.photos)):
            Image.fromarray(self.photos[name]).save(base/'renders'/f'{i:05d}.png')
            Image.fromarray(self.photos[name]).save(base/'gt'/f'{i:05d}.png')
            Image.fromarray(np.full((12,12),60+i,np.float32)).save(base/'vis'/f'depth_{i:05d}.tiff')

    def test_two_train_views_have_distinct_correct_renders_and_pending_arms(self):
        self.extraction(0);v.publish(self.cfg,0)
        receipt=v.read(v.ROOT/'alpha_0/publication.json');self.assertEqual(set(receipt['views']),{'source_a','source_b'})
        a,b=[receipt['views'][k] for k in ['source_a','source_b']]
        self.assertNotEqual(a['rgb']['sha256'],b['rgb']['sha256'])
        self.assertTrue(a['rgb']['url'].endswith('00000.png'));self.assertTrue(b['rgb']['url'].endswith('00001.png'))
        before=(v.ROOT/'alpha_0/publication.json').read_bytes()
        self.extraction(4);v.publish(self.cfg,4)
        self.assertEqual((v.ROOT/'alpha_0/publication.json').read_bytes(),before)
        manifest=v.read(v.ROOT/'manifest.json')
        self.assertEqual(manifest['run_status']['completed'],2)
        self.assertEqual([r['status'] for r in manifest['regions'][0]['conditions']],['available','pending','available'])

    def test_wrong_region_is_rejected(self):
        self.extraction(0);receipt=v.read(v.EXP/'train/alpha_0/receipt.json');receipt['region']='P3'
        with self.assertRaises(ValueError):v.validate_training(receipt,self.cfg,0)


if __name__=='__main__':unittest.main()
