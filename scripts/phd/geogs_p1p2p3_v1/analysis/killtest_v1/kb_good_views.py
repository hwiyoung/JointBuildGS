"""K-b at fine level: among GOOD DA3 views only, does GT-free cross-view DA3 consistency predict per-point DA3 error? Also zone-wise DA3 error using good views only."""
import sys, os, json, numpy as np
from scipy.spatial import cKDTree
from zones import *
region, task, ref_path, fp_path, out, good_batches = sys.argv[1:7]
good_batches = set(int(b) for b in good_batches.split(','))
W, H = 1400, 1013
cam = open(f'{task}/inputs/{region}/scene/train_sparse_txt/cameras.txt').read().split(); fx, fy, cx, cy = map(float, cam[4:8])
bm = {}
bdir = f'{task}/da3/{region}/balanced_v2/batches'
for f in sorted(os.listdir(bdir)):
    if f.endswith('.json'):
        j = json.load(open(f'{bdir}/{f}'))
        for n in j['names']: bm[os.path.splitext(n)[0]] = j['batch_id']
views = []
for line in open(f'{task}/inputs/{region}/scene/train_sparse_txt/images.txt'):
    t = line.split()
    if len(t) >= 10 and t[-1].lower().endswith('.jpg'):
        stem = os.path.splitext(t[9])[0]
        if bm.get(stem) not in good_batches: continue
        w, x, y, z = map(float, t[1:5]); tr = np.array(list(map(float, t[5:8])))
        Rm = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        views.append((stem, Rm, tr, np.load(f'{task}/inputs/{region}/da3/raw_depth/{stem}.npy')))
print('good views', len(views), [v[0][-8:] for v in views])
prior = np.load(f'{task}/evaluation/geometry/{region}/prior_mesh/sample0.1_reference0.1.npz')
P = prior['reference_points']; d_rp = prior['reference_to_triangle_distance']
fp_fn, ids = load_footprint_mask_fn(fp_path, region); ras = build_zone_raster(region, P, d_rp, fp_fn); labels = zone_labels(region, ras)
ref_lab = label_points(region, ras, labels, P[:, :2]); zones = [z for z in sorted(set(labels)) if z != 'empty']
tree = cKDTree(P)
def project(X, Rm, tr):
    Xc = X @ Rm.T + tr; z = Xc[:, 2]
    return fx * Xc[:, 0] / np.where(z != 0, z, 1e-9) + cx, fy * Xc[:, 1] / np.where(z != 0, z, 1e-9) + cy, z
