"""DA3 depth vs UAS reference (evaluation-only) + GT-free multi-view DA3 consistency test.
Usage: da3_audit.py REGION TASK REFERENCE_NPZ FOOTPRINT_GEOJSON OUT"""
import sys, os, json, numpy as np
from scipy.spatial import cKDTree
from zones import *
region, task, ref_path, fp_path, out = sys.argv[1:6]
W, H = 1400, 1013
BLOCK = 4          # z-buffer block (px)
ZTOL = 0.35        # occlusion tolerance (m)
# ---- cameras
cam = open(f'{task}/inputs/{region}/scene/train_sparse_txt/cameras.txt').read().split()
fx, fy, cx, cy = map(float, cam[4:8])
K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
views = []
for line in open(f'{task}/inputs/{region}/scene/train_sparse_txt/images.txt'):
    t = line.split()
    if len(t) >= 10 and t[-1].lower().endswith('.jpg'):
        q = np.array(list(map(float, t[1:5]))); tr = np.array(list(map(float, t[5:8]))); name = t[9]
        w, x, y, z = q
        Rm = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        views.append((name, Rm, tr))
print('views', len(views))
# ---- reference: full (for z-buffer) and prism (for scoring + zones)
full = np.load(ref_path)['uas_xyz'].astype(np.float64)
prior = np.load(f'{task}/evaluation/geometry/{region}/prior_mesh/sample0.1_reference0.1.npz')
Rp = prior['reference_points']; d_rp = prior['reference_to_triangle_distance']
fp_fn, ids = load_footprint_mask_fn(fp_path, region)
ras = build_zone_raster(region, Rp, d_rp, fp_fn); labels = zone_labels(region, ras)
ref_lab = label_points(region, ras, labels, Rp[:, :2])
print('full ref', full.shape, 'x', full[:,0].min(), full[:,0].max(), 'y', full[:,1].min(), full[:,1].max(), '| prism ref', len(Rp))
# subsample full for z-buffer speed (voxel 0.2 m)
vox = np.floor(full / 0.2).astype(np.int64); _, ui = np.unique(vox, axis=0, return_index=True); fz = full[ui]
print('zbuffer points', len(fz))
# score points: prism reference (already 0.1 voxel)
P = Rp
def project(X, Rm, tr):
    Xc = X @ Rm.T + tr
    z = Xc[:, 2]
    u = fx * Xc[:, 0] / np.where(z != 0, z, 1e-9) + cx; v = fy * Xc[:, 1] / np.where(z != 0, z, 1e-9) + cy
    return u, v, z
