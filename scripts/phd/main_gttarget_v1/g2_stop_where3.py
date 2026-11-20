"""Stage 2 note (CPU, read only), rerun1 (seed 0, same settings): all Gaussians at 15,000 (point_cloud iteration_15000 ply) of B173 x LoD2 vs B173 x ALS gtt_s0 and FINALTRAIN B173 x LoD2:
inside / outside the scene view box, and where outside (distance from the box, height), scale."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
def ply(p):
    with open(p, 'rb') as f:
        h = b''
        while not h.endswith(b'end_header\n'): h += f.readline()
        n = int(h.split(b'element vertex ')[1].split()[0]); props = [l.split()[-1].decode() for l in h.split(b'\n') if l.startswith(b'property')]
        a = np.frombuffer(f.read(n*4*len(props)), 'f4').reshape(n, len(props))
    return {k: a[:, i] for i, k in enumerate(props)}
box = view_box('B173nb_b10'); lo, hi = np.asarray(box[0]), np.asarray(box[1]); print('box', lo, hi)
for name, p in [('GTT LoD2 rerun1', O/'runs/B173nb_b10__LoD2/gtt_s0_rerun1/model/point_cloud/iteration_15000/point_cloud.ply'),
                ('GTT LoD2', O/'runs/B173nb_b10__LoD2/gtt_s0/model/point_cloud/iteration_15000/point_cloud.ply'),
                ('GTT ALS', O/'runs/B173nb_b10__ALS/gtt_s0/model/point_cloud/iteration_15000/point_cloud.ply'),
                ('FT LoD2', FT/'runs/B173nb_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_15000/point_cloud.ply')]:
    v = ply(p); X = np.c_[v['x'], v['y'], v['z']]; inside = ((X >= lo) & (X <= hi)).all(1)
    d = np.linalg.norm(np.maximum(np.maximum(lo-X, X-hi), 0), axis=1); s = np.exp(np.c_[v['scale_0'], v['scale_1']]).max(1)
    print(f'{name}: total {len(X):,} inside {inside.sum():,} outside {(~inside).sum():,}; outside distance q50 {np.median(d[~inside]):.1f} q95 {np.quantile(d[~inside],.95):.1f} m; '
          f'z q05/q50/q95 outside {np.quantile(X[~inside,2],[.05,.5,.95]).round(1)}; scale q50 inside {np.median(s[inside]):.3f} outside {np.median(s[~inside]):.3f}')
    for r in [(0, 10), (10, 50), (50, 200), (200, 1e9)]:
        m = (~inside) & (d >= r[0]) & (d < r[1]); print(f'   outside {r[0]}-{r[1]} m: {m.sum():,}')
    g = np.floor(X[~inside, :2]/50).astype(int); u, c = np.unique(g, axis=0, return_counts=True); o = np.argsort(-c)[:5]
    print('   top 50 m cells outside:', [(tuple((u[i]*50+25).tolist()), int(c[i])) for i in o])