# (1) zone-wise DA3 error with good views (z-buffer from prism reference, block 3px)
B = 3; nbx, nby = W // B + 1, H // B + 1
pt_e = [[] for _ in range(len(P))]
recs = []
for stem, Rm, tr, D in views:
    u, v, z = project(P, Rm, tr); ok = (z > 1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    idx = np.flatnonzero(ok); bu = (u[idx] / B).astype(int); bv = (v[idx] / B).astype(int)
    zb = np.full(nbx * nby, np.inf); np.minimum.at(zb, bv * nbx + bu, z[idx])
    vis = z[idx] <= zb[bv * nbx + bu] + 0.3; idx = idx[vis]
    uu = np.clip(np.round(u[idx]).astype(int), 0, W - 1); vv = np.clip(np.round(v[idx]).astype(int), 0, H - 1)
    d = D[vv, uu]; g = np.isfinite(d) & (d > 0); idx, d, zc = idx[g], d[g], z[idx][g]
    recs.append((idx, d - zc))
pt = np.concatenate([r[0] for r in recs]); e = np.concatenate([r[1] for r in recs])
order = np.argsort(pt); ps = pt[order]; es = e[order]
uniq, st = np.unique(ps, return_index=True); en = np.r_[st[1:], len(ps)]
med = np.array([np.median(es[a:b]) for a, b in zip(st, en)]); pt_med = np.full(len(P), np.nan); pt_med[uniq] = med
def stats(x):
    x = x[np.isfinite(x)]
    return dict(n=int(len(x)), median=float(np.median(x)), mae=float(np.mean(np.abs(x))), p_gt_0_5=float(np.mean(np.abs(x) > .5)), p_gt_1=float(np.mean(np.abs(x) > 1))) if len(x) else dict(n=0)
res = dict(region=region, good_views=[v[0] for v in views], zone_err=({zn: stats(pt_med[ref_lab == zn]) for zn in zones} | {'ALL': stats(pt_med)}))
# (2) K-b fine: probes from good views, consistency across other good views, GT error to prism reference
STEP = 12; vv_g, uu_g = np.mgrid[0:H:STEP, 0:W:STEP]; vv_g = vv_g.ravel(); uu_g = uu_g.ravel()
(x0, x1), (y0, y1) = DOMAINS[region]
cons, gterr, pl = [], [], []
for i, (stem, Rm, tr, D) in enumerate(views):
    d = D[vv_g, uu_g]; ok = np.isfinite(d) & (d > 0)
    rays = np.stack([(uu_g[ok] - cx) / fx, (vv_g[ok] - cy) / fy, np.ones(ok.sum())], 1)
    Xw = (rays * d[ok][:, None] - tr) @ Rm
    inside = (Xw[:, 0] >= x0) & (Xw[:, 0] < x1) & (Xw[:, 1] >= y0) & (Xw[:, 1] < y1); Xw = Xw[inside]
    if len(Xw) == 0: continue
    r_all = np.full((len(Xw), len(views)), np.nan, np.float32)
    for j, (stem2, Rm2, tr2, D2) in enumerate(views):
        if j == i: continue
        u2, v2, z2 = project(Xw, Rm2, tr2); okj = (z2 > 1) & (u2 >= 0) & (u2 < W) & (v2 >= 0) & (v2 < H)
        if okj.sum() == 0: continue
        dj = D2[np.clip(np.round(v2[okj]).astype(int), 0, H - 1), np.clip(np.round(u2[okj]).astype(int), 0, W - 1)]
        r_all[okj, j] = dj - z2[okj]
    nv = np.isfinite(r_all).sum(1); keep = nv >= 3
    c = np.nanmedian(np.abs(r_all[keep]), axis=1); g, _ = tree.query(Xw[keep], k=1)
    cons.append(c); gterr.append(g); pl.append(label_points(region, ras, labels, Xw[keep][:, :2]))
cons = np.concatenate(cons); gterr = np.concatenate(gterr); pl = np.concatenate(pl)
from scipy.stats import spearmanr
def auc(score, y):
    r = np.empty(len(score)); r[np.argsort(score)] = np.arange(len(score)) + 1
    npos = y.sum(); nneg = len(y) - npos
    return float((r[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)) if npos and nneg else float('nan')
kb = dict(n_probes=int(len(cons)), spearman=float(spearmanr(cons, gterr).correlation))
for thr in [0.5, 1.0]:
    yb = gterr > thr; kb[f'auc_err_gt_{thr}'] = auc(cons, yb); kb[f'frac_err_gt_{thr}'] = float(yb.mean())
tab = []
for a, b in [(0, .1), (.1, .25), (.25, .5), (.5, 1), (1, 2), (2, 1e9)]:
    m = (cons >= a) & (cons < b)
    if m.sum(): tab.append(dict(cons_bin=f'{a}-{b}', n=int(m.sum()), err_median=float(np.median(gterr[m])), frac_err_gt_0_5=float((gterr[m] > .5).mean()), frac_err_gt_1=float((gterr[m] > 1).mean())))
kb['table'] = tab
kb['by_zone'] = {zn: dict(n=int((pl == zn).sum()), cons_median=float(np.median(cons[pl == zn])), err_median=float(np.median(gterr[pl == zn])), frac_err_gt_0_5=float((gterr[pl == zn] > .5).mean())) for zn in zones if (pl == zn).sum()}
res['kb_good'] = kb
json.dump(res, open(f'{out}/kb_good_{region}.json', 'w'), indent=1, default=float)
print(json.dumps(res, indent=1, default=float))
