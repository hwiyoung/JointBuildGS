"""PHD-MAIN-BASE151-v1 read-only check: why sample_normals keeps no triangle for one unit mesh (b151_score151.unit inputs).

  python b151_diag_empty.py <unit> <prior> <run> [<run> ...]   -> prints counts, writes nothing.
scientific_verdict: null
"""
import sys

import numpy as np

sys.path.insert(0, '/b151s')
import b151_score151 as S  # noqa: E402
import b151_common as BC  # noqa: E402

uname, prior, *runs = sys.argv[1:]
S.gt_cfg(); BC.cfg('score151')
u = S.layout()[uname]
g = np.load(BC.B / 'gt' / f'gt151_{prior}.npz')
grid = S.CampusGrid(g['xyz'])
lo, hi = np.array(u['rect_min']), np.array(u['rect_max'])
inr = (g['xyz'][:, :2] >= lo).all(1) & (g['xyz'][:, :2] <= hi).all(1)
print('unit', uname, 'rect', lo.tolist(), hi.tolist(), 'gt_rows_in_rect', int(inr.sum()), 'grid_cells', len(grid.keys))
for run in runs:
    P_ = 'ALS' if run.split('_')[1] == '2DGS' else run.split('_')[2]
    mesh = S.O / 'meshes' / f'{uname}__{P_}__{run}' / 'final.ply'
    V, F = S.read_surface(mesh)
    if len(F) == 0:
        print(run, 'V', V.shape, 'F', F.shape); continue
    tri = V[F]; c = tri.mean(1)
    a = .5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    print(run, 'V', V.shape, V.dtype, 'F', F.shape, F.dtype, 'Fmax', int(F.max()), 'nan_V', int(np.isnan(V).any(1).sum()),
          'centroid_in_cells', int(grid.in_cells(c).sum()), 'area>0.01', int((a > .01).sum()), 'area_sum', float(a.sum()),
          'centroid_q', np.percentile(c, [0, 50, 100], axis=0).round(1).tolist())