# accumulate per (point, view)
rec_pt, rec_view, rec_e, rec_z, rec_conf = [], [], [], [], []
per_view = []
da3_dir = f'{task}/inputs/{region}/da3/raw_depth'; conf_dir = f'{task}/inputs/{region}/da3/confidence'
for vi, (name, Rm, tr) in enumerate(views):
    stem = os.path.splitext(name)[0]
    D = np.load(f'{da3_dir}/{stem}.npy'); C = np.load(f'{conf_dir}/{stem}.npy') if os.path.exists(f'{conf_dir}/{stem}.npy') else None
    # z-buffer from full reference
    u, v, z = project(fz, Rm, tr)
    ok = (z > 1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    bu = (u[ok] / BLOCK).astype(int); bv = (v[ok] / BLOCK).astype(int)
    nbx, nby = W // BLOCK + 1, H // BLOCK + 1
    zb = np.full(nbx * nby, np.inf); np.minimum.at(zb, bv * nbx + bu, z[ok])
    # prism points
    u, v, z = project(P, Rm, tr)
    ok = (z > 1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    idx = np.flatnonzero(ok)
    bu = (u[idx] / BLOCK).astype(int); bv = (v[idx] / BLOCK).astype(int)
    vis = z[idx] <= zb[bv * nbx + bu] + ZTOL
    idx = idx[vis]
    if len(idx) == 0: per_view.append((name, 0, np.nan, np.nan, np.nan)); continue
    uu = np.clip(np.round(u[idx]).astype(int), 0, W - 1); vv = np.clip(np.round(v[idx]).astype(int), 0, H - 1)
    d = D[vv, uu]; zc = z[idx]
    good = np.isfinite(d) & (d > 0)
    idx, d, zc, uu, vv = idx[good], d[good], zc[good], uu[good], vv[good]
    e = d - zc
    conf = C[vv, uu] if C is not None else np.full(len(d), np.nan)
    rec_pt.append(idx.astype(np.int32)); rec_view.append(np.full(len(idx), vi, np.int16)); rec_e.append(e.astype(np.float32)); rec_z.append(zc.astype(np.float32)); rec_conf.append(conf.astype(np.float32))
    # per-view affine fit d ~ s*z + t (robust via two-pass)
    A = np.stack([zc, np.ones_like(zc)], 1); s, t = np.linalg.lstsq(A, d, rcond=None)[0]
    res = d - (s * zc + t); keep = np.abs(res) < 3 * np.median(np.abs(res)) + 1e-6
    if keep.sum() > 100:
        s, t = np.linalg.lstsq(A[keep], d[keep], rcond=None)[0]; res = d - (s * zc + t)
    per_view.append((name, len(idx), float(s), float(t), float(np.median(np.abs(res)))))
pt = np.concatenate(rec_pt); vw = np.concatenate(rec_view); e = np.concatenate(rec_e); zc = np.concatenate(rec_z); conf = np.concatenate(rec_conf)
print('observations', len(e), 'points observed', len(np.unique(pt)))
# per-point median error
order = np.argsort(pt); ps = pt[order]; es = e[order]
uniq, start = np.unique(ps, return_index=True); end = np.r_[start[1:], len(ps)]
med = np.array([np.median(es[a:b]) for a, b in zip(start, end)]); nobs = end - start
pt_med = np.full(len(P), np.nan); pt_med[uniq] = med; pt_n = np.zeros(len(P), int); pt_n[uniq] = nobs
zones = [zn for zn in sorted(set(labels)) if zn != 'empty']
def stats(x):
    x = x[np.isfinite(x)]
    if len(x) == 0: return dict(n=0)
    return dict(n=int(len(x)), median=float(np.median(x)), mae=float(np.mean(np.abs(x))), p_abs_gt_0_5=float(np.mean(np.abs(x) > 0.5)), p_abs_gt_1=float(np.mean(np.abs(x) > 1)), p_abs_gt_2=float(np.mean(np.abs(x) > 2)), q10=float(np.quantile(x, .1)), q90=float(np.quantile(x, .9)))
res = dict(region=region, views=len(views), observations=int(len(e)), zone_point_median_error=dict(), zone_obs_error=dict(), range_bins=dict(), per_view=per_view)
for zn in ['ALL'] + zones:
    m = np.ones(len(P), bool) if zn == 'ALL' else (ref_lab == zn)
    res['zone_point_median_error'][zn] = stats(pt_med[m])
    mo = np.ones(len(e), bool) if zn == 'ALL' else (ref_lab[pt] == zn)
    res['zone_obs_error'][zn] = stats(e[mo])
edges = [0, 40, 60, 80, 100, 120, 150, 200, 400]
for a, b in zip(edges[:-1], edges[1:]):
    m = (zc >= a) & (zc < b)
    res['range_bins'][f'{a}-{b}'] = stats(e[m]) | dict(rel_mae=float(np.mean(np.abs(e[m]) / zc[m])) if m.sum() else float('nan'))
# error by height class within zones (low vs elevated) for cause analysis
h = P[:, 2] - ras['ground_z'][cell_index(P[:, :2], region)[1] * ras['nx'] + cell_index(P[:, :2], region)[0]]
res['height_class_point_median_error'] = {'ground_h<1': stats(pt_med[h < 1]), 'elevated_h>=2': stats(pt_med[h >= 2])}
# per-view affine summary
sv = np.array([x[2] for x in per_view if x[1] > 0]); tv = np.array([x[3] for x in per_view if x[1] > 0]); rv = np.array([x[4] for x in per_view if x[1] > 0])
res['per_view_affine'] = dict(scale_median=float(np.median(sv)), scale_q10=float(np.quantile(sv, .1)), scale_q90=float(np.quantile(sv, .9)), shift_median=float(np.median(tv)), shift_q10=float(np.quantile(tv, .1)), shift_q90=float(np.quantile(tv, .9)), residual_medabs_median=float(np.median(rv)))
# ---- K-b: GT-free multi-view consistency of DA3 vs GT error
STEP = 14
tree = cKDTree(P)
(x0, x1), (y0, y1) = DOMAINS[region]
Dmaps = {}
for vi, (name, Rm, tr) in enumerate(views):
    Dmaps[vi] = np.load(f'{da3_dir}/{os.path.splitext(name)[0]}.npy')
cons, gterr, probe_z, probe_view, probe_xyz = [], [], [], [], []
vv_grid, uu_grid = np.mgrid[0:H:STEP, 0:W:STEP]; vv_grid = vv_grid.ravel(); uu_grid = uu_grid.ravel()
for vi, (name, Rm, tr) in enumerate(views):
    D = Dmaps[vi]; d = D[vv_grid, uu_grid]; ok = np.isfinite(d) & (d > 0)
    rays = np.stack([(uu_grid[ok] - cx) / fx, (vv_grid[ok] - cy) / fy, np.ones(ok.sum())], 1)
    Xc = rays * d[ok][:, None]; Xw = (Xc - tr) @ Rm   # inverse of Xc = R X + t  -> X = R^T (Xc - t)
    inside = (Xw[:, 0] >= x0) & (Xw[:, 0] < x1) & (Xw[:, 1] >= y0) & (Xw[:, 1] < y1)
    Xw = Xw[inside]; zi = d[ok][inside]
    if len(Xw) == 0: continue
    r_all = np.full((len(Xw), len(views)), np.nan, np.float32)
    for vj, (name2, Rm2, tr2) in enumerate(views):
        if vj == vi: continue
        u2, v2, z2 = project(Xw, Rm2, tr2)
        okj = (z2 > 1) & (u2 >= 0) & (u2 < W) & (v2 >= 0) & (v2 < H)
        if okj.sum() == 0: continue
        dj = Dmaps[vj][np.clip(np.round(v2[okj]).astype(int), 0, H-1), np.clip(np.round(u2[okj]).astype(int), 0, W-1)]
        r_all[okj, vj] = dj - z2[okj]
    nvis = np.isfinite(r_all).sum(1)
    c = np.nanmedian(np.abs(r_all), axis=1)
    g, _ = tree.query(Xw, k=1)
    keep = nvis >= 3
    cons.append(c[keep]); gterr.append(g[keep]); probe_z.append(zi[keep]); probe_view.append(np.full(keep.sum(), vi)); probe_xyz.append(Xw[keep])
cons = np.concatenate(cons); gterr = np.concatenate(gterr); probe_z = np.concatenate(probe_z); probe_xyz = np.concatenate(probe_xyz)
# GT error definition: distance to nearest UAS point (cap 5 m). Probes far from any UAS could be in reference gaps -> cap.
gt_bad = gterr > 1.0
from scipy.stats import spearmanr
def auc(score, y):
    o = np.argsort(score); s = score[o]; yy = y[o]
    # AUC via rank statistic (higher score -> positive)
    r = np.empty(len(s)); r[np.argsort(s)] = np.arange(len(s)) + 1
    npos = y.sum(); nneg = len(y) - npos
    return float((r[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)) if npos and nneg else float('nan')
kb = dict(n_probes=int(len(cons)), frac_gt_err_gt_1=float(gt_bad.mean()), spearman=float(spearmanr(cons, gterr).correlation), auc_consistency_for_gt_err_gt_1=auc(cons, gt_bad))
bins = [0, 0.25, 0.5, 1, 2, 5, 1e9]
tab = []
for a, b in zip(bins[:-1], bins[1:]):
    m = (cons >= a) & (cons < b)
    if m.sum(): tab.append(dict(consistency_bin=f'{a}-{b}', n=int(m.sum()), gt_err_median=float(np.median(gterr[m])), frac_gt_err_gt_1=float(gt_bad[m].mean())))
kb['table'] = tab
kb['silent_failure_frac_among_consistent_lt_0_5'] = float(gt_bad[cons < 0.5].mean()) if (cons < 0.5).sum() else float('nan')
# probes by zone
pl = label_points(region, ras, labels, probe_xyz[:, :2])
kb['by_zone'] = {zn: dict(n=int((pl == zn).sum()), consistency_median=float(np.median(cons[pl == zn])), gt_err_median=float(np.median(gterr[pl == zn])), frac_gt_err_gt_1=float(gt_bad[pl == zn].mean()), silent_frac=float(gt_bad[(pl == zn) & (cons < 0.5)].mean()) if ((pl == zn) & (cons < 0.5)).sum() else float('nan')) for zn in zones if (pl == zn).sum()}
res['kb_consistency'] = kb
json.dump(res, open(f'{out}/da3_audit_{region}.json', 'w'), indent=1, default=float)
np.savez(f'{out}/da3_audit_{region}_arrays.npz', pt_med=pt_med, pt_n=pt_n, ref_lab=ref_lab.astype(str), P=P, cons=cons, gterr=gterr, probe_xyz=probe_xyz, probe_z=probe_z)
print(json.dumps({k: res[k] for k in ['zone_point_median_error', 'height_class_point_median_error', 'range_bins', 'per_view_affine', 'kb_consistency']}, indent=1, default=float))
