"""5절(점이 얼마나 지워지나)과 6절(다시 낸 판정)의 패치·점 값. 참값은 처음 상태·채점에만(JUDGESTRUCT js1 과 같은 쓰임).
판정 = JUDGESTRUCT-v1 구조 하한: J.decide(본값 규칙: 점 4개 미만은 가시성 검사대로, 한계 안 = 일치, 저장된 광도 결과) 뒤 차이가 유의한 패치 = 영상 깊이 사용.
바뀌는 값: n, MVS 높이, u_M, L, d, geometry, 가시성(free). 고정: 사전 정보 높이, σ_P, σ_W, r, τ, 광도 결과, 처음 상태.
사용: mf4_judge.py <prior> <method> [<method> ...]"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *            # J, CASE, MATCH, PLACE, REGIONS, CASES, STATE, STATE_ORDER, SURF, PN, plane_distance, loadz, wq, ...
import a1_variants as A1
import pandas as pd
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mfcommon as MC
JSP = MC.JS

def load_method(d, prior, method):
    out = {k: [] for k in ['n', 'mvs_mean_m', 'mvs_median_m', 'u_M', 'raw_n', 'free']}
    for ti, t in enumerate(d['tiles']):
        m = np.flatnonzero(d['tile'] == ti); z = loadz(MC.O/'patch'/method/f'{t}.npz'); si = loadz(MC.O/'sight'/method/f'{t}__{prior}.npz', ['free5', 'free10', 'patch_id'])
        assert np.array_equal(z[f'{prior}__patch_id'], d['patch_id'][m]) and np.array_equal(si['patch_id'], d['patch_id'][m])
        for k in ['n', 'mvs_mean_m', 'mvs_median_m', 'u_M', 'raw_n']: out[k].append(z[f'{prior}__{k}'])
        out['free'].append(np.where(d['kind'][m] == 1, si['free10'], si['free5']))
    return {k: np.concatenate(v) for k, v in out.items()}

def main(prior, methods):
    MC.cfg(); T = Timer(); OUT = MC.O/'judge'/prior; OUT.mkdir(parents=True, exist_ok=True)
    d = A1.load(prior); x = loadz(JP/f'patch_{prior}.npz', ['building', 'place'])
    N = len(d['kind']); A = d['area']; mi = J.VARIANTS.index('method'); hP = d['prior_height_m']; sP, sW, rr = d['sigma_P'], d['sigma_W'], d['r_m']
    valid = np.isfinite(hP) & np.isfinite(d['normal']).all(1); normal_ok = np.isfinite(d['normal']).all(1); pcode = d['photo_code']
    rb0 = d['j_region'][:, mi].copy(); hb = d['target_h'][:, mi]
    pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int); assert len(pc) == N
    fa = np.load(JSP/prior/'fig_arrays.npz'); lo_js = fa['lo']; sig_js = fa['sig']
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'building', 'target_ok_v'])
    keep = np.flatnonzero(g['paired'] & np.isin(g['case'], CASES)); gid = g['gid'][keep]; cs = g['case'][keep]; Ng = len(keep)
    ok0 = g['target_ok_v'][mi][keep]; xyz = g['xyz'][keep]; nor = g['normal'][keep]; wall = g['gt_kind'][keep] == 2; tau = g['tau'][keep]; del g
    pkind = d['kind'][gid]; exp_reg = np.array([MATCH[c] for c in CASES])[np.searchsorted(CASES, cs)]
    def score(h):
        hc = ~((h == hb) | (np.isnan(h) & np.isnan(hb))); ok = ok0.copy(); sel = np.flatnonzero(hc[gid]); pg = gid[sel]
        if len(sel): ds = plane_distance(xyz[sel], nor[sel], d['centre'][pg], d['normal'][pg], h[pg], wall[sel]); ok[sel] = np.abs(ds) <= tau[sel]
        return ok
    same = cs == pc[gid]; valid_pc = np.isin(pc, CASES)
    def pok_of(ok):
        num = np.bincount(gid[same], weights=ok[same], minlength=N); den = np.bincount(gid[same], minlength=N); return (den > 0) & (num/np.maximum(den, 1) >= .5)
    exp_p = np.full(N, -1); exp_p[valid_pc] = [MATCH[int(c)] for c in pc[valid_pc]]
    base = None; CHK = []; ROWS = []; IS = []; TR = []; PATCH = {}
    for method in methods:
        v = load_method(d, prior, method); n = v['n']; hM = v['mvs_mean_m']; u = v['u_M']
        dm = hM - hP
        with np.errstate(invalid='ignore'): L = 1.96*(np.sqrt(u**2 + sP**2 + sW**2) + np.abs(rr))
        geom = J.geometry_code(n, dm, L)
        reg, why = J.decide(prior, n, geom, hP, hM, normal_ok, u, pcode, v['free']); rb = reg[mi]
        sig = valid & (n >= 4) & (geom == 1); lo = rb.copy(); lo[sig] = 2
        h = J.target_height(lo, hP, hM, u, sP, sW); ok = score(h); pok = pok_of(ok)
        if method == 'none':
            eqf = lambda a, b: 100*float(np.mean((a == b) | (np.isnan(a) & np.isnan(b)))) if a.dtype.kind == 'f' else 100*float(np.mean(a == b))
            for nm, a, b in [('n', n, d['n']), ('MVS 높이', hM, d['mvs_mean_m']), ('u_M', u, d['u_M']), ('L', L, d['L_m']), ('d', dm, d['d_for_check']), ('geometry', geom, d['geometry']),
                             ('가시성 free', v['free'], d['free']), ('본값 판정', rb, rb0), ('차이가 유의한 패치', sig, sig_js), ('구조 하한 판정', lo, lo_js)]:
                CHK.append(dict(prior=prior, check=f'검산 1: 지금 점군 다시 냄 {nm} = 저장 값', equal_pct=eqf(np.asarray(a), np.asarray(b)), n=N))
            base = dict(lo=lo, sig=sig, n=n, raw_n=v['raw_n'], med=v['mvs_median_m'], geom=geom)
        # ---- 6절 줄
        for sn, kk in SURF[prior]:
            kp = np.isin(pkind, kk); km = np.isin(d['kind'], kk); row = dict(prior=prior, surface=sn, method=method)
            for c in CASES:
                m = kp & (cs == c); row[f'n_{CASE[c]}'] = int(m.sum()); row[f'ok_{CASE[c]}'] = 100*ok[m].mean(); row[f'name_{CASE[c]}'] = 100*(lo[gid][m] == exp_reg[m]).mean()
                mp = km & (pc == c); a = A[mp].sum(); row[f'patch_ok_{CASE[c]}'] = 100*A[mp & pok].sum()/a
            row['ok_전체'] = 100*ok[kp].mean(); mp = km & valid_pc; row['patch_ok_전체'] = 100*A[mp & pok].sum()/A[mp].sum()
            for lv in ['ok', 'patch_ok']:
                vals = np.array([row[f'{lv}_{CASE[c]}'] for c in CASES]); row[f'{lv}_네 경우 평균'] = float(vals.mean()); row[f'{lv}_최솟값'] = float(vals.min()); row[f'{lv}_최대 격차'] = float(vals.max() - vals.min())
            row['sig_area_m2'] = float(A[km & sig].sum()); row['sig_patches'] = int((km & sig).sum())
            ROWS.append(row)
            # 처음 상태 (셈 1-1 같은 표, 차이가 유의한 패치)
            m = sig & km; st = m & np.isin(pc, STATE_ORDER); a_st = A[st].sum(); r = dict(prior=prior, surface=sn, method=method, patches=int(m.sum()), area_m2=float(A[m].sum()), area_with_state_m2=float(a_st))
            for s_ in STATE_ORDER: mm = m & (pc == s_); r[f'n_{STATE[s_]}'] = int(mm.sum()); r[f'area_pct_{STATE[s_]}'] = 100*A[mm].sum()/a_st if a_st else np.nan
            for s_ in [-2, -3, -9]: r[f'n_{STATE[s_]}'] = int((m & (pc == s_)).sum())
            IS.append(r)
            # 판정 바뀜
            if method != 'none':
                ch = km & (lo != base['lo'])
                for (f_, t_), grp in pd.DataFrame(dict(f=base['lo'][ch], t=lo[ch], a=A[ch])).groupby(['f', 't']):
                    TR.append(dict(prior=prior, surface=sn, method=method, before=JUD.get(int(f_), str(f_)), after=JUD.get(int(t_), str(t_)), patches=len(grp), area_m2=float(grp.a.sum()), area_pct_of_surface=100*float(grp.a.sum()/A[km].sum())))
        PATCH[method] = dict(raw_n=v['raw_n'], n=n, lo=lo, sig=sig, med=v['mvs_median_m'], geom=geom)
        print('JUDGE', prior, method, json.dumps(jsafe({k: ROWS[-1][k] for k in ['ok_전체', 'patch_ok_전체', 'sig_area_m2']}), ensure_ascii=False), round(T.s()), flush=True)
    pd.DataFrame(ROWS).to_csv(OUT/f'rows_{"_".join(methods)}.csv', index=False); pd.DataFrame(IS).to_csv(OUT/f'initial_{"_".join(methods)}.csv', index=False)
    pd.DataFrame(TR).to_csv(OUT/f'transitions_{"_".join(methods)}.csv', index=False)
    for method, p in PATCH.items():
        np.savez_compressed(OUT/f'patch_{method}.npz', **p)
    dump(OUT/f'checks_{"_".join(methods)}.json', dict(at=now(), checks=CHK, seconds=T.s(), scientific_verdict=None))
    for c in CHK: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False), flush=True)
    MC.progress(f'mf4 {prior} {methods} 끝, {round(T.s())} 초')

if __name__ == '__main__': main(sys.argv[1], sys.argv[2:])
