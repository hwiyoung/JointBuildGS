"""PHD-MAIN-BASE151-v1 2.2: training scenes of the four TRAINUNIT cells per method (jointbuildgs:dev, CPU; run_cpu.sh).

  python b151_scenes.py 2dgs            # /b151/scenes/2DGS/cell<k>/
2DGS (SB twodgs/prep_scenes_2dgs.py rule, the cell instead of the site box):
  sparse/0/cameras.bin, images.bin   byte copies of TU1 scenes/cell<k>/scene_ALS/sparse/0 (the cell's train + test views)
  sparse/0/points3D.ply              ONLY the origin-0 rows of TU1 scenes/cell<k>/scene_ALS/sparse/0/points3D.ply (the SfM points of the
                                     expanded cell; same fields and types); checked equal to the origin-0 rows of scene_LoD2
  jbgs_calibration.json              byte copy (principal-point adapter)
  split.json                         byte copy of TU1 scenes/cell<k>/split.json (JBGS_SPLIT_JSON)
  images                             not written: the training mounts TU1 scenes/campus/images at /scene/images (read-only)
Receipt /b151/scenes/2DGS/cell<k>/scene_receipt.json. scientific_verdict: null
"""
import os
import shutil
import sys

import numpy as np
from plyfile import PlyData, PlyElement

from b151_common import *


def two_dgs():
    c = cfg()
    out_all = []
    for cell in c['cells']['per_cell']:
        k = cell['id']
        src = TU1 / 'scenes' / f'cell{k}'
        dst = B / 'scenes/2DGS' / f'cell{k}'
        (dst / 'sparse/0').mkdir(parents=True, exist_ok=True)
        for n in ['cameras.bin', 'images.bin']:
            shutil.copyfile(src / 'scene_ALS/sparse/0' / n, dst / 'sparse/0' / n)
            assert sha(dst / 'sparse/0' / n) == cell['sparse'][n]['sha256']
        shutil.copyfile(src / 'scene_ALS/jbgs_calibration.json', dst / 'jbgs_calibration.json')
        shutil.copyfile(src / 'split.json', dst / 'split.json')
        assert sha(dst / 'split.json') == cell['split']['sha256']
        rows = {}
        total = {}
        for prior in ['ALS', 'LoD2']:
            v = PlyData.read(str(src / f'scene_{prior}/sparse/0/points3D.ply'))['vertex'].data
            o = np.load(src / f'scene_{prior}/sparse/0/origin.npy')
            assert len(o) == len(v)
            rows[prior] = v[o == 0]
            total[prior] = int(len(v))
        a, b = rows['ALS'], rows['LoD2']
        same = len(a) == len(b) and all(np.array_equal(a[n], b[n]) for n in a.dtype.names)
        assert same, f'cell{k}: origin-0 rows differ between scene_ALS and scene_LoD2'
        PlyData([PlyElement.describe(a, 'vertex')], text=False, byte_order='<').write(str(dst / 'sparse/0/points3D.ply'))
        back = PlyData.read(str(dst / 'sparse/0/points3D.ply'))['vertex'].data
        assert len(back) == len(a) and all(np.array_equal(back[n], a[n]) for n in a.dtype.names)
        split = json.loads((dst / 'split.json').read_text())
        rec = dict(at=now(), cell=k, method='2DGS', train_views=len(split['train']), test_views=len(split['test']),
                   initial_points=int(len(a)), fields=list(a.dtype.names), prior_rows_dropped_ALS=total['ALS'] - int(len(a)), prior_rows_dropped_LoD2=total['LoD2'] - int(len(a)),
                   origin0_equal_ALS_LoD2=bool(same),
                   files={n: sha(dst / 'sparse/0' / n) for n in ['cameras.bin', 'images.bin', 'points3D.ply']},
                   calibration_sha256=sha(dst / 'jbgs_calibration.json'), split_sha256=sha(dst / 'split.json'),
                   images='TU1 scenes/campus/images mounted read-only at /scene/images',
                   rule='SB twodgs/prep_scenes_2dgs.py rule (origin-0 rows only) on the TRAINUNIT cell scene', scientific_verdict=None)
        dump(dst / 'scene_receipt.json', rec)
        out_all.append(rec)
        print('SCENE_2DGS', k, rec['train_views'], rec['test_views'], rec['initial_points'], flush=True)
    dump(B / 'scenes/2DGS/scenes.json', dict(at=now(), cells=out_all, scientific_verdict=None))


if __name__ == '__main__':
    dict(**{'2dgs': two_dgs})[sys.argv[1]]()
