"""셈 1-1~1-4. 저장된 판정·목표·참값 점만 읽는다(학습·새 광도 점수·새 기하 없음). 참값은 처음 상태, 채점, '참값으로' 판(구조 상한·상한 2)에만.
사용: js1_count.py <prior>"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import pandas as pd
import a1_variants as A1


def main(prior):
    cf = cfg(); T = Timer(); OUT = O/prior; OUT.mkdir(parents=True, exist_ok=True)
    d = A1.load(prior); x = loadz(JP/f'patch_{prior}.npz', ['building', 'place', 'case', 'mixed'])
    N = len(d['kind']); A = d['area']; mi = J.VARIANTS.index('method'); hP, hM, u = d['prior_height_m'], d['mvs_mean_m'], d['u_M']
    valid = np.isfinite(hP) & np.isfinite(d['normal']).all(1); n = d['n']; geom = d['geometry']
    missing = valid & (n >= 0) & (n < 4); inside = valid & (geom == 0)
    sig = valid & (n >= 4) & (geom == 1); nolim = valid & (n >= 4) & ~np.isfinite(d['L_m'])
    rb = d['j_region'][:, mi].copy(); hb = d['target_h'][:, mi]
    pz = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz'); pc = pz['pc'].astype(int); assert len(pc) == N
    CHK = []; NOTE = {}
    NOTE['sets'] = dict(sig=int(sig.sum()), nolim=int(nolim.sum()), sig_and_nolim=int((sig & nolim).sum()), sig_without_mvs_height=int((sig & ~np.isfinite(hM)).sum()),
                        nolim_without_mvs_height=int((nolim & ~np.isfinite(hM)).sum()), nolim_geom=dict(zip(*[v.tolist() for v in np.unique(geom[nolim], return_counts=True)])),
                        sig_base_region=dict(zip(*[v.tolist() for v in np.unique(rb[sig], return_counts=True)])), nolim_base_region=dict(zip(*[v.tolist() for v in np.unique(rb[nolim], return_counts=True)])),
                        inside_and_nolim=int((inside & nolim).sum()))
    assert not (sig & nolim).any()
    tgt = lambda reg: J.target_height(reg, hP, hM, u, d['sigma_P'], d['sigma_W']).astype(np.float64)
    hb_re = tgt(rb); CHK.append(dict(prior=prior, check='본 방법 목표 다시 냄 = 저장 값', equal_pct=100*float(np.mean((hb_re == hb) | (np.isnan(hb_re) & np.isnan(hb)))), n=N))
    # ---- 판 (판정)
    lo = rb.copy(); lo[sig] = 2
    nl2 = nolim & np.isfinite(hM); lo_b = lo.copy(); lo_b[nl2] = 2
    E = sig & (pc == 2); Oth = sig & ~E
    up = lo.copy(); up[E] = 1
    allP = lo.copy(); allP[sig] = 1          # 차이가 유의한 패치 모두 사전정보 사용 (셈 1-4의 끝점, 판이 아님)
    # ---- 참값 점
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'building', 'target_ok_v', 'region_v'])
    paired = g['paired']; gid_all = g['gid']; case_all = g['case']
    keep = np.flatnonzero(paired & np.isin(case_all, CASES)); gid = gid_all[keep]; cs = case_all[keep]; Ng = len(keep)
    ok0 = g['target_ok_v'][mi][keep]; xyz = g['xyz'][keep]; nor = g['normal'][keep]; wall = g['gt_kind'][keep] == 2; tau = g['tau'][keep]; gb = g['building'][keep]
    po = g['target_ok_v'][0][keep]; io = g['target_ok_v'][1][keep]
    pkind = d['kind'][gid]; exp_reg = np.array([MATCH[c] for c in CASES])[np.searchsorted(CASES, cs)]
    def score(h):
        hc = ~((h == hb) | (np.isnan(h) & np.isnan(hb))); ok = ok0.copy(); sel = np.flatnonzero(hc[gid]); pg = gid[sel]
        if len(sel): ds = plane_distance(xyz[sel], nor[sel], d['centre'][pg], d['normal'][pg], h[pg], wall[sel]); ok[sel] = np.abs(ds) <= tau[sel]
        return ok
    ok_b = score(hb); CHK.append(dict(prior=prior, check='본 방법 점 채점 = JC 저장 값', equal_pct=100*float(np.mean(ok_b == ok0)), n=Ng))
    H = {'구조 하한': tgt(lo), '구조 하한 (나)': tgt(lo_b), '구조 상한': tgt(up), '모두 사전정보 사용': tgt(allP)}
    OK = {k: score(h) for k, h in H.items()}
    okI = OK['구조 하한']; okP = OK['모두 사전정보 사용']
    # 구조 상한 2: 패치 안 네 경우 참값 점(>= 3) 가운데 영상 깊이 목표 τ 안 < 0.5, 사전 정보 목표 τ 안 >= 0.5
    in_sig = sig[gid]; cntp = np.bincount(gid[in_sig], minlength=N); nI = np.bincount(gid[in_sig], weights=okI[in_sig], minlength=N); nP = np.bincount(gid[in_sig], weights=okP[in_sig], minlength=N)
    with np.errstate(invalid='ignore', divide='ignore'): U2 = sig & (cntp >= 3) & (nI/np.maximum(cntp, 1) < .5) & (nP/np.maximum(cntp, 1) >= .5)
    up2 = lo.copy(); up2[U2] = 1; H['구조 상한 2'] = tgt(up2); OK['구조 상한 2'] = score(H['구조 상한 2'])
    REG = {'본 방법': rb, '구조 하한': lo, '구조 하한 (나)': lo_b, '구조 상한': up, '구조 상한 2': up2, '모두 사전정보 사용': allP}
    OK['본 방법'] = ok_b
    NOTE['upper2'] = dict(patches=int(U2.sum()), area_m2=float(A[U2].sum()), of_which_state=dict(zip(*[v.tolist() for v in np.unique(pc[U2], return_counts=True)])),
                          image_error_patches=int(E.sum()), image_error_area_m2=float(A[E].sum()), overlap_patches=int((U2 & E).sum()), overlap_area_m2=float(A[U2 & E].sum()))
    # 검산 3 바탕: 구조 상한 = 구조 하한 에서 E 의 점만 사전정보 쪽
    inE = E[gid]; CHK.append(dict(prior=prior, check='구조 상한 점 = (E 밖 구조 하한, E 안 모두 사전정보 사용)', equal_pct=100*float(np.mean(OK['구조 상한'] == np.where(inE, okP, okI))), n=Ng))
    # 식별 1 비교 (검산 4)
    pos = {s: i for i, s in enumerate(d['patch_id'])}; id1 = np.full(N, -1, np.int16)
    for r in REGIONS + ['none']:
        p = JABL/'variants'/f'{r}__{prior}.npz'
        if not p.exists(): continue
        with np.load(p) as v:
            vn = [str(s) for s in v['variants']]; ii = np.array([pos[s] for s in v['patch_id']]); id1[ii] = v['region'][vn.index('식별 1 없음·영상 깊이 사용')]
    assert (id1 >= 0).all()
    ID1 = []
    for nm, reg in [('구조 하한', lo), ('구조 하한 (나)', lo_b)]:
        df_ = reg != id1; ID1.append(dict(prior=prior, variant=nm, same_patch_pct=100*float(1 - df_.mean()), same_area_pct=100*float(1 - A[df_].sum()/A.sum()), diff_patches=int(df_.sum()), diff_area_m2=float(A[df_].sum())))
        if df_.any():
            why = pd.DataFrame(dict(sig=sig[df_], nolim=nolim[df_], geom=geom[df_], has_uM=np.isfinite(u[df_]), has_L=np.isfinite(d['L_m'][df_]), has_mvs=np.isfinite(hM[df_]), base=rb[df_], id1=id1[df_], this=reg[df_], area=A[df_]))
            w = why.groupby(['sig', 'nolim', 'geom', 'has_uM', 'has_L', 'has_mvs', 'base', 'id1', 'this']).agg(patches=('area', 'size'), area_m2=('area', 'sum')).reset_index()
            w.insert(0, 'variant', nm); w.insert(0, 'prior', prior); w.to_csv(OUT/f'id1_diff_{nm}.csv', index=False)
    # ---- 패치 단위
    same = cs == pc[gid]; valid_pc = np.isin(pc, CASES)
    def pok_of(ok):
        num = np.bincount(gid[same], weights=ok[same], minlength=N); den = np.bincount(gid[same], minlength=N); return (den > 0) & (num/np.maximum(den, 1) >= .5)
    POK = {k: pok_of(v) for k, v in OK.items()}
    exp_p = np.full(N, -1); exp_p[valid_pc] = [MATCH[int(c)] for c in pc[valid_pc]]
    # ---- 표 3.2/3.3: 구조 판 줄
    bu, bidx = np.unique(gb, return_inverse=True)
    ROWS = []
    for vn in ['본 방법', '구조 하한', '구조 하한 (나)', '구조 상한', '구조 상한 2']:
        ok = OK[vn]; reg = REG[vn]; rg = reg[gid]; pk = POK[vn]
        for sn, kk in SURF[prior]:
            kp = np.isin(pkind, kk); km = np.isin(d['kind'], kk); row = dict(prior=prior, surface=sn, variant=vn)
            for c in CASES:
                m = kp & (cs == c); row[f'n_{CASE[c]}'] = int(m.sum()); row[f'ok_{CASE[c]}'] = 100*ok[m].mean(); row[f'name_{CASE[c]}'] = 100*(rg[m] == exp_reg[m]).mean()
                mp = km & (pc == c); a = A[mp].sum(); row[f'patch_ok_{CASE[c]}'] = 100*A[mp & pk].sum()/a; row[f'patch_name_{CASE[c]}'] = 100*A[mp & (reg == exp_p)].sum()/a
            row['ok_전체'] = 100*ok[kp].mean(); mp = km & valid_pc; row['patch_ok_전체'] = 100*A[mp & pk].sum()/A[mp].sum()
            row['changed_area_m2'] = float(A[km & (reg != rb)].sum()); row['changed_patches'] = int((km & (reg != rb)).sum())
            # 건물 x 경우 칸 (>= 200 점) 이 판 - 본 방법 의 중앙값
            bc = bidx[kp]*4 + np.searchsorted(CASES, cs[kp]); nb = np.bincount(bc, minlength=len(bu)*4); v1 = np.bincount(bc, weights=ok[kp], minlength=len(bu)*4); v0 = np.bincount(bc, weights=ok_b[kp], minlength=len(bu)*4)
            cell = nb >= 200; dl = 100*(v1[cell] - v0[cell])/nb[cell]
            row['building_cells'] = int(cell.sum()); row['building_diff_median_pp'] = float(np.median(dl)) if len(dl) else np.nan
            row['building_base_better_cells'] = int((dl < 0).sum()); row['building_base_worse_cells'] = int((dl > 0).sum())
            ROWS.append(row)
    pd.DataFrame(ROWS).to_csv(OUT/'rows.csv', index=False)
    # ---- 셈 1-1: 처음 상태
    pl = x['place']; reg_name = np.where(np.isin(d['region'], REGIONS), d['region'], 'none'); pb = x['building']
    paired_rows = np.flatnonzero(paired); pg_all = gid_all[paired_rows]; pcase_all = case_all[paired_rows]; pkind_all = d['kind'][pg_all]
    IS = []
    for setname, S in [('차이가 유의한 패치', sig), ('한계가 없는 패치', nolim)]:
        splits = [('전체', '전체', np.ones(N, bool))] + [('탐색 지역', r, reg_name == r) for r in REGIONS + ['none']] + [('자리', PLACE[k], pl == k) for k in [0, 1, 2]]
        for sn, kk in SURF[prior]:
            km = np.isin(d['kind'], kk)
            for spn, spv, spm in splits:
                m = S & km & spm; row = dict(prior=prior, surface=sn, set=setname, split=spn, split_value=spv, patches=int(m.sum()), area_m2=float(A[m].sum()))
                st = m & np.isin(pc, STATE_ORDER); a_st = A[st].sum(); row['area_with_state_m2'] = float(a_st)
                for s_ in STATE_ORDER: mm = m & (pc == s_); row[f'n_{STATE[s_]}'] = int(mm.sum()); row[f'area_pct_{STATE[s_]}'] = 100*A[mm].sum()/a_st if a_st else np.nan
                for s_ in [-2, -3, -9]: row[f'n_{STATE[s_]}'] = int((m & (pc == s_)).sum()); row[f'area_{STATE[s_]}_m2'] = float(A[m & (pc == s_)].sum())
                row['check_sum'] = row['patches'] == sum(row[f'n_{STATE[s_]}'] for s_ in STATE_ORDER + [-2, -3, -9])
                pm = m[pg_all]; npts = int(pm.sum()); row['gt_points'] = npts
                for c in CASES: row[f'pt_pct_{CASE[c]}'] = 100*(pm & (pcase_all == c)).sum()/npts if npts else np.nan
                row['pt_pct_네 경우 밖'] = 100*(pm & ~np.isin(pcase_all, CASES)).sum()/npts if npts else np.nan
                IS.append(row)
    pd.DataFrame(IS).to_csv(OUT/'t11_initial_state.csv', index=False)
    # 건물마다
    BB = []
    for sn, kk in SURF[prior]:
        km = np.isin(d['kind'], kk); m = sig & km
        ub, bi = np.unique(pb[m], return_inverse=True); At = np.bincount(bi, weights=A[m]); st = np.isin(pc[m], STATE_ORDER); Ast = np.bincount(bi, weights=A[m]*st, minlength=len(ub))
        for b_, name in enumerate(ub):
            r = dict(prior=prior, surface=sn, building=str(name), sig_area_m2=float(At[b_]), area_with_state_m2=float(Ast[b_]))
            for s_ in STATE_ORDER:
                v = np.bincount(bi, weights=A[m]*(pc[m] == s_), minlength=len(ub))[b_]; r[f'area_pct_{STATE[s_]}'] = 100*v/Ast[b_] if Ast[b_] else np.nan
            BB.append(r)
    pd.DataFrame(BB).to_csv(OUT/'t11_by_building_rows.csv', index=False)
    # 닿는 범위
    cat = np.full(N, 4, np.int8); cat[missing] = 3; cat[nolim] = 2; cat[inside] = 0; cat[sig] = 1
    CATN = {1: '차이가 유의한 패치', 0: '한계 안(일치)', 2: '한계가 없는 패치', 3: '영상 깊이 점 4개 미만', 4: '그 밖'}
    RE = []
    for sn, kk in SURF[prior]:
        kp = np.isin(pkind, kk)
        for c in CASES:
            m = kp & (cs == c); row = dict(prior=prior, surface=sn, case=CASE[c], gt_points=int(m.sum()))
            for k_ in [1, 0, 2, 3, 4]: row[f'pct_{CATN[k_]}'] = 100*(m & (cat[gid] == k_)).sum()/m.sum() if m.sum() else np.nan
            ms = m & sig[gid]; row['차이가 유의한 패치 안: 처음 상태 영상 깊이 오류 패치 %'] = 100*(ms & E[gid]).sum()/ms.sum() if ms.sum() else np.nan
            for s_, lab_ in [(0, '두 자료 모두 유효'), (1, '사전정보 오류')]: row[f'차이가 유의한 패치 안: 처음 상태 {lab_} 패치 %'] = 100*(ms & (pc[gid] == s_)).sum()/ms.sum() if ms.sum() else np.nan
            other = m & (cat[gid] == 4); row['그 밖 = 유효하지 않음'] = int((other & ~valid[gid]).sum()); row['그 밖 = n>=4, MVS 높이 없음·한계 안팎 아님'] = int((other & valid[gid]).sum())
            RE.append(row)
    pd.DataFrame(RE).to_csv(OUT/'t11_reach.csv', index=False)
    # JUDGEPROBE 검산 (지붕, 한계 밖, 사전정보 오류 대 영상 깊이 오류)
    JPC_ = []
    for sn, kk in SURF[prior]:
        km = np.isin(d['kind'], kk); base = km & (geom == 1)
        a1_, a2_ = int((base & (x['case'] == 1) & ~x['mixed']).sum()), int((base & (x['case'] == 2) & ~x['mixed']).sum())
        b1_, b2_ = int((sig & km & (pc == 1)).sum()), int((sig & km & (pc == 2)).sum()); ar1, ar2 = float(A[sig & km & (pc == 1)].sum()), float(A[sig & km & (pc == 2)].sum())
        JPC_.append(dict(prior=prior, surface=sn, jp_rule_prior_err_patches=a1_, jp_rule_image_err_patches=a2_, jp_rule_ratio=f'{100*a1_/(a1_+a2_):.1f} : {100*a2_/(a1_+a2_):.1f}' if a1_ + a2_ else '',
                         state_prior_err_patches=b1_, state_image_err_patches=b2_, state_ratio_patches=f'{100*b1_/(b1_+b2_):.1f} : {100*b2_/(b1_+b2_):.1f}' if b1_ + b2_ else '',
                         state_ratio_area=f'{100*ar1/(ar1+ar2):.1f} : {100*ar2/(ar1+ar2):.1f}' if ar1 + ar2 else ''))
    pd.DataFrame(JPC_).to_csv(OUT/'t11_jp_check.csv', index=False)
    # ---- 셈 1-4: 패치마다 덧셈 값
    GR = []
    for sn, kk in SURF[prior]:
        kp = np.isin(pkind, kk); km = np.isin(d['kind'], kk); e = dict(prior=prior, surface=sn)
        for c in CASES:
            m = kp & (cs == c); e[f'n_{CASE[c]}'] = int(m.sum()); e[f'lo_{CASE[c]}'] = float(okI[m].sum()); e[f'base_{CASE[c]}'] = float(ok_b[m].sum())
            e[f'dE_{CASE[c]}'] = float((okP[m & inE].astype(int) - okI[m & inE].astype(int)).sum()); inO = Oth[gid]; e[f'dO_{CASE[c]}'] = float((okP[m & inO].astype(int) - okI[m & inO].astype(int)).sum())
            mp = km & (pc == c); e[f'pa_{CASE[c]}'] = float(A[mp].sum()); e[f'plo_{CASE[c]}'] = float(A[mp & POK['구조 하한']].sum()); e[f'pbase_{CASE[c]}'] = float(A[mp & POK['본 방법']].sum())
            pI, pP = POK['구조 하한'], POK['모두 사전정보 사용']
            e[f'pdE_{CASE[c]}'] = float((A*(pP.astype(int) - pI.astype(int)))[mp & E].sum()); e[f'pdO_{CASE[c]}'] = float((A*(pP.astype(int) - pI.astype(int)))[mp & Oth].sum())
        e['A_E'] = float(A[km & E].sum()); e['A_O'] = float(A[km & Oth].sum()); e['A_O_state'] = float(A[km & Oth & np.isin(pc, STATE_ORDER)].sum())
        e['E_patches'] = int((km & E).sum()); e['O_patches'] = int((km & Oth).sum())
        GR.append(e)
    dump(OUT/'grid_terms.json', dict(rows=GR, scientific_verdict=None))
    # 그림용
    np.savez(OUT/'fig_arrays.npz', sig=sig, nolim=nolim, pc=pc, E=E, U2=U2, lo=lo, up=up, rb=rb, keep=keep, ok_b=np.packbits(ok_b), ok_lo=np.packbits(okI), ok_up=np.packbits(OK['구조 상한']), n=Ng)
    dump(OUT/'js1.json', dict(at=now(), prior=prior, patches=N, gt_points=Ng, checks=CHK, notes=NOTE, id1=ID1, seconds=T.s(), scientific_verdict=None))
    for c in CHK + ID1: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False), flush=True)
    progress(f'js1 {prior} 끝: 패치 {N:,}, 참값 점 {Ng:,}, 차이가 유의한 패치 {int(sig.sum()):,}, {round(T.s())} 초')
if __name__ == '__main__': main(sys.argv[1])
