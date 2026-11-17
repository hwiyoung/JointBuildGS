"""Work na (order 4): is depth supervision on the pixels the problem group gives weight to, and if so is it already satisfied. GPU (/source = r31), scene dumps.
  pixels <run> <state> <place> <control> : per training view, stride-4 pixels inside the group's 3-sigma screen footprints; per pixel group alpha*T,
                                           all-splat contributions (2DGS compositing of addendum 3/4), target depth / sigma / weight / owner of the map
                                           -> payload addendum5/na/pix_<run>_<state>.npz
  tables <run> <state>                   : supervised share (weighted by group alpha*T and by pixel count), owner of the target, rendered - target,
                                           map weight, weight split before / within / after the target +- 1.96 sigma -> tables/na_pixels_<run>_<state>.csv"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
NA5 = A5O/'na'
GROUP_KO = ['문제 무리', '대조 무리']

def pixels(run, state, place, control, stride=4, gmin=1e-3, rmax=96):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_da as D4
    camera = D4.gpu_setup(); t0 = time.monotonic(); model = run_model(run); stem = RUNS4[run]['stem']; S = D4.load_pt(model, state)
    bands = list(groups_for(place, control, run).values()); X = S['xyz'].double().numpy(); size = torch.exp(S['scaling']).max(1).values.numpy()
    it = int(str(state).split('_')[0]); Sd = dict(xyz=X, uid=S['uid'].numpy())
    memb = []   # each group on its own (a Gaussian may be in both, as in works ga and da)
    for gi, B in enumerate(bands):
        m, dn, _ = member_of(B, Sd, it); memb.append(m)
    T_ = Targets(RUNS4[run]['stem'])
    praw = [np.unique(B.P['patch_row'][B.P['patch_row'] >= 0]) if isinstance(B, Band) else (T_.valid[B.vset[B.vset >= 0]] if len(B.vset) else np.zeros(0, 'i8')) for B in bands]
    md, mi = D4.views_of(stem); recs = {k: [] for k in ['view', 'group', 'gw', 'acc', 'mean', 'td', 'sig', 'wmap', 'own', 'w_front', 'w_within', 'w_behind', 'gw_front', 'gw_within', 'gw_behind']}
    gidx = [np.flatnonzero(m) for m in memb]
    with torch.no_grad():
        g = D4.gmodel(S)
        for j, (nm, m) in enumerate(sorted(mi.items())):
            with np.load(md/m['file']) as z: td_m = z['depth']; sg_m = z['sigma']; w_m = z['weight']; own_m = z['owner']
            H, W = own_m.shape; K = np.asarray(m['K']); M = np.asarray(m['W2C']); f = float(K[0, 0])
            for gi in range(2):
                ii = gidx[gi]
                if not len(ii): continue
                Xc = X[ii]@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; ok = zc > .2
                u = K[0, 0]*Xc[:, 0]/np.where(ok, zc, 1)+K[0, 2]; v = K[1, 1]*Xc[:, 1]/np.where(ok, zc, 1)+K[1, 2]
                r = np.minimum(np.ceil(3*size[ii]*f/np.where(ok, zc, 1)), rmax); ok &= (u+r >= 0) & (u-r < W) & (v+r >= 0) & (v-r < H)
                if not ok.any(): continue
                mask = np.zeros((H, W), bool)
                for uu, vv, rr in zip(u[ok], v[ok], r[ok]):
                    x0, x1 = int(max(0, uu-rr)), int(min(W, uu+rr+1)); y0, y1 = int(max(0, vv-rr)), int(min(H, vv+rr+1)); mask[y0:y1, x0:x1] = True
                sub = np.zeros((H, W), bool); sub[::stride, ::stride] = True; py, px = np.nonzero(mask & sub)
                if not len(px): continue
                cam = camera(W, H, K, M, nm); C = D4.contrib(g, cam, px, py); n = len(px)
                if not len(C): continue
                p = C[:, 0].astype('i8'); w = C[:, 2]; z_ = C[:, 3]; isg = memb[gi][C[:, 1].astype('i8')]
                gw = np.bincount(p, w*isg, n); keep = gw > gmin
                if not keep.any(): continue
                acc, mean, _ = D4.per_pixel(C, n); td = td_m[py, px].astype('f8'); sg = sg_m[py, px].astype('f8'); tol = 1.96*sg
                rel = z_-td[p]; fr = rel < -tol[p]; be = rel > tol[p]; wi = ~fr & ~be; okt = np.isfinite(td[p]) & (td[p] > 0)
                for key, msk in [('front', fr), ('within', wi), ('behind', be)]:
                    recs[f'w_{key}'].append(np.bincount(p, w*(msk & okt), n)[keep]); recs[f'gw_{key}'].append(np.bincount(p, w*(msk & okt & isg), n)[keep])
                recs['view'].append(np.full(keep.sum(), j, 'i2')); recs['group'].append(np.full(keep.sum(), gi, 'i1')); recs['gw'].append(gw[keep]); recs['acc'].append(acc[keep]); recs['mean'].append(mean[keep])
                recs['td'].append(td[keep]); recs['sig'].append(sg[keep]); recs['wmap'].append(w_m[py, px].astype('f8')[keep])
                own = own_m[py, px][keep]; recs['own'].append(np.where(np.isin(own, praw[gi]), 0, np.where(own >= 0, 1, 2)).astype('i1'))
    R = {k: np.concatenate(v) if v else np.zeros(0) for k, v in recs.items()}
    NA5.mkdir(parents=True, exist_ok=True); savez(NA5/f'pix_{run}_{state}.npz', **R, group_rows_problem=gidx[0], group_rows_control=gidx[1], stride=np.int32(stride), gmin=np.float32(gmin))
    print('PIXELS', run, state, {k: len(v) for k, v in [('problem', gidx[0]), ('control', gidx[1])]}, len(R['gw']), round(time.monotonic()-t0), flush=True)

def tables(run, state):
    z = loadz(NA5/f'pix_{run}_{state}.npz'); rows = []
    sup = np.isfinite(z['td']) & (z['td'] > 0) & (z['wmap'] > 0) & np.isfinite(z['mean']) & (z['mean'] > 0)
    dd = z['mean']-z['td']; tol = 1.96*z['sig']; within = sup & (np.abs(dd) <= tol)
    OWN = ['그 자리의 목표 원판', '다른 면의 목표 원판', '목표 원판 없음(영상 깊이가 목표, 무게 1 / 영상 깊이도 없으면 감독 없음)']
    for gi, nm in enumerate(GROUP_KO):
        G = z['group'] == gi; n = int(G.sum()); gw = z['gw']
        if not n: continue
        S_ = G & sup; Wt = gw[G].sum()
        r = dict(run=run, state=state, group=nm, gaussians=int(len(z['group_rows_problem' if gi == 0 else 'group_rows_control'])), pixels=n,
                 supervised_pct_pixels=pct(sup[G]), supervised_pct_weighted=100*float(gw[S_].sum()/Wt) if Wt > 0 else None)
        for k, ko in enumerate(OWN):
            r[f'감독 화소 주인: {ko} %(화소)'] = pct(z['own'][S_] == k) if S_.any() else None
            r[f'감독 화소 주인: {ko} %(무게)'] = 100*float(gw[S_ & (z['own'] == k)].sum()/max(gw[S_].sum(), 1e-12)) if S_.any() else None
            r[f'감독 안 걸린 화소: {ko} %'] = pct(z['own'][G & ~sup] == k) if (G & ~sup).any() else None
        r['그린 깊이 - 목표 (m) q25/q50/q75'] = q4(dd[S_]); r['허용 구간 안 %(화소)'] = pct(within[S_]) if S_.any() else None
        r['허용 구간 안 %(무게)'] = 100*float(gw[S_ & within].sum()/max(gw[S_].sum(), 1e-12)) if S_.any() else None
        r['화소 무게 q25/q50/q75'] = q4(z['wmap'][S_]); r['화소 무게 1인 화소 %'] = pct(z['wmap'][S_] == 1.) if S_.any() else None
        for key, ko in [('front', '목표 앞'), ('within', '목표 ± 1.96σ'), ('behind', '목표 뒤')]:
            r[f'화소당 무게 평균: {ko}'] = float(z[f'w_{key}'][S_].mean()) if S_.any() else None
            r[f'그 가운데 무리의 무게 평균: {ko}'] = float(z[f'gw_{key}'][S_].mean()) if S_.any() else None
        r['무리 무게 q25/q50/q75 (감독 화소)'] = q4(gw[S_])
        r['허용 구간 안이면서 무리 무게 ≥ 0.1 %(감독 화소)'] = pct((within & (gw >= .1))[S_]) if S_.any() else None
        r['small_group'] = r['gaussians'] < 30
        rows.append(r)
    table5(f'na_pixels_{run}_{state}', rows); print('NA TABLE', run, state, flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'pixels': pixels, 'tables': tables}[a[0]](*a[1:])
