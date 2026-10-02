"""Probe: removals hidden by the vegetation rule.  The s3 screen drops cells whose ALS points
are mostly class 20 without class 6; R1 Z08 was such a structure.  Here: cells with ALS height
above ground > 2.5 m, current ULS height < 1.0 m (now ground), ALS class-20 share > 0.5 and no
class 6, grouped into components >= 25 m2.  Trees cut down also appear; each component is
listed with its ALS multi-return share (trees high, solid roofs low) for visual follow-up.
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
D = dict(np.load(out / 'derived.npz')); A = dict(np.load(out / 's1' / 'rasters_als_mvs_uls.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
dtm = D['dtm'].astype(float)
h_als = D['als'].astype(float) - dtm; h_uls = D['uls'].astype(float) - dtm; h_mvs = D['mvs'].astype(float) - dtm
c20 = (D['als_veg'] > 0.5) & (D['als_n_c6'] == 0)
m = (h_als > 2.5) & (h_uls < 1.0) & c20 & D['in_dom'] & np.isfinite(h_uls)
m = ndi.binary_opening(m, iterations=1)
lab, k = ndi.label(m, structure=np.ones((3, 3)))
sizes = ndi.sum(np.ones(m.shape), lab, index=np.arange(1, k + 1)) * res * res
multi = np.where(A['als_n'] > 0, A['als_n_multi'] / np.maximum(A['als_n'], 1), np.nan)
B = np.array([[np.cos(np.deg2rad(70)), np.sin(np.deg2rad(70))], [np.sin(np.deg2rad(70)), -np.cos(np.deg2rad(70))]])
rows = []
for j in np.argsort(-sizes):
    if sizes[j] < 25:
        break
    sel = lab == j + 1
    yy, xx = np.nonzero(sel)
    e, n = float(ec[int(xx.mean())]), float(nc[int(yy.mean())])
    uv = (np.array([e, n]) - [690953.0, 5336071.0]) @ B.T
    # planarity proxy of the 2022 surface: std of ALS DSM inside the component
    rows.append(dict(area_m2=round(float(sizes[j]), 1), e=round(e, 1), n=round(n, 1), u=round(float(uv[0]), 1), v=round(float(uv[1]), 1),
                     h_als_med=round(float(np.nanmedian(h_als[sel])), 2), h_uls_med=round(float(np.nanmedian(h_uls[sel])), 2),
                     h_mvs_med=round(float(np.nanmedian(h_mvs[sel])), 2), als_multireturn=round(float(np.nanmean(multi[sel])), 3),
                     als_dsm_std=round(float(np.nanstd(D['als'][sel])), 2), lod2_share=round(float((D['fid'][sel] >= 0).mean()), 2)))
for r in rows:
    print(r)
(out / 'qa' / 'masked_removals.json').write_text(json.dumps(rows, indent=1))
