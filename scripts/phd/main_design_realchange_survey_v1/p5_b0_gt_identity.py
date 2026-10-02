"""Probe: is the GeoGS example evaluation cloud (r1_b1_sub002_transformed.ply, the source of
gt_cropped / gt_clean) the TUM2TWIN ULS nadir file?  Compares per-0.5 m-cell max heights of
the GT (shifted back to global with the recovered author frame) with the ULS nadir grid and
reports the vertical offset, its spread, and the GT extent/density.  scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text())
art = Path(cfg['artifact_root_container'])
p = art / cfg['inputs']['b0_scene'] / 'evaluation_reference' / 'r1_b1_sub002_transformed.ply'
with open(p, 'rb') as f:
    hdr = b''
    while b'end_header' not in hdr:
        hdr += f.readline()
    off = len(hdr)
n = int([l for l in hdr.decode().splitlines() if l.startswith('element vertex')][0].split()[-1])
dt = np.dtype([('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
v = np.memmap(p, dtype=dt, mode='r', offset=off, shape=(n,))
x = np.asarray(v['x']); y = np.asarray(v['y']); z = np.asarray(v['z'])
print('GT points', n, 'local bbox', [round(a, 2) for a in (x.min(), y.min(), z.min(), x.max(), y.max(), z.max())])
shift = [-690955.0, -5336042.0]
E = x - shift[0]; N = y - shift[1]
print('global XY bbox', round(E.min(), 2), round(N.min(), 2), round(E.max(), 2), round(N.max(), 2), 'area m2 %.0f' % ((E.max() - E.min()) * (N.max() - N.min())))
g = cfg['grid']; res = g['res_m']
A = np.load(out / 's1' / 'rasters_als_mvs_uls.npz')
U = A['uls_zmax'].astype(float); ny, nx = U.shape
ix = ((E - g['e_min']) / res).astype(int); iy = ((N - g['n_min']) / res).astype(int)
ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
flat = iy[ok] * nx + ix[ok]
gmax = np.full(nx * ny, -np.inf); np.maximum.at(gmax, flat, z[ok])
cnt = np.bincount(flat, minlength=nx * ny)
has = (cnt >= 5) & np.isfinite(U.ravel())
d = U.ravel()[has] - gmax[has]
m = np.median(d)
print('cells compared', int(has.sum()), 'ULS zmax - GT zmax: median %.3f  NMAD %.3f  p05 %.3f p95 %.3f  frac |d-med|<0.05 %.3f' % (
    m, 1.4826 * np.median(np.abs(d - m)), np.quantile(d, .05), np.quantile(d, .95), np.mean(np.abs(d - m) < 0.05)))
print('implied global z offset of the GT frame = %.3f m (GT local z + this = ULS height)' % m)
occupied = (cnt > 0).sum() * res * res
print('GT density over occupied cells: %.0f pts/m2 (occupied %.0f m2)' % (n / occupied, occupied))
# colour check: GT RGB vs ULS mean RGB in the same cells
ur = A['uls_rsum'].ravel() / np.maximum(A['uls_n'].ravel(), 1)
gr = np.bincount(flat, weights=np.asarray(v['r'])[ok].astype(float), minlength=nx * ny) / np.maximum(cnt, 1)
cc = np.corrcoef(ur[has], gr[has])[0, 1]
print('per-cell mean red channel correlation GT vs ULS: %.3f' % cc)
res_out = dict(points=n, global_bbox=[float(E.min()), float(N.min()), float(E.max()), float(N.max())], cells=int(has.sum()),
               uls_minus_gt_median=float(m), nmad=float(1.4826 * np.median(np.abs(d - m))), frac_within_5cm=float(np.mean(np.abs(d - m) < 0.05)),
               density_pts_m2=float(n / occupied), red_corr=float(cc))
(out / 'qa' / 'b0_gt_identity.json').write_text(json.dumps(res_out, indent=1))
