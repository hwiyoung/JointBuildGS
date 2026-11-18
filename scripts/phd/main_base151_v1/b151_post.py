"""PHD-MAIN-BASE151-v1 CPU post steps (jointbuildgs:dev; run_cpu.sh).

  python b151_post.py merge <run>                 # OUT/runs/<run>/merged/point_cloud.ply (+ .json)
  python b151_post.py crop <ply> <box_json> <out>   # Gaussians inside an evaluation box (render_model's inclusive float32 test)
Merge rule (config merge = TRAINUNIT tu_postcpu.merge): keep Gaussians whose xy is in the original cell [min, max) and concatenate the
four iteration-30000 point_cloud.ply files of the cells' final attempts. scientific_verdict: null
"""
import sys

import numpy as np
from plyfile import PlyData, PlyElement

from b151_common import *


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp.ply')
    PlyData([PlyElement.describe(data, 'vertex')], text=False).write(str(tmp))
    tmp.rename(path)


def final_ply(run, k):
    rec = json.loads((B / 'runs' / run / f'cell{k}' / 'receipt.json').read_text())
    assert rec['status'] == 'TRAINING_COMPLETE', (run, k, rec['status'])
    a = rec['attempts'][-1]['attempt']
    return B / 'runs' / run / f'cell{k}' / f'attempt{a}' / 'model/point_cloud/iteration_30000/point_cloud.ply'


def merge(run):
    c = cfg()
    parts, rec = [], []
    for cell in c['cells']['per_cell']:
        ply = final_ply(run, cell['id'])
        v = PlyData.read(str(ply))['vertex'].data
        lo, hi = np.array(cell['original_min'], float), np.array(cell['original_max'], float)
        x, y = v['x'].astype(float), v['y'].astype(float)
        keep = (x >= lo[0]) & (x < hi[0]) & (y >= lo[1]) & (y < hi[1])
        parts.append(v[keep])
        rec.append(dict(cell=cell['id'], ply=str(ply), sha256=sha(ply), total=int(len(v)), kept=int(keep.sum())))
    assert len({p.dtype for p in parts}) == 1, 'cells have different PLY fields'
    data = np.concatenate(parts)
    out = B / 'runs' / run / 'merged/point_cloud.ply'
    write(out, data)
    dump(out.with_suffix('.json'), dict(at=now(), run=run, cells=rec, merged=int(len(data)), output_sha256=sha(out),
                                        rule='keep xy in original cell [min, max); concatenate (TRAINUNIT tu_postcpu.merge)', scientific_verdict=None))
    print('MERGED', run, len(data), flush=True)


def crop(ply, box_json, out):
    box = np.array(json.loads(Path(box_json).read_text())['box'], np.float32)
    v = PlyData.read(str(ply))['vertex'].data
    xyz = np.c_[v['x'], v['y'], v['z']].astype(np.float32)
    inside = ((xyz >= box[0]) & (xyz <= box[1])).all(1)
    write(out, v[inside])
    dump(Path(out).with_suffix('.json'), dict(at=now(), source=str(ply), source_sha256=sha(ply), box_source=str(box_json), box=box.tolist(),
                                              total=int(len(v)), kept=int(inside.sum()), rule='render_model inclusive box test, float32 (tu_postcpu.crop)',
                                              output_sha256=sha(out), scientific_verdict=None))
    print('CROP', out, len(v), int(inside.sum()), flush=True)


if __name__ == '__main__':
    dict(merge=merge, crop=crop)[sys.argv[1]](*sys.argv[2:])
