"""Work da (order 5): forces on the problem-making Gaussians by loss, from the signed gradient records (r31 trainlog grads at the save iterations). CPU.
  grads <run> <place> <control> : problem group, control group and the floor-bound Gaussians of addendum 4, per window / kind / distance bin / after reset
                                  -> tables/da_grads_<run>.csv, payload addendum5/da/grads_<run>.npz (one row per Gaussian x record)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
DA5 = A5O/'da'
TERMS = [('photo', '광도'), ('depth', '깊이'), ('gs2d', '2DGS 정규화')]

def summ(sel, R):
    out = {}
    n = int(sel.sum()); out['samples'] = n; out['gaussians'] = int(len(np.unique(R['uid'][sel]))) if n else 0
    for t, ko in TERMS:
        g = -R[f'{t}_op'][sel]; nz = g != 0
        out[f'{ko}_불투명도_받은기록'] = int(nz.sum())
        out[f'{ko}_불투명도_올림%_받은기록'] = pct(g[nz] > 0) if nz.any() else None
        out[f'{ko}_불투명도_올림%_전체기록'] = pct(g > 0) if n else None
        out[f'{ko}_불투명도_합'] = float(g.sum()) if n else None
        out[f'{ko}_불투명도_중앙값_받은기록'] = med(g[nz]); out[f'{ko}_불투명도_절댓값중앙값_받은기록'] = med(np.abs(g[nz]))
        out[f'{ko}_불투명도_평균_전체기록'] = float(g.mean()) if n else None
        p = R[f'{t}_pos'][sel]; pz = (R[f'{t}_xyzmag'][sel] > 0) & np.isfinite(p)   # nan = no target plane (floater)
        out[f'{ko}_위치_목표면반대쪽%_받은기록'] = pct(p[pz] > 0) if pz.any() else None
        out[f'{ko}_위치_법선성분중앙값_받은기록'] = med(p[pz]); out[f'{ko}_위치_법선성분절댓값중앙값'] = med(np.abs(p[pz]))
    ph = np.abs(R['photo_op'][sel]); de = np.abs(R['depth_op'][sel]); ok = ph > 0
    out['깊이대광도_불투명도_q25_q50_q75'] = q4(de[ok]/ph[ok]); out['깊이대광도_표본'] = int(ok.sum())
    out['깊이0_광도>0_비율%'] = pct((de == 0)[ok]) if ok.any() else None
    out['small_group'] = out['gaussians'] < 30
    return out

def grads(run, place, control):
    c = cfg5(); model = run_model(run); bands = groups_for(place, control, run)
    if place == 'floor_band': pp = place_patches(place); lut = {int(v): pp['out'][i] for i, v in enumerate(pp['v'])}; vb = pp['v']
    else: vb = None
    files = sorted((model/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem)); recs = {k: [] for k in ['group', 'it', 'uid', 'kind', 'dn', 'post'] + [f'{t}_{x}' for t, _ in TERMS for x in ['op', 'pos', 'xyzmag']]}
    resets = c['resets']
    for f in files:
        it = int(f.stem); g = loadz(f)
        if f'photo_opacity_signed' not in g: raise SystemExit(f'{run}: no signed gradients')
        S = raw_state(model, str(it)); idx = {int(u): i for i, u in enumerate(S['uid'])}; j = np.array([idx.get(int(u), -1) for u in g['uid']]); ok = np.flatnonzero(j >= 0)
        X = S['xyz'][j[ok]].astype('f8'); tag = S['target_tag'][j[ok]]; ti = S['target_index'][j[ok]]; Ssub = dict(xyz=X, uid=S['uid'][j[ok]])
        post = any(r < it <= r+100 for r in resets)
        sets = []
        for nm, B in bands.items():
            m, dn, _ = member_of(B, Ssub, it); no = out_normal(B, B.last_j[m]) if m.any() else None
            sets.append((nm, np.flatnonzero(m), dn[m], no if no is not None else np.full((int(m.sum()), 3), np.nan), kind_of5(tag[m], ti[m], B.vset)))
        bb = np.flatnonzero((tag == 1) & np.isin(ti, vb)) if vb is not None else np.zeros(0, 'i8')
        if len(bb):
            nout = np.array([lut[int(v)] for v in ti[bb]]); dnb, _, _ = bands['문제 무리'].offsets(X[bb])
            sets.append(('바닥에 묶인 가우시안(덧붙임 4)', bb, dnb, nout, np.zeros(len(bb), 'i1')))
        for nm, rr, dn, nout, kd in sets:
            if not len(rr): continue
            gi = ok[rr]; recs['group'].append(np.full(len(rr), nm, dtype=object)); recs['it'].append(np.full(len(rr), it)); recs['uid'].append(g['uid'][gi]); recs['kind'].append(kd)
            recs['dn'].append(dn); recs['post'].append(np.full(len(rr), post))
            for t, _ in TERMS:
                recs[f'{t}_op'].append(g[f'{t}_opacity_signed'][gi].astype('f8')); recs[f'{t}_xyzmag'].append(g[f'{t}_xyz'][gi].astype('f8'))
                recs[f'{t}_pos'].append(-(g[f'{t}_xyzvec'][gi].astype('f8')*nout).sum(1))   # gradient-descent step along n_out: + = away from the target plane
    R = {k: np.concatenate(v) if v else np.zeros(0) for k, v in recs.items()}; rows = []
    W = [tuple(w) for w in c['work_da']['windows']]; bins = [tuple(b) for b in c['work_da']['distance_bins_m']]
    for nm in ['문제 무리', '대조 무리', '바닥에 묶인 가우시안(덧붙임 4)']:
        G = R['group'] == nm
        for a, b in W:
            w = G & (((R['it'] > a) & (R['it'] <= b)) | ((a == 0) & (R['it'] == 0)))
            if not w.any(): continue
            rows.append(dict(run=run, group=nm, window=f'{a}–{b}', split='전체', **summ(w, R)))
            if nm != '바닥에 묶인 가우시안(덧붙임 4)':
                for k in range(4):
                    s = w & (R['kind'] == k)
                    if s.any(): rows.append(dict(run=run, group=nm, window=f'{a}–{b}', split=f'종류: {KIND_KO[k]}', **summ(s, R)))
            for lo, hi in bins:
                s = w & (R['dn'] >= lo) & (R['dn'] < hi if hi < 3 else R['dn'] <= hi)
                if s.any(): rows.append(dict(run=run, group=nm, window=f'{a}–{b}', split=f'목표면까지 {lo}–{hi} m', **summ(s, R)))
            for pv, ko in [(True, '재설정 뒤 100회 안'), (False, '그 밖')]:
                s = w & (R['post'] == pv)
                if s.any(): rows.append(dict(run=run, group=nm, window=f'{a}–{b}', split=ko, **summ(s, R)))
    table5(f'da_grads_{run}', rows); DA5.mkdir(parents=True, exist_ok=True)
    savez(DA5/f'grads_{run}.npz', **{k: (v.astype(str) if k == 'group' else v) for k, v in R.items()}); print('GRADS', run, len(files), len(R['uid']), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'grads': grads}[a[0]](*a[1:])
