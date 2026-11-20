"""Stage 2 note (CPU, read only): Gaussians alive at 15,000 born after the 12,000 opacity reset, B173 scenes:
inside/outside the scene view box, birth kind, origin (seed kind), and the distance band; plus alive-at-12000 counts."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
box = view_box('B173nb_b10'); lo, hi = np.asarray(box[0]), np.asarray(box[1])
for name in ['B173nb_b10__LoD2/gtt_s0_rerun1', 'B173nb_b10__LoD2/gtt_s0', 'B173nb_b10__ALS/gtt_s0']:
    T = O/'runs'/name/'model/trainlog/states'
    s = np.load(T/'15000.npz'); s12 = np.load(T/'12000_pre_reset.npz')
    X = s['xyz']; inside = ((X >= lo) & (X <= hi)).all(1); d = np.linalg.norm(np.maximum(np.maximum(lo-X, X-hi), 0), axis=1)
    b = s['born_at']; new = b > 12000; X12 = s12['xyz']; in12 = ((X12 >= lo) & (X12 <= hi)).all(1)
    print(f'{name}: alive 12000 {len(X12):,} (in {in12.sum():,} out {(~in12).sum():,}); alive 15000 {len(X):,} (in {inside.sum():,} out {(~inside).sum():,}); born>12000 {new.sum():,} in {(new&inside).sum():,} out {(new&~inside).sum():,}')
    for r in [(0, 50), (50, 200), (200, 1e9)]:
        m = new & ~inside & (d >= r[0]) & (d < r[1]); print(f'   born>12000 outside {r[0]}-{r[1]} m: {m.sum():,}')
    for k in ['born_how', 'origin']:
        u, c = np.unique(s[k][new & ~inside], return_counts=True); print(f'   born>12000 outside by {k}:', dict(zip(u.tolist(), c.tolist())))
    for a, bb in [(12000, 13000), (13000, 14000), (14000, 15001)]:
        m = (b > a) & (b <= bb); print(f'   born ({a},{bb}]: {m.sum():,} outside {(m & ~inside).sum():,}')
    sc = np.exp(s['scale'][:, :2]).max(1) if s['scale'].min() < 0 else s['scale'][:, :2].max(1)
    print(f'   scale q50 born>12000 outside {np.median(sc[new&~inside]):.2f} m, older outside {np.median(sc[~new&~inside]):.2f} m')
