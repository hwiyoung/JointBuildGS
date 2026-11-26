"""덧붙임 3 2절: u_M 이 빈 패치에 후보 값(A 같은 건물·면 종류 중앙값, B 같은 사전 정보·면 종류 전체 중앙값, C 원통 안 영상 점 표준편차)을 넣고 ① 한계 L 을 같은 식으로 다시 내어
① 같다·다르다와 판 4(v2 목표) 정확도가 어떻게 되는지 센다. 셈만, 판단 규칙·값은 바꾸지 않는다(참값은 채점에만).
대상: ① 값 없음 가운데 n ≥ 4, d 있음, 저장 L 없음이고 u_M 이 없는 패치. σ_P 가 없으면 후보를 넣어도 L 없음(값 없음 그대로).
① 같다 -> 두 자료, h_T = mvs_mean_m 높이 x σ_P²/(σ_P² + u²), τ_T = max(τ_P, τ_I) (목표 맞음은 target_check 로 새로 셈).
① 다르다 -> ③(①에서 온 시작 점, judgevis fuse, cons ≥ 4 영상): 저장 from1 이 있으면(need1) 그 값, 없으면 그 패치에만 새로 셈. 영상 -> 'cur'(없으면 v1 d), 사전 정보 -> 0.
사용: GT_STAGE=ga3 g24_uM_candidates.py"""
from common import *
import pandas as pd
import judge_lib as JL
import g8_score as G8
import target_check as TC
from target_check import J4, T4
A3 = json.loads((C/'judgeeval_v1_add3.json').read_text()); assert sha(C/'judgeeval_v1_add3.json') == json.loads((C/'judgeeval_v1_add3.lock.json').read_text())['config_sha256'], 'add3 config changed after lock'
TD = D/'tables/바'; CANDS = ['A', 'B', 'C']
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def Lcalc(u, S1): return 1.96*(np.sqrt(u**2 + S1['sigma_P']**2 + S1['sigma_W']**2) + np.abs(S1['r_m']))
def fuse_from1(prior, S1, rows):
    """rows(패치 차례)의 ①에서 온 시작 점을 fuse -> 패치마다 일관된 점 수(g6_step3 과 같은 규칙)."""
    N = len(S1['patch_index']); pos = -np.ones(int(S1['patch_index'].max()) + 1, np.int64); pos[S1['patch_index']] = np.arange(N); own = pos[S1['start_owner']]
    want = np.zeros(N, bool); want[rows] = True; m = want[own]; st = S1['starts'][m].astype(np.int32); o = own[m]
    if not len(st): return np.zeros(N), np.zeros(N), 0
    key = st[:, 0].astype(np.int64)*(1024*741) + st[:, 1]; uk, inv = np.unique(key, return_inverse=True); us = np.c_[(uk // (1024*741)).astype(np.int32), (uk % (1024*741)).astype(np.int32)]
    sb = O/'tmp'/f'fz_add3_{prior}.bin'; ob = O/'tmp'/f'fz_add3_{prior}.out'; np.ascontiguousarray(us, '<i4').tofile(sb)
    subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(us)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'), stderr=subprocess.DEVNULL)
    R = np.fromfile(ob, '<i4').reshape(-1, 3); sb.unlink(); ob.unlink(); cons = (R[inv, 0] == 1).astype(float)
    return np.bincount(o, weights=cons, minlength=N), np.bincount(o, minlength=N), len(us)
def main():
    c = cfg(); build_vis(); T = Timer(); rows = []; chk = dict(at=now(), scientific_verdict=None, add3_config_sha256=sha(C/'judgeeval_v1_add3.json'))
    old = pd.read_csv(D/'tables/마/t_v1_v2_diff.csv')
    for prior in PRIORS:
        d = G8.Data(prior, c); N = len(d.idx); S1 = d.S1; S3 = d.S3; F = loadz(O/'work'/STAGE/f'judge4_v2_{prior}.npz'); assert np.array_equal(F['patch_index'], d.idx)
        j4 = F['J4_판 4']; ok = F['ok_판 4']; tm = np.array([T4.get(int(x), -1) for x in d.t]); r1 = d.r1(); n = S1['n'][:, 2]; dd = S1['d_mean'][:, 2]; uM = S1['u_M']
        Lchk = Lcalc(uM, S1); fin = np.isfinite(S1['L_m']); chk.setdefault('L_recompute_max_diff', {})[prior] = float(np.nanmax(np.abs(Lchk[fin] - S1['L_m'][fin])))
        assert chk['L_recompute_max_diff'][prior] < 1e-9, 'L recompute differs'
        tgt = (r1 == JL.NONE) & (n >= 4) & np.isfinite(dd) & ~np.isfinite(S1['L_m']) & ~np.isfinite(uM)
        # 후보 값
        Pall = loadz(inp('patches', prior=prior), ['u_M', 'kind']); U = {}
        bA = pd.DataFrame(dict(b=d.building, k=d.kind, u=uM)).dropna().groupby(['b', 'k']).u.median(); U['A'] = np.array([bA.get((b, k), np.nan) for b, k in zip(d.building, d.kind)])
        mB = {k: float(np.nanmedian(Pall['u_M'][Pall['kind'] == k])) for k in np.unique(d.kind)}; U['B'] = np.array([mB[k] for k in d.kind]); U['C'] = S1['sd'][:, 2].astype(float)
        chk.setdefault('candidate_B', {})[prior] = {int(k): v for k, v in mB.items()}
        R1 = {}; aff_all = np.zeros(N, bool)
        for cn in CANDS:
            L = Lcalc(U[cn], S1); r = r1.copy(); g = tgt & np.isfinite(L); r[g] = np.where(np.abs(dd[g]) <= L[g], JL.SAME, JL.DIFF); R1[cn] = r; aff_all |= g & (r == JL.DIFF)
        new3 = aff_all & ~S3['need1']; cons_new, tot_new, nu = fuse_from1(prior, S1, np.flatnonzero(new3)); cons1 = np.where(S3['need1'], S3['from1_cons'], cons_new)
        chk.setdefault('step3_new', {})[prior] = dict(patches_with_stored_from1=int((aff_all & S3['need1']).sum()), patches_new=int(new3.sum()), unique_pixels=nu, new_without_start_points=int((new3 & (tot_new == 0)).sum()))
        # 목표: 같다 -> 섞음(후보 u), 다르다 -> 영상/사전 정보
        Hz = loadz(O/'work'/STAGE/f'heights_{prior}.npz'); nm = [str(x) for x in Hz['names']]; cur = Hz['H'][:, nm.index('cur')]; hb = np.where(np.isfinite(cur), cur, Hz['H'][:, nm.index('d_mean_2')])
        okI = np.where(np.isfinite(cur), Hz['ok'][:, nm.index('cur')], Hz['ok'][:, nm.index('d_mean_2')]); ok0 = Hz['ok'][:, nm.index('0')]
        sP2 = S1['sigma_P']**2; same_any = np.zeros(N, bool)
        for cn in CANDS: same_any |= tgt & (R1[cn] == JL.SAME)
        ii = np.flatnonzero(same_any); Hm = np.c_[[hb[ii]*sP2[ii]/(sP2[ii] + U[cn][ii]**2) for cn in CANDS]].T; tP = np.array([tauP(prior, k) for k in d.kind[ii]]); Tm = np.repeat(np.maximum(tP, tauI())[:, None], 3, 1)
        okS = np.zeros((N, 3), bool)
        if len(ii): o_, _ = TC.check(prior, d.idx[ii], Hm, Tm, 'add3'); okS[ii] = o_
        res = {'지금(판 4, v2)': (j4, ok, np.zeros(N, bool), r1)}
        for ci, cn in enumerate(CANDS):
            r = R1[cn]; j = j4.copy(); o = ok.copy(); g = tgt & (r != JL.NONE)
            s_ = g & (r == JL.SAME); j[s_] = 0; o[s_] = okS[s_, ci]
            df_ = g & (r == JL.DIFF); img = df_ & (cons1 >= 4); pri = df_ & ~(cons1 >= 4); j[img] = 1; o[img] = okI[img]; j[pri] = 3; o[pri] = ok0[pri]
            res[f'후보 {cn}'] = (j, o, g, r)
        for sn, sm in [('지붕', d.kind == 1), ('벽', d.kind == 2)]:
            if not sm.any(): continue
            for (vn, vm), (un, w) in G8.UV(d):
                if un == '점': continue
                for k, cnm in list(enumerate(J4)) + [(None, '전체(채점한 넓이)')]:
                    mm = sm & vm & ((tm == k) if k is not None else (tm >= 0)); tot = w[mm].sum()
                    if not tot: continue
                    base = None
                    for pn, (j, o, g, r) in res.items():
                        ja = 100*w[mm & (j == tm)].sum()/tot; ta = 100*w[mm & o].sum()/tot
                        if base is None: base = (ja, ta)
                        rows.append(dict(prior=PN[prior], surface=sn, version=vn, case=cnm, candidate=pn, case_area=tot, uM_missing_target_area=w[mm & tgt].sum(), changed_area=w[mm & g].sum(),
                                         step1_same_area=w[mm & g & (r == JL.SAME)].sum(), step1_diff_area=w[mm & g & (r == JL.DIFF)].sum(), still_none_area=w[mm & tgt & ~g].sum() if pn != '지금(판 4, v2)' else w[mm & tgt].sum(),
                                         diff_to_image_area=w[mm & g & (r == JL.DIFF) & (cons1 >= 4)].sum(), diff_to_prior_area=w[mm & g & (r == JL.DIFF) & ~(cons1 >= 4)].sum(),
                                         judgment_acc=ja, target_acc=ta, judgment_acc_now=base[0], target_acc_now=base[1], judgment_diff_pp=ja - base[0], target_diff_pp=ta - base[1], unit=un))
        # 첫 줄 = 묶음 마 판 4 v2
        for sn in (['지붕', '벽'] if prior == 'LoD2' else ['지붕']):
            for cnm in J4 + ['전체(채점한 넓이)']:
                a = [r_ for r_ in rows if r_['prior'] == PN[prior] and r_['surface'] == sn and r_['version'] == '전체' and r_['case'] == cnm and r_['candidate'] == '지금(판 4, v2)' and r_['unit'] == '넓이']
                if not a: continue
                o_ = old[(old.plan == '판 4') & (old.prior == PN[prior]) & (old.surface == sn) & (old.version == '전체') & (old.unit == '넓이') & (old.case == cnm)]
                assert np.isclose(a[0]['target_acc'], float(o_.target_acc_v2.iloc[0])), ('first row differs from 마', prior, sn, cnm)
        chk.setdefault('first_row_equals_ma', {})[prior] = True
        savez(O/'work'/STAGE/f'uM_candidates_{prior}.npz', patch_index=d.idx, target=tgt, **{f'u_{k}': U[k] for k in CANDS}, **{f'r1_{k}': R1[k] for k in CANDS}, cons1=cons1)
        print('CAND', prior, chk['step3_new'][prior], round(T.s()), flush=True)
    write('t8_uM_candidates', pd.DataFrame(rows), 't8: u_M 빈 패치(① 값 없음·n≥4·L 없음)에 후보 A·B·C 를 넣었을 때 ① 같다·다르다 넓이와 판 4(v2 목표) 판단 정확도(판정 넷)·목표 정확도, 지금 대비 %p. 첫 줄 = 묶음 마(점검 통과). 셈만, 판단 바꾸지 않음')
    chk['seconds'] = T.s(); dump(TD/'checks_2.json', chk); progress(f'덧붙임 3 2절 후보 셈: {jsafe(chk)}'); print(json.dumps(jsafe(chk), ensure_ascii=False))
if __name__ == '__main__': main()
