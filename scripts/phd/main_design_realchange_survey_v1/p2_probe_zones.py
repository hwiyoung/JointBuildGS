"""Probe: height statistics inside given polygons (R1 Z08 and change components).
Reads derived grids only.  Prints numbers for the report.  scientific_verdict: null."""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
D = dict(np.load(out / 'derived.npz'))
A = dict(np.load(out / 's1' / 'rasters_als_mvs_uls.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
EE, NN = np.meshgrid(ec, nc)
pts = np.column_stack([EE.ravel(), NN.ravel()])
z08 = [[690916.7665713681, 5336041.620778608], [690932.4994979611, 5336084.846639165], [690977.6047437588, 5336068.429672285], [690961.8718171659, 5336025.203811728]]
polys = {'R1_Z08': z08}
for r in csv.DictReader(open(out / 'change_components.csv')):
    pass
dtm = D['dtm'].astype(float)


def report(name, poly):
    m = MPath(np.array(poly)).contains_points(pts).reshape(ny, nx)
    a = m.sum() * res * res
    h = {k: D[k].astype(float) - dtm for k in ('als', 'uls', 'mvs')}
    hl = np.where(np.isfinite(D['lod']), D['lod'].astype(float) - dtm, 0.0)
    print('==', name, 'area %.0f m2' % a)
    for k in ('als', 'uls', 'mvs'):
        x = h[k][m]; x = x[np.isfinite(x)]
        print('  h_%s: med %.2f p90 %.2f  frac>2.5 %.3f  area>2.5 %.0f m2' % (k, np.median(x), np.quantile(x, .9), (x > 2.5).mean(), (x > 2.5).sum() * res * res))
    print('  LoD2 roof present frac %.3f, LoD2 footprint frac %.3f' % (np.isfinite(D['lod'][m]).mean(), (D['fid'][m] >= 0).mean()))
    n = A['als_n'][m].sum();
    print('  ALS points %d: c2 %.3f c6 %.3f c20 %.3f other %.3f; multi-return %.3f' % (n, A['als_n_c2'][m].sum() / n, A['als_n_c6'][m].sum() / n, A['als_n_c20'][m].sum() / n, A['als_n_other'][m].sum() / n, A['als_n_multi'][m].sum() / n))
    sel = m & (h['als'] > 2.5)
    if sel.sum():
        n2 = A['als_n'][sel].sum()
        print('  cells with ALS h>2.5 (%.0f m2): ALS c6 %.3f c20 %.3f; ULS h med %.2f; MVS h med %.2f; ALS h med %.2f; ULS multi %.3f' % (
            sel.sum() * res * res, A['als_n_c6'][sel].sum() / n2, A['als_n_c20'][sel].sum() / n2, np.nanmedian(h['uls'][sel]), np.nanmedian(h['mvs'][sel]),
            np.nanmedian(h['als'][sel]), np.nanmean(D['veg'][sel])))
        both = sel & (h['uls'] < 1.0)
        print('    of which ULS h<1.0 (now ground): %.0f m2' % (both.sum() * res * res))


report('R1_Z08', z08)
extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
for k, v in extra.items():
    report(k, v)
