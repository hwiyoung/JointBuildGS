"""Probe: horizontal registration between the sources, per 80 m tile.

For integer cell shifts (dx, dy) in [-3, 3] m (0.5 m steps), the median
|ULS(x) - S(x - shift)| over building-edge cells (|grad S| > 1, not vegetation,
|ULS - S| < 5 m to drop real change) is computed per tile; the minimising shift is
reported.  S = ALS 2022 DSM, LoD2 roof surface, MVS 2024 DSM.  Positive dx = S must
move east to match ULS.  Grid resolution limits the answer to 0.5 m.
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
D = dict(np.load(out / 'derived.npz'))
g = cfg['grid']; res = g['res_m']
uls = D['uls'].astype(float)
veg = D['veg'] > 0.3
ny, nx = uls.shape
T = int(80 / res)
shifts = range(-6, 7)
result = {}
for name in ('als', 'lod', 'mvs'):
    S = D[name].astype(float)
    if name == 'lod':
        S = np.where(np.isfinite(S), S, D['dtm'].astype(float))
    gy, gx = np.gradient(np.nan_to_num(S, nan=0.0), res)
    edge = (np.hypot(gx, gy) > 1.0) & ~veg & np.isfinite(uls) & np.isfinite(S)
    best = {}
    tiles = [(ty, tx) for ty in range(0, ny - T + 1, T) for tx in range(0, nx - T + 1, T)
             if edge[ty:ty + T, tx:tx + T].sum() >= 400]
    scores = {t: {} for t in tiles}
    for dy in shifts:
        for dx in shifts:
            Ss = np.roll(np.roll(S, dy, axis=0), dx, axis=1)
            d = np.abs(uls - Ss)
            for (ty, tx) in tiles:
                dd = d[ty:ty + T, tx:tx + T]
                m = edge[ty:ty + T, tx:tx + T] & np.isfinite(dd) & (dd < 5.0)
                if m.sum() >= 200:
                    scores[(ty, tx)][(dx, dy)] = float(np.median(dd[m]))
    for (ty, tx), sc in scores.items():
        if not sc:
            continue
        k = min(sc, key=sc.get)
        e0 = g['e_min'] + (tx + T / 2) * res; n0 = g['n_min'] + (ty + T / 2) * res
        best['%d_%d' % (int(e0), int(n0))] = dict(e=e0, n=n0, dx_m=k[0] * res, dy_m=k[1] * res, med_at_best=round(sc[k], 3),
                                                 med_at_zero=round(sc.get((0, 0), np.nan), 3), edge_cells=int(edge[ty:ty + T, tx:tx + T].sum()))
    result[name] = best
    vals = np.array([[v['dx_m'], v['dy_m']] for v in best.values()])
    print(name, 'tiles', len(best), 'shift dx median %.2f dy median %.2f' % tuple(np.median(vals, axis=0)))
    for k, v in sorted(best.items(), key=lambda kv: (kv[1]['n'], kv[1]['e'])):
        print('  %s dx %+.1f dy %+.1f  med best %.3f zero %.3f  n %d' % (k, v['dx_m'], v['dy_m'], v['med_at_best'], v['med_at_zero'], v['edge_cells']))
(out / 'qa' / 'horizontal_shift_probe.json').write_text(json.dumps(result, indent=1))
