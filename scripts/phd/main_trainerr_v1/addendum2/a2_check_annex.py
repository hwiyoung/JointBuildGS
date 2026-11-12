"""Addendum 2 check (read-only): Gaussian count, opacity and size in the annex_under box (B0_b10__ALS, both arms), and how many discs reach the under-roof points."""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum2')
from a2_common import *
c = bcfg(); bx = c['places']['annex_under']
for arm in ARMS:
    S = Snap('B0_b10__ALS', arm); x = S.xyz; m = (x[:, 0] >= bx['x'][0]) & (x[:, 0] <= bx['x'][1]) & (x[:, 1] >= bx['y'][0]) & (x[:, 1] <= bx['y'][1]) & (x[:, 2] >= -46) & (x[:, 2] <= -30)
    print(arm, 'box gaussians', int(m.sum()), 'opacity>=0.1', int((m & (S.opacity >= .1)).sum()), 'size q', np.percentile(S.size[m], [10, 50, 90]).round(2) if m.any() else None, 'z q', np.percentile(x[m, 2], [10, 50, 90]).round(2) if m.any() else None,
          'tags', np.unique(S.tag[m], return_counts=True))
    z = loadz(A2O/'points'/f'na_{arm}.npz'); P = z['annex_under__spot'].astype('f8')
    for r in [0.2, 0.5, 1.0, 2.0]:
        q = S.tree.query_ball_point(P, r, workers=8); print('  radius', r, 'spots with >=1 centre', float(np.mean([len(a) > 0 for a in q])))
