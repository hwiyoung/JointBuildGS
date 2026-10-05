"""Per-view triplet check: prior raycast depth vs UAS z-buffer depth (validates pose+projection), DA3 vs prior, DA3 vs UAS. Groups by DA3 batch."""
import sys, os, json, numpy as np
region, task, ref_path, out = sys.argv[1:5]
W, H = 1400, 1013; B = 2
cam = open(f'{task}/inputs/{region}/scene/train_sparse_txt/cameras.txt').read().split(); fx, fy, cx, cy = map(float, cam[4:8])
views = []
for line in open(f'{task}/inputs/{region}/scene/train_sparse_txt/images.txt'):
    t = line.split()
    if len(t) >= 10 and t[-1].lower().endswith('.jpg'):
        w, x, y, z = map(float, t[1:5]); tr = np.array(list(map(float, t[5:8])))
        Rm = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        views.append((t[9], Rm, tr))
bm = {}
bdir = f'{task}/da3/{region}/balanced_v2/batches'
for f in sorted(os.listdir(bdir)):
    if f.endswith('.json'):
        j = json.load(open(f'{bdir}/{f}'))
        for n in j['names']: bm[os.path.splitext(n)[0]] = j['batch_id']
full = np.load(ref_path)['uas_xyz'].astype(np.float64)
vox = np.floor(full / 0.15).astype(np.int64); _, ui = np.unique(vox, axis=0, return_index=True); fz = full[ui]
nbx, nby = W // B + 1, H // B + 1
def robust_affine(x, y):
    A = np.stack([x, np.ones_like(x)], 1)
    s, t = np.linalg.lstsq(A, y, rcond=None)[0]; r = y - (s * x + t)
    for _ in range(2):
        keep = np.abs(r) < 3 * np.median(np.abs(r)) + 1e-6
        if keep.sum() < 50: break
        s, t = np.linalg.lstsq(A[keep], y[keep], rcond=None)[0]; r = y - (s * x + t)
    return float(s), float(t), float(np.median(np.abs(r)))
rows = []
for name, Rm, tr in views:
    stem = os.path.splitext(name)[0]
    Dp = np.load(f'{task}/inputs/{region}/prior/raw_depth/{stem}.npy'); Dd = np.load(f'{task}/inputs/{region}/da3/raw_depth/{stem}.npy')
    Xc = fz @ Rm.T + tr; z = Xc[:, 2]
    u = fx * Xc[:, 0] / np.where(z != 0, z, 1e-9) + cx; v = fy * Xc[:, 1] / np.where(z != 0, z, 1e-9) + cy
    ok = (z > 1) & (u >= 0) & (u < W) & (v >= 0) & (v < H)
    bu = (u[ok] / B).astype(int); bv = (v[ok] / B).astype(int)
    zb = np.full(nbx * nby, np.inf); np.minimum.at(zb, bv * nbx + bu, z[ok])
    zb = zb.reshape(nby, nbx)
    # sample pixel grid
    vv, uu = np.mgrid[0:H:4, 0:W:4]; vv = vv.ravel(); uu = uu.ravel()
    uas = zb[vv // B, uu // B]; pr = Dp[vv, uu]; da = Dd[vv, uu]
    m_pu = np.isfinite(uas) & np.isfinite(pr) & (pr > 0)
    m_du = np.isfinite(uas) & np.isfinite(da) & (da > 0)
    m_dp = np.isfinite(pr) & (pr > 0) & np.isfinite(da) & (da > 0)
    C = -Rm.T @ tr; elev = float(np.degrees(np.arcsin(-Rm[2] @ np.array([0, 0, 1.0])))) if True else 0.0  # view dir z component
    r = dict(name=stem, batch=bm.get(stem, -1), n_pu=int(m_pu.sum()), prior_minus_uas_median=float(np.median(pr[m_pu] - uas[m_pu])) if m_pu.sum() else np.nan,
             prior_minus_uas_medabs=float(np.median(np.abs(pr[m_pu] - uas[m_pu]))) if m_pu.sum() else np.nan,
             da3_minus_uas_median=float(np.median(da[m_du] - uas[m_du])) if m_du.sum() else np.nan,
             da3_minus_prior_median=float(np.median(da[m_dp] - pr[m_dp])) if m_dp.sum() else np.nan,
             cam_z=float(C[2]), viewdir_z=float(Rm[2, 2]), uas_depth_median=float(np.median(uas[m_du])) if m_du.sum() else np.nan)
    if m_dp.sum() > 200: r['da3_vs_prior_scale'], r['da3_vs_prior_shift'], r['da3_vs_prior_res'] = robust_affine(pr[m_dp], da[m_dp])
    if m_du.sum() > 200: r['da3_vs_uas_scale'], r['da3_vs_uas_shift'], r['da3_vs_uas_res'] = robust_affine(uas[m_du], da[m_du])
    if m_pu.sum() > 200: r['prior_vs_uas_scale'], r['prior_vs_uas_shift'], r['prior_vs_uas_res'] = robust_affine(uas[m_pu], pr[m_pu])
    rows.append(r)
json.dump(rows, open(f'{out}/depth_triplet_{region}.json', 'w'), indent=1)
print(f'{region}: views {len(rows)}')
print('name | batch | viewdir_z | uasDepth | prior-uas med/medabs | da3-uas med | da3-prior med | da3~prior (s,t,res) | da3~uas (s,t,res) | prior~uas (s,t,res)')
for r in rows:
    g = lambda k: ('%.2f' % r[k]) if k in r and np.isfinite(r[k]) else '-'
    print('%s | %s | %s | %s | %s/%s | %s | %s | %s,%s,%s | %s,%s,%s | %s,%s,%s' % (r['name'][-12:], r['batch'], g('viewdir_z'), g('uas_depth_median'), g('prior_minus_uas_median'), g('prior_minus_uas_medabs'), g('da3_minus_uas_median'), g('da3_minus_prior_median'),
          g('da3_vs_prior_scale'), g('da3_vs_prior_shift'), g('da3_vs_prior_res'), g('da3_vs_uas_scale'), g('da3_vs_uas_shift'), g('da3_vs_uas_res'), g('prior_vs_uas_scale'), g('prior_vs_uas_shift'), g('prior_vs_uas_res')))
import collections
byb = collections.defaultdict(list)
for r in rows:
    if 'da3_vs_prior_res' in r: byb[r['batch']].append((r['da3_vs_prior_scale'], r['da3_vs_prior_shift'], r['da3_vs_prior_res'], r.get('prior_vs_uas_res', np.nan)))
print('\nbatch | n | da3~prior scale med | shift med | res med | prior~uas res med')
for b, v in sorted(byb.items()):
    v = np.array(v); print('%s | %d | %.3f | %.1f | %.2f | %.2f' % (b, len(v), np.median(v[:, 0]), np.median(v[:, 1]), np.median(v[:, 2]), np.nanmedian(v[:, 3])))
