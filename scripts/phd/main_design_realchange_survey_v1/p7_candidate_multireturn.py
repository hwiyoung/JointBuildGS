"""Probe: ALS 2022 multi-return share and class mix inside each candidate component, to tell
solid structures (roofs: few multi-returns) from tree crowns (many).  Same component masks as
s6.  scientific_verdict: null."""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
D = dict(np.load(out / 'derived.npz')); A = dict(np.load(out / 's1' / 'rasters_als_mvs_uls.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
EE, NN = np.meshgrid(ec, nc); pts = np.column_stack([EE.ravel(), NN.ravel()])
dtm = D['dtm'].astype(float)
nd = {k: D[k].astype(float) - dtm for k in ('uls', 'als')}
fid = D['fid']
nd['lod'] = np.where(np.isfinite(D['lod']), D['lod'].astype(float) - dtm, np.where(fid >= 0, np.nan, 0.0))
tv = {r['tid']: r for r in json.loads((out / 'targets_views.json').read_text())}
res_ = {}
for r in csv.DictReader(open(out / 'candidates.csv')):
    t = tv[r['tid']]
    inside = MPath(np.array(t['poly'])).contains_points(pts).reshape(ny, nx)
    if r['tid'] == 'R1_Z08':
        m = inside & (nd['als'] > 2.5) & (nd['uls'] < 1.0)
    else:
        prior = 'als' if r['screen_prior'] == 'ALS' else 'lod'
        d = nd['uls'] - nd[prior]
        sign = -1 if float(r['d_uls_als' if prior == 'als' else 'd_uls_lod2']) < 0 else 1
        m = inside & np.isfinite(d) & (np.abs(d) > 2.5) & (np.sign(d) == sign)
    n = A['als_n'][m].sum()
    un = A['uls_n'][m].sum()
    res_[r['tid']] = dict(als_multi=round(float(A['als_n_multi'][m].sum() / max(n, 1)), 3), als_c6=round(float(A['als_n_c6'][m].sum() / max(n, 1)), 3),
                          als_c20=round(float(A['als_n_c20'][m].sum() / max(n, 1)), 3), uls_multi=round(float(A['uls_n_multi'][m].sum() / max(un, 1)), 3),
                          cat=r['category'])
    print(r['tid'], res_[r['tid']])
(out / 'qa' / 'candidate_multireturn.json').write_text(json.dumps(res_, indent=1))
