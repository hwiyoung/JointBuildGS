"""Stage 2 note (CPU, read only): where did the Gaussians of B173 x LoD2 gtt_s0 grow between 12,000 and 15,000 (HEALTH_STOP at 15,000)?
Compares trainlog states (12000_pre_reset, 15000) of this run with B173 x ALS gtt_s0 on a 5 m XY grid; prints field names, totals, top cells."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
def load(stem, it):
    z = np.load(O/'runs'/stem/'gtt_s0/model/trainlog/states'/f'{it}.npz'); return {k: z[k] for k in z.files}
a = load('B173nb_b10__LoD2', '15000'); print('fields', {k: v.shape for k, v in a.items()})
xyzk = next(k for k in a if 'xyz' in k)
out = {}
for stem in ['B173nb_b10__LoD2', 'B173nb_b10__ALS']:
    for it in ['12000_pre_reset', '15000']:
        s = load(stem, it); X = s[xyzk]; out[(stem, it)] = X; print(stem, it, len(X))
X1 = out[('B173nb_b10__LoD2', '15000')]; X0 = out[('B173nb_b10__ALS', '15000')]
lo = np.minimum(X1.min(0), X0.min(0))[:2]
def grid(X): k = np.floor((X[:, :2]-lo)/5).astype(int); u, c = np.unique(k, axis=0, return_counts=True); return {tuple(x): n for x, n in zip(u, c)}
g1, g0 = grid(X1), grid(X0); d = sorted(((g1.get(k, 0)-g0.get(k, 0), k) for k in set(g1) | set(g0)), reverse=True)
tot = sum(v for v, _ in d if v > 0); print('excess LoD2-ALS at 15000:', len(X1)-len(X0), 'positive cells sum', tot)
for v, k in d[:12]:
    c = lo+np.array(k)*5+2.5; sel = (np.floor((X1[:, :2]-lo)/5).astype(int) == np.array(k)).all(1); z = X1[sel, 2]
    print(f'cell x={c[0]:.1f} y={c[1]:.1f}: LoD2 {g1.get(k,0)} ALS {g0.get(k,0)} excess {v} ({100*v/tot:.1f}%) z median {np.median(z):.1f} q05 {np.quantile(z,.05):.1f} q95 {np.quantile(z,.95):.1f}')
for k in a:
    if k != xyzk and a[k].ndim == 1 and a[k].dtype.kind in 'if' and len(a[k]) == len(X1):
        print('field', k, 'median', float(np.median(a[k])), 'q99', float(np.quantile(a[k], .99)))
