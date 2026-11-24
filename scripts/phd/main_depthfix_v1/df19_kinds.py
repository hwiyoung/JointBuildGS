"""Additional request 1 (11-24), item 1: kinds of instruction the target points receive in VISIBLE views, maps 판 0 and 판 1 (CPU, read only).
Target points = case 2 (image depth wrong) & 판 0 target right; lost / kept by 판 0 seed 0 base extraction. Views = outward (point normal faces the camera), point in frame,
visible = image depth at the point's pixel not nearer than the point by > 10 m (TARGETPATH 10 m rule). Pixel = floor(K x + 0.5).
Kinds (TARGETPATH-v1 tp2, unchanged): 1 right target (disc owner, weight > 0, |target − point depth| <= τ), 2 other target in front (disc, weight > 0, target < point − τ),
3 image-depth instruction (no disc, weight > 0; sub-split: within τ / in front / behind the point), 4 target behind (disc, weight > 0, target > point + τ), 5 no instruction (weight 0).
Per point: share of visible views of each kind -> median over points; share of points with kind 1 > 1/2; share of points with kind 3 > 1/2 and, among kind-3 instructions,
the share outside τ (pooled over pairs, and per-point median); pixel weight median per kind (pooled over pairs, zeros excluded).
usage: df19_kinds.py <stem>   writes docs/tables/kinds_visible_<stem>.csv/json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
KN = ['맞는 목표', '앞의 다른 목표', '영상 깊이 지시', '뒤의 목표', '지시 없음']

def main(stem):
    site = stem.split('__')[0]; P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'normal', 'tau', 'case_id', 'target_ok']); R = loadz(O/'points_out'/f'res_{stem}.npz', ['p0_s0'])
    tgt = np.flatnonzero((P['case_id'] == 2) & P['target_ok']); kept = (R['p0_s0'][tgt] & 1).astype(bool)
    X = P['xyz'][tgt].astype('f8'); N = P['normal'][tgt].astype('f8'); tau = P['tau'][tgt]; n = len(tgt)
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']
    cnt = {m: np.zeros((n, 5), 'i4') for m in ['p0', 'p1']}; sub3 = {m: np.zeros((n, 3), 'i4') for m in ['p0', 'p1']}; vis = np.zeros(n, 'i4')
    W = {m: {k: [] for k in range(5)} for m in ['p0', 'p1']}; Wk = {m: {k: [] for k in range(5)} for m in ['p0', 'p1']}
    for name, meta in idx.items():
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M); Pc = X@M[:3, :3].T + M[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = np.floor(K[0, 0]*Pc[:, 0]/z + K[0, 2] + .5); v = np.floor(K[1, 1]*Pc[:, 1]/z + K[1, 2] + .5)
        ok = (z > .1) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741) & (((Cc[None] - X)*N).sum(1) > 0); ii = np.flatnonzero(ok)
        if not len(ii): continue
        uu, vv, zz = u[ii].astype(int), v[ii].astype(int), z[ii]
        mv = np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f'{name}.npy')[vv, uu]; vs = ~(np.isfinite(mv) & (mv > 0) & (mv < zz - 10.)); ii, uu, vv, zz = ii[vs], uu[vs], vv[vs], zz[vs]
        vis[ii] += 1; t = tau[ii]
        for m, var in [('p0', 'base'), ('p1', 'ga')]:
            a = loadz(O/'maps/base'/var/stem/f'{name}.npz', ['depth', 'weight', 'owner']); o = a['owner'][vv, uu]; w = a['weight'][vv, uu]; d = a['depth'][vv, uu]
            k = np.full(len(ii), 4); disc = (o >= 0) & (w > 0); img = (o < 0) & (w > 0)
            k[disc & (np.abs(d - zz) <= t)] = 0; k[disc & (d < zz - t)] = 1; k[img] = 2; k[disc & (d > zz + t)] = 3
            np.add.at(cnt[m], (ii, k), 1)
            s3 = np.where(np.abs(d - zz) <= t, 0, np.where(d < zz, 1, 2)); np.add.at(sub3[m], (ii[img], s3[img]), 1)
            for kk in range(5):
                mk = (k == kk) & (w > 0)
                if mk.any(): W[m][kk].append(w[mk]); Wk[m][kk].append(kept[ii[mk]])
    rows = []
    for g, gm in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        for m, lab in [('p0', '판 0'), ('p1', '판 1')]:
            c = cnt[m][gm]; vv_ = vis[gm]; has = vv_ > 0; share = c[has]/vv_[has, None]
            r = dict(stem=STEM_KO[stem], group=g, map=lab, points=int(gm.sum()), points_with_visible_views=int(has.sum()), visible_views_median=float(np.median(vv_)) if len(vv_) else None)
            for kk in range(5): r[f'{KN[kk]}_비율_중앙값_pct'] = 100*float(np.median(share[:, kk])) if has.any() else None
            r['맞는 목표_절반_넘는_점_pct'] = 100*float((share[:, 0] > .5).mean()) if has.any() else None
            r['영상 깊이 지시_절반_넘는_점_pct'] = 100*float((share[:, 2] > .5).mean()) if has.any() else None
            s3 = sub3[m][gm]; tot3 = s3.sum()
            r['영상 깊이 지시_허용 밖_pct(모음)'] = 100*float((s3[:, 1] + s3[:, 2]).sum()/tot3) if tot3 else None
            r['영상 깊이 지시_앞_pct(모음)'] = 100*float(s3[:, 1].sum()/tot3) if tot3 else None; r['영상 깊이 지시_뒤_pct(모음)'] = 100*float(s3[:, 2].sum()/tot3) if tot3 else None
            p3 = s3.sum(1) > 0; r['영상 깊이 지시_허용 밖_점마다 중앙값_pct'] = 100*float(np.median((s3[p3, 1] + s3[p3, 2])/s3[p3].sum(1))) if p3.any() else None
            for kk in range(4):
                if W[m][kk]:
                    w_ = np.concatenate(W[m][kk]); kp = np.concatenate(Wk[m][kk]); sel = kp if g.startswith('지킨') else ~kp
                    r[f'{KN[kk]}_무게_중앙값(0 뺌)'] = float(np.median(w_[sel])) if sel.any() else None
            rows.append(r)
    table(f'kinds_visible_{stem}', rows); print('KINDS', stem, json.dumps(rows[1], ensure_ascii=False)[:500], flush=True)

if __name__ == '__main__': main(sys.argv[1])
