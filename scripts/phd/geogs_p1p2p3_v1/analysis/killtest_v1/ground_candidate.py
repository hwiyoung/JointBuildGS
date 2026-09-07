"""Oracle test (vectorized): snap stale prior surface to the prior's own local ground; does it recover the current surface?"""
import sys, json, numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import minimum_filter
from zones import *
region, task, fp_path, out = sys.argv[1:5]
prior = np.load(f'{task}/evaluation/geometry/{region}/prior_mesh/sample0.1_reference0.1.npz')
R = prior['reference_points']; d_rp = prior['reference_to_triangle_distance']; S = prior['prediction_surface_samples']; d_s = prior['prediction_to_reference_distance']
fp_fn, ids = load_footprint_mask_fn(fp_path, region); ras = build_zone_raster(region, R, d_rp, fp_fn); labels = zone_labels(region, ras)
s_lab = label_points(region, ras, labels, S[:, :2]); r_lab = label_points(region, ras, labels, R[:, :2])
stale_zone = 'stale_now_low' if region == 'P1' else 'bldg_stale'
stale = (s_lab == stale_zone) & (d_s >= 1.0)
print('prior samples', len(S), 'stale samples (oracle)', int(stale.sum()), 'ref in stale zone', int((r_lab == stale_zone).sum()))
# prior local ground raster from NON-stale prior samples: 2 m cells, 5th percentile z, then 15 m window minimum
(x0, x1), (y0, y1) = DOMAINS[region]; c = 2.0
nx = int(np.ceil((x1 - x0) / c)) + 1; ny = int(np.ceil((y1 - y0) / c)) + 1
low = S[~stale]
ix = np.clip(((low[:, 0] - x0) / c).astype(int), 0, nx - 1); iy = np.clip(((low[:, 1] - y0) / c).astype(int), 0, ny - 1)
flat = iy * nx + ix
g = np.full(nx * ny, np.inf)
order = np.argsort(flat); fs = flat[order]; zs = low[order, 2]
st = np.searchsorted(fs, np.arange(nx * ny)); en = np.searchsorted(fs, np.arange(nx * ny), side='right')
for k in range(nx * ny):
    if en[k] - st[k] >= 5: g[k] = np.quantile(zs[st[k]:en[k]], 0.05)
g2 = minimum_filter(g.reshape(ny, nx), size=15, mode='nearest')   # 15 cells = 30 m window
sx = np.clip(((S[:, 0] - x0) / c).astype(int), 0, nx - 1); sy = np.clip(((S[:, 1] - y0) / c).astype(int), 0, ny - 1)
gz = g2[sy, sx]
moved = S.copy(); moved[stale, 2] = gz[stale]
ok = np.isfinite(moved[:, 2])
tree_ref = cKDTree(R)
d_after, nn = tree_ref.query(moved[stale & ok], k=1); d_before = d_s[stale & ok]
tree_mv = cKDTree(moved[ok]); tree_orig = cKDTree(S)
rz = r_lab == stale_zone
r_after, _ = tree_mv.query(R[rz], k=1); r_before, _ = tree_orig.query(R[rz], k=1)
# how far is prior ground from current UAS ground in the stale zone: compare gz to the lowest UAS z per cell
res = dict(region=region, stale_samples=int(stale.sum()), stale_with_ground=int((stale & ok).sum()),
           snapped_minus_nearest_uas_z_median=float(np.median(moved[stale & ok, 2] - R[nn, 2])),
           precision_stale_before={t: float((d_before <= t).mean()) for t in [0.25, 0.5, 1.0]}, precision_stale_after={t: float((d_after <= t).mean()) for t in [0.25, 0.5, 1.0]},
           recall_stale_before={t: float((r_before <= t).mean()) for t in [0.25, 0.5, 1.0]}, recall_stale_after={t: float((r_after <= t).mean()) for t in [0.25, 0.5, 1.0]},
           median_dist_before=float(np.median(d_before)), median_dist_after=float(np.median(d_after)), p90_dist_after=float(np.quantile(d_after, .9)))
json.dump(res, open(f'{out}/ground_candidate_{region}.json', 'w'), indent=1); print(json.dumps(res, indent=1))
