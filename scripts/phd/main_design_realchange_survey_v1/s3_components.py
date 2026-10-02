"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 3: change-component inventory.

Footprint-independent screen over the image-supported domain.  For each prior
(ALS 2022 surface, LoD2 roofs with 'no building' = terrain) and each current
source (ULS 2024-12-17 = independent reference, MVS 2024-12-17 = current-image
observation), cells with |current - prior| above a threshold that are not
vegetation-like are grouped into 8-connected components of >= 25 m2.

Height above ground uses the ALS 2022 class-2 DTM (nearest-filled, 5x5 median).
Vegetation-like = ULS multi-return fraction > 0.3, or ALS class-20 share > 0.5
without class-6 points.  Rules are descriptive screens fixed before reading the
result; every component is then looked at in image crops.  scientific_verdict: null.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import scipy.ndimage as ndi

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
D = dict(np.load(out / 'derived.npz'))
blds = json.loads((out / 's1' / 'lod2_buildings.json').read_text())
regs = json.loads((out / 'regions.json').read_text())
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
B_angle = np.deg2rad(70.0); B = np.array([[np.cos(B_angle), np.sin(B_angle)], [np.sin(B_angle), -np.cos(B_angle)]]); sh = np.array([690953.0, 5336071.0])
dtm = D['dtm'].astype(float)
fid = D['fid']
in_lod = fid >= 0
nd = {k: D[k].astype(float) - dtm for k in ('uls', 'mvs', 'als')}
lod_nd = np.where(np.isfinite(D['lod']), D['lod'].astype(float) - dtm, np.where(in_lod, np.nan, 0.0))
nd['lod'] = lod_nd
veg = (D['veg'] > 0.3) | ((D['als_veg'] > 0.5) & (D['als_n_c6'] == 0))
dom = D['in_dom']

from matplotlib.path import Path as MPath
reg_masks = {}
EE, NN = np.meshgrid(ec, nc)
pts = np.column_stack([EE.ravel(), NN.ravel()])
for rid, r in regs.items():
    reg_masks[rid] = MPath(np.array(r['corners_epsg25832'])).contains_points(pts).reshape(ny, nx)

rows = []
for cur in ('uls', 'mvs'):
    for pri in ('als', 'lod'):
        d = nd[cur] - nd[pri]
        valid = np.isfinite(d) & dom
        for thr in (2.5, 1.0):
            m = valid & (np.abs(d) > thr) & ~veg
            m = ndi.binary_opening(m, iterations=1)
            # split by sign so that a raised and a lowered part stay separate components
            for sign in (1, -1):
                ms = m & (np.sign(d) == sign)
                lab, k = ndi.label(ms, structure=np.ones((3, 3)))
                if not k:
                    continue
                area = ndi.sum(np.ones_like(d), lab, index=np.arange(1, k + 1)) * res * res
                for j in np.nonzero(area >= 25.0)[0]:
                    sel = lab == j + 1
                    yy, xx = np.nonzero(sel)
                    e = float(ec[int(round(xx.mean()))]); n = float(nc[int(round(yy.mean()))])
                    uv = (np.array([e, n]) - sh) @ B.T
                    ids, cnt = np.unique(fid[sel][fid[sel] >= 0], return_counts=True)
                    blist = ';'.join('%s:%.2f' % (blds[i]['id'].replace('DEBY_LOD2_', ''), c / sel.sum()) for i, c in sorted(zip(ids, cnt), key=lambda t: -t[1])[:4])
                    hc = float(np.nanmedian(nd[cur][sel])); hp = float(np.nanmedian(nd[pri][sel]))
                    other = 'mvs' if cur == 'uls' else 'uls'
                    d_other = nd[other][sel] - nd[pri][sel]
                    agree = float(np.mean((np.abs(d_other) > thr) & (np.sign(d_other) == sign))) if np.isfinite(d_other).any() else None
                    if hp > 2.5 and hc < 1.0:
                        kind = 'removed'
                    elif hp < 1.0 and hc > 2.5:
                        kind = 'new'
                    elif sign < 0:
                        kind = 'lower'
                    else:
                        kind = 'higher'
                    rows.append(dict(cur=cur, prior=pri, thr=thr, sign=sign, kind=kind, area_m2=round(float(area[j]), 1),
                                     e=round(e, 1), n=round(n, 1), u=round(float(uv[0]), 1), v=round(float(uv[1]), 1),
                                     d_med=round(float(np.nanmedian(d[sel])), 2), d_p90abs=round(float(np.nanquantile(np.abs(d[sel]), .9)), 2),
                                     h_cur=round(hc, 2), h_prior=round(hp, 2), other_agree=None if agree is None else round(agree, 3),
                                     als_c6_share=round(float(np.mean(D['als_n_c6'][sel] > 0)), 3), in_lod2=round(float(in_lod[sel].mean()), 3),
                                     buildings=blist, regions=';'.join(rid for rid, mk in reg_masks.items() if mk[sel].mean() > 0.05),
                                     bbox=[float(ec[xx.min()]), float(nc[yy.min()]), float(ec[xx.max()]), float(nc[yy.max()])]))
keys = list(rows[0].keys())
with open(out / 'change_components.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
    for r in rows:
        w.writerow({k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()})
print(len(rows), 'components')
for r in rows:
    if r['thr'] == 2.5:
        print(r['cur'], r['prior'], r['kind'], r['area_m2'], r['e'], r['n'], 'uv', r['u'], r['v'], 'd', r['d_med'], 'h', r['h_cur'], r['h_prior'],
              'agree', r['other_agree'], 'c6', r['als_c6_share'], 'lod', r['in_lod2'], r['buildings'], r['regions'])
