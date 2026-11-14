"""CPU helpers: crop a trained Gaussian PLY to an evaluation box (same inclusive test as render_model), and
merge the four cell models of a prior keeping Gaussians inside their original (unexpanded) cell.

  python tu_postcpu.py crop <ply> <site> <out>
  python tu_postcpu.py merge <prior> [cellsef]     (cellsef: addendum 14 filter cells under runs/ef)
"""
import sys

from plyfile import PlyData, PlyElement

from tu_common import *

G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'


def write(path, data, comments=()):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp.ply')
    PlyData([PlyElement.describe(data, 'vertex')], text=False).write(str(tmp))
    tmp.rename(path)


def crop(ply, site, out):
    box = np.array(json.loads((G / 'views' / f'{site}.json').read_text())['box'], np.float32)
    v = PlyData.read(str(ply))['vertex'].data
    xyz = np.c_[v['x'], v['y'], v['z']].astype(np.float32)
    inside = ((xyz >= box[0]) & (xyz <= box[1])).all(1)
    write(out, v[inside])
    dump(Path(out).with_suffix('.json'), dict(at=now(), source=str(ply), source_sha256=sha(ply), site=site, box=box.tolist(), total=len(v),
         kept=int(inside.sum()), rule='render_model inclusive box test, float32', output_sha256=sha(out), scientific_verdict=None))
    print('CROP', site, len(v), int(inside.sum()), flush=True)


def merge(prior, kind='cells'):
    cells = json.loads((TU / 'cells/cells.json').read_text())['cells']
    assert kind in ('cells', 'cellsef', 'cellsef1fix')
    parts = []
    rec = []
    for c in cells:
        run = TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{c["id"]}' if kind == 'cells' else TU / 'runs/ef' / f'cellsef_{prior}_s0_cell{c["id"]}'
        if kind == 'cellsef1fix' and c['id'] == 1:
            run = TU / 'runs/ef' / f'cellsef_{prior}_s0_cell1fix'   # addendum 17: cell 1 with the fixed scene radius
        r = json.loads((run / 'receipt.json').read_text())
        assert r['status'] == 'TRAINING_COMPLETE'
        ply = run / f'attempt{r["attempts"][-1]["attempt"]}' / 'model/point_cloud/iteration_30000/point_cloud.ply'
        v = PlyData.read(str(ply))['vertex'].data
        lo, hi = np.array(c['original_min'], float), np.array(c['original_max'], float)
        x, y = v['x'].astype(float), v['y'].astype(float)
        keep = (x >= lo[0]) & (x < hi[0]) & (y >= lo[1]) & (y < hi[1])
        parts.append(v[keep])
        rec.append(dict(cell=c['id'], ply=str(ply), sha256=sha(ply), total=len(v), kept=int(keep.sum())))
    data = np.concatenate(parts)
    out = TU / ('runs/cells' if kind == 'cells' else 'runs/ef') / f'{kind}_{prior}_s0' / 'merged/point_cloud.ply'
    write(out, data)
    dump(out.with_suffix('.json'), dict(at=now(), prior=prior, cells=rec, merged=len(data), output_sha256=sha(out),
         rule='keep xy in original cell [min, max); concatenate', scientific_verdict=None))
    print('MERGED', prior, len(data), flush=True)


if __name__ == '__main__':
    dict(crop=crop, merge=merge)[sys.argv[1]](*sys.argv[2:])
