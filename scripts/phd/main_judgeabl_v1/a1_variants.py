"""3절(기존 1·2·3·5, 기존 4 세 실험 지역)과 4.1~4.5 판: 판정·목표를 저장된 값으로 내고 JC 2.5 규칙으로 채점한다.
판정과 기준에는 참값을 쓰지 않는다. 참값은 경우, 목표 맞음, 5 % 확인(JC s8 규칙)에만. 사용: a1_variants.py <prior>"""
from common import *
import pandas as pd
DROP = [7, 6, 4, 5, 9]          # 광도 결과 차례 1~4 (+ 셈 안 함) -> 기본 판정


def load(prior):
    keys = ['tile', 'kind', 'area', 'n', 'geometry', 'prior_height_m', 'mvs_mean_m', 'mvs_sd_m', 'normal', 'centre', 'u_M', 'sigma_P', 'sigma_W', 'r_m', 'L_m', 'd_for_check',
            'photo_code', 's_P', 's_M', 't', 'j_region', 'j_reason', 'target_h', 'region', 'texture_P', 'texture_M', 'nsel_P', 'nsel_M', 'mvs_available', 'tiles']
    d = loadz(JP/f'patch_{prior}.npz', keys); ts = list(d['tiles']); N = len(d['kind'])
    free = np.zeros(N, bool); gt_p = np.full(N, np.nan); pid = []
    for ti, t in enumerate(ts):
        m = np.flatnonzero(d['tile'] == ti)
        si = loadz(JC/'sight'/f'{t}__{prior}.npz', ['free5', 'free10']); free[m] = np.where(d['kind'][m] == 1, si['free10'], si['free5'])
        gp = JC/'truth/gt_patch'/f'{t}__{prior}.npz'
        if gp.exists(): gt_p[m] = loadz(gp, ['gt_p'])['gt_p']
        pid.append(loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id'])['patch_id'])
        assert len(pid[-1]) == len(m) and np.array_equal(m, np.arange(m[0], m[0] + len(m)))
    d['free'] = free; d['gt_p'] = gt_p; d['patch_id'] = np.concatenate(pid)
    tau = json.loads((JC/'stage0/tau.json').read_text())['values']
    key = lambda k: prior + ('_wall' if k == 2 else '_roof') if prior == 'LoD2' else 'ALS_roof'
    d['tau_p'] = np.array([tau.get(r, tau['none'])[key(k)] for r, k in zip(d['region'], d['kind'])])
    return d


def photo_refs(prior, d, cfgd):
    """사진 점(JP photo) 에서 t 와 같은 표본으로 t_q, (s_M - s_P) 의 5 %/95 %, 분위 비교 기준 분포. 참값 없음."""
    P = loadz(JP/f'photo_{prior}.npz', ['kind', 'area', 'region', 'all_within', 's_P', 's_M'])
    qs = cfgd['baselines_section3']['old3']['sweep_q']; kinds = [1, 2] if prior == 'LoD2' else [1]; ref = {}; rows = []
    for kind in kinds:
        for reg in REGIONS + ['none']:
            base = (P['kind'] == kind) & P['all_within']; pool = base & (P['region'] == reg) if reg != 'none' else base & (P['region'] != 'none')
            rs = [SEED_T, REGIONS.index(reg) if reg != 'none' else 7, 0 if prior == 'LoD2' else 1, kind]
            t, _, ch = J.threshold(P['s_P'], P['area'], pool, rs); w = P['area'][ch]
            sp, sm = P['s_P'][ch], P['s_M'][ch]; df = sm - sp
            e = dict(t=t, tq={q: J.quantile(sp, w, q) for q in qs}, c_lo=J.quantile(df, w, .05), c_hi=J.quantile(df, w, .95))
            for nm, x in [('P', sp), ('M', sm)]:
                ok = np.isfinite(x) & (w > 0); o = np.argsort(x[ok], kind='stable'); e[f'cdf_{nm}'] = (x[ok][o], np.cumsum(w[ok][o])/max(w[ok].sum(), 1e-12))
            ref[(reg, kind)] = e
            rows.append(dict(prior=prior, kind='지붕' if kind == 1 else '벽', region=reg, t=t, **{f't_q{int(q*100)}': v for q, v in e['tq'].items()}, c_lo=e['c_lo'], c_hi=e['c_hi'],
                             pool_count=int(pool.sum()), sample_count=len(ch), sample_finite_diff=int(np.isfinite(df).sum())))
    rk = np.where(np.isin(d['region'], REGIONS), d['region'], 'none')
    def per_patch(f):
        out = np.full(len(rk), np.nan)
        for (reg, kind), e in ref.items():
            m = (rk == reg) & (d['kind'] == kind); out[m] = f(e, m)
        return out
    return ref, rows, per_patch


def main(prior):
    cf = cfg(); T = Timer(); d = load(prior); N = len(d['kind']); dflt = 1 if prior == 'ALS' else 2
    mi = J.VARIANTS.index('method'); A = d['area']; hP = d['prior_height_m']; hM = d['mvs_mean_m']; u = d['u_M']; dd = d['d_for_check']; pc = d['photo_code']
    valid = np.isfinite(hP) & np.isfinite(d['normal']).all(1); missing = valid & (d['n'] >= 0) & (d['n'] < 4); present = valid & (d['n'] >= 4) & np.isfinite(hM)
    geom = d['geometry']; inside = valid & (geom == 0); nou = present & (geom == 9) & ~np.isfinite(u); outside = (valid & (geom == 1)) | nou
    spa = np.isfinite(d['s_P']) & (d['nsel_P'] >= 3) & (d['texture_P'] >= 5)
    sma = np.isfinite(d['s_M']) & d['mvs_available'] & (d['nsel_M'] >= 3) & (d['texture_M'] >= 5)
    ref, trows, per_patch = photo_refs(prior, d, cf)
    t5 = per_patch(lambda e, m: e['t']); fin = np.isfinite(d['t'])
    CHK = [dict(prior=prior, check='사진 점에서 다시 낸 t = 패치의 저장된 t', equal_pct=100*float(np.mean((t5[fin] == d['t'][fin]))), n=int(fin.sum()))]
    NOTES = {}

    def tgt(reg, agree_nan_mean=False):
        h = J.target_height(reg, hP, hM, u, d['sigma_P'], d['sigma_W'])
        m = (reg == 0) & ~np.isfinite(h) & np.isfinite(hP) & np.isfinite(hM)
        if agree_nan_mean: h[m] = .5*(hP[m] + hM[m])
        return h, float(A[m].sum())

    def assemble(inside_m, out_m, rule, miss='base'):
        reg = np.full(N, 9, np.int8); why = np.full(N, 9, np.int8)
        if miss == 'base': reg[missing] = 4; reg[missing & d['free']] = 3
        elif miss == 'all4': reg[missing] = 4
        elif miss == 'all3': reg[missing] = 3
        r, w = rule(out_m); reg[out_m] = r[out_m]; why[out_m] = w[out_m]; reg[inside_m] = 0
        return reg, why

    def photo_base(m):
        r = np.full(N, dflt, np.int8); w = np.full(N, 2, np.int8)
        r[pc == 0] = 1; w[pc == 0] = 0; r[pc == 1] = 2; w[pc == 1] = 1; return r, w

    def cmp_rule(go_image, go_prior, why_code=4, keep_default=None):
        def f(m):
            r = np.full(N, dflt, np.int8); w = np.full(N, 2, np.int8)
            r[go_prior] = 1; w[go_prior] = why_code; r[go_image] = 2; w[go_image] = why_code
            if keep_default is not None: r[keep_default] = dflt; w[keep_default] = 2
            return r, w
        return f

    V = {}   # name -> (reg, why, h, meta)
    def add(name, reg, why, h, **meta): V[name] = (reg, why, h.astype(np.float64), meta)
    # 본값 다시 냄
    reg, why = assemble(inside, outside, photo_base); h, _ = tgt(reg)
    CHK.append(dict(prior=prior, check='본값 판정 다시 냄 = JC 본 방법', equal_pct=100*float(np.mean(reg == d['j_region'][:, mi])), n=N))
    hb = d['target_h'][:, mi]; CHK.append(dict(prior=prior, check='본값 목표 다시 냄 = JC 본 방법', equal_pct=100*float(np.mean((h == hb) | (np.isnan(h) & np.isnan(hb)))), n=N))
    assert (reg == d['j_region'][:, mi]).all()
    for nm, j in [('본 방법', mi), ('사전 정보 단독', 0), ('영상 단독', 1), ('기하 일관성 검사 단독', 2), ('광도 일관성 검사 단독', 3), ('유보 2 기본 판정의 반대', 5), ('패치 다수결 상한', 7)]:
        add(nm, d['j_region'][:, j], d['j_reason'][:, j], d['target_h'][:, j], stored=True)
    # ---- 3절 기존 방법
    def present_rule(go_image, why_code):
        def f(m):
            r = np.full(N, 1, np.int8); w = np.full(N, why_code, np.int8); r[go_image] = 2; return r, w
        return f
    none_in = np.zeros(N, bool); absd = np.abs(dd)
    for T_ in cf['baselines_section3']['old1']['sweep_T_m']:
        reg, why = assemble(none_in, present, present_rule(absd > T_, 3), miss='all4'); add(f'기존 1 T={T_:g} m', reg, why, tgt(reg)[0], family='old1', value=T_)
    root = np.sqrt(u**2 + d['sigma_P']**2 + d['sigma_W']**2)
    for k in cf['baselines_section3']['old2']['sweep_k']:
        Lk = k*(root + np.abs(d['r_m'])); gi = np.isfinite(Lk) & (absd > Lk)
        reg, why = assemble(none_in, present, present_rule(gi, 3), miss='all4'); why[present & ~np.isfinite(Lk)] = 2
        add(f'기존 2 배수 {k:g}', reg, why, tgt(reg)[0], family='old2', value=k, L_missing_area_m2=float(A[present & ~np.isfinite(Lk)].sum()))
    gi = np.isfinite(d['L_m']) & (absd > d['L_m']); reg, why = assemble(none_in, present, present_rule(gi, 3), miss='all4'); why[present & ~np.isfinite(d['L_m'])] = 2
    add('기존 2 대표(저장된 L)', reg, why, tgt(reg)[0], family='old2_rep', L_missing_area_m2=float(A[present & ~np.isfinite(d['L_m'])].sum()))
    for q in cf['baselines_section3']['old3']['sweep_q']:
        tq = per_patch(lambda e, m, q=q: e['tq'][q]); gi = spa & np.isfinite(tq) & (d['s_P'] < tq)
        reg, why = assemble(none_in, present, present_rule(gi, 4), miss='all4'); add(f'기존 3 아래 {q*100:g} %', reg, why, tgt(reg)[0], family='old3', value=q)
    for nm, LT in [('기존 5 T=0.5 m', np.full(N, .5)), ('기존 5 T=L', d['L_m'])]:
        gi = np.isfinite(LT) & (absd > LT) & spa & np.isfinite(d['t']) & (d['s_P'] < d['t'])
        reg, why = assemble(none_in, present, present_rule(gi, 3), miss='all4'); add(nm, reg, why, tgt(reg)[0], family='old5', L_missing_area_m2=float(A[present & ~np.isfinite(LT)].sum()))
    # ---- 4.1 검출
    five = []
    def five_pct(name, dv, Lv):
        ok = (d['n'] >= 4) & np.isfinite(d['gt_p']) & np.isfinite(hP) & np.isfinite(hM)
        cell0 = ok & (np.abs(hP - d['gt_p']) <= d['tau_p']) & (np.abs(hM - d['gt_p']) <= d['tau_p'])
        for kn, km in ([('지붕', d['kind'] == 1), ('벽', d['kind'] == 2)] if prior == 'LoD2' else [('지붕', d['kind'] == 1)]):
            m = cell0 & km & np.isfinite(Lv) & np.isfinite(dv); a = float(A[m].sum()); o = m & (np.abs(dv) > Lv)
            five.append(dict(prior=prior, variant=name, surface=kn, cell0_area_m2=a, outside_area_m2=float(A[o].sum()), outside_pct=100*float(A[o].sum())/a if a else np.nan, cell0_patches=int(m.sum())))
    five_pct('본 방법', dd, d['L_m'])
    rk = np.where(np.isin(d['region'], REGIONS), d['region'], 'none'); det3_m = np.full(N, np.nan); det3_L = np.full(N, np.nan); det3_rows = []
    for kind in ([1, 2] if prior == 'LoD2' else [1]):
        for reg_ in REGIONS + ['none']:
            pool = present & np.isfinite(dd) & (d['kind'] == kind) & ((d['region'] == reg_) if reg_ != 'none' else np.isin(d['region'], REGIONS))
            m_, s_ = nmad_w(dd[pool], A[pool]); tg = (rk == reg_) & (d['kind'] == kind); det3_m[tg] = m_; det3_L[tg] = 1.96*s_
            det3_rows.append(dict(prior=prior, kind='지붕' if kind == 1 else '벽', region=reg_, median_d_m=m_, nmad_m=s_, limit_m=1.96*s_, pool_patches=int(pool.sum())))
    u4 = d['mvs_sd_m']/np.sqrt(np.maximum(d['n'], 1)); u4[d['n'] < 1] = np.nan
    DET = [('검출 1 고정 문턱 0.5 m', dd, np.full(N, .5)), ('검출 2 고정 문턱 1.0 m', dd, np.full(N, 1.)), ('검출 3 지역 하나의 한계', dd - det3_m, det3_L),
           ('검출 4 원통 흩어짐', dd, 1.96*(np.sqrt(u4**2 + d['sigma_P']**2 + d['sigma_W']**2) + np.abs(d['r_m']))),
           ('검출 5 σ_W 뺌', dd, 1.96*(np.sqrt(u**2 + d['sigma_P']**2) + np.abs(d['r_m']))), ('검출 6 r 뺌', dd, 1.96*root), ('검출 7 σ_P 뺌', dd, 1.96*(np.sqrt(u**2 + d['sigma_W']**2) + np.abs(d['r_m'])))]
    for nm, dv, Lv in DET:
        gv = np.full(N, 9, np.int8); ok = valid & (d['n'] >= 4) & np.isfinite(dv) & np.isfinite(Lv)
        gv[ok & (np.abs(dv) <= Lv)] = 0; gv[ok & (np.abs(dv) > Lv)] = 1
        ins = valid & (gv == 0); out = (valid & (gv == 1)) | (present & (gv == 9) & ~np.isfinite(u))
        reg, why = assemble(ins, out, photo_base); h, amean = tgt(reg, agree_nan_mean=True)
        add(nm, reg, why, h, family='det', agree_without_uM_area_m2=amean, outside_area_m2=float(A[valid & (gv == 1)].sum()), inside_area_m2=float(A[ins].sum()))
        five_pct(nm, dv, Lv)
    # ---- 4.2 식별
    sP, sM, t = d['s_P'], d['s_M'], d['t']; drop = np.isin(pc, DROP)
    ID = [('식별 1 없음·영상 깊이 사용', lambda m: (np.full(N, 2, np.int8), np.full(N, 5, np.int8))),
          ('식별 2 없음·사전정보 사용', lambda m: (np.full(N, 1, np.int8), np.full(N, 5, np.int8))),
          ('식별 3 사전 정보 면만', cmp_rule(spa & np.isfinite(t) & (sP < t), spa & np.isfinite(t) & (sP >= t))),
          ('식별 4 영상 깊이 면만', cmp_rule(sma & np.isfinite(t) & (sM >= t), sma & np.isfinite(t) & (sM < t)))]
    clo = per_patch(lambda e, m: e['c_lo']); chi = per_patch(lambda e, m: e['c_hi']); df_ = sM - sP
    ID.append(('식별 5 두 점수의 차이', cmp_rule(~drop & (df_ > chi), ~drop & (df_ < clo))))
    ID.append(('식별 6 두 점수의 크기', cmp_rule(~drop & (sM > sP), ~drop & ~(sM > sP))))
    qP = np.full(N, np.nan); qM = np.full(N, np.nan)
    for (reg_, kind), e in ref.items():
        m = (rk == reg_) & (d['kind'] == kind)
        for nm_, x, q in [('P', sP, qP), ('M', sM, qM)]:
            xs, cw = e[f'cdf_{nm_}']
            if len(xs): ix = np.searchsorted(xs, x[m], 'right'); q[m] = np.where(ix > 0, cw[np.maximum(ix - 1, 0)], 0.)
    ID.append(('식별 7 분위 비교', cmp_rule(~drop & (qM > qP), ~drop & ~(qM > qP))))
    for nm, rule in ID:
        reg, why = assemble(inside, outside, rule); add(nm, reg, why, tgt(reg)[0], family='id')
    na = loadz(JP/f'na_{prior}.npz', ['region_new', 'reason_new', 'target_h_new']); add('식별 8 t_M', na['region_new'], na['reason_new'], na['target_h_new'], family='id')
    # ---- 4.3 유보
    def ab1(m):
        r, w = photo_base(m); bl = np.isin(pc, [2, 3]); r[bl & (sM > sP)] = 2; r[bl & ~(sM > sP)] = 1; w[bl] = 4; return r, w
    reg, why = assemble(inside, outside, ab1); add('유보 1 없음', reg, why, tgt(reg)[0], family='ab')
    # ---- 4.4 처리
    rb = d['j_region'][:, mi]; wb = d['j_reason'][:, mi]
    for nm, src in [('처리 1 일치는 사전 정보 높이', hP), ('처리 2 일치는 영상 깊이 높이', hM)]:
        h = hb.copy(); h[rb == 0] = src[rb == 0]; add(nm, rb, wb, h, family='pr')
    # ---- 4.5 가시성
    for nm, miss in [('가시성 1 모두 결측', 'all4'), ('가시성 2 모두 제거', 'all3')]:
        reg, why = assemble(inside, outside, photo_base, miss=miss); add(nm, reg, why, tgt(reg)[0], family='vis')
    # ---- 4.6 참고 줄 (a4_lr.py 가 만든 판정; 참값으로 학습)
    if (O/f'lr_{prior}.npz').exists():
        z = loadz(O/f'lr_{prior}.npz', ['region', 'reason', 'target_h']); add('참고 참값으로 학습한 결합', z['region'], z['reason'], z['target_h'], family='ref')
    # ---- 덧붙임 1 확인 9 (b9_variants.py; 고정 값을 바꾼 판, JC 민감도 판)
    if (O/f'extra_variants_{prior}.npz').exists():
        z = np.load(O/f'extra_variants_{prior}.npz')
        for k, nm in enumerate(z['names']): add(str(nm), z['region'][k], z['reason'][k], z['target_h'][k], family='fix')
    print('VARIANTS', prior, len(V), round(T.s()), flush=True)

    # ================= 채점 (참값)
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'patch_kind', 'group', 'place', 'textureless', 'building', 'src', 'site', 'target_ok_v', 'region_v', 'target_distance_v'])
    keep = np.flatnonzero(g['paired'] & np.isin(g['case'], CASES)); G = {k: v[..., keep] if k in ('target_ok_v', 'region_v', 'target_distance_v') else v[keep] for k, v in g.items()}; del g
    gid = G['gid']; Ng = len(gid); ci = np.searchsorted(CASES, G['case']); ki = (G['patch_kind'] == 2).astype(int)
    gi = (G['group'] == 'experiment').astype(int); pi = np.clip(G['place'] + 1, 0, 3); xi = np.clip(G['textureless'] + 1, 0, 2)
    # 기존 4 세 실험 지역 (JA decisions region[4], 지금 판 짝)
    f3 = np.zeros(Ng, bool); f_reg = np.full(Ng, -1, np.int8); f_dist = np.full(Ng, np.nan); FCHK = []
    gall = loadz(JC/'analysis'/f'gt_{prior}.npz', ['src', 'site']); gx = None
    for site in SITES:
        z = loadz(JC/'truth/exp'/f'{site}__{prior}.npz', ['xyz', 'current_patch_id']); rows = np.flatnonzero((G['src'] == 1) & (G['site'] == site))
        allrows = np.flatnonzero((gall['src'] == 1) & (gall['site'] == site))
        if gx is None: gx = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz'])['xyz']
        assert len(allrows) == len(z['xyz']) and np.allclose(gx[allrows], z['xyz']), ('truth/exp alignment', site)
        pos_in_site = np.searchsorted(allrows, keep[rows]); assert np.array_equal(allrows[pos_in_site], keep[rows])
        dec = loadz(JA/'decisions'/f'{site}__{prior}.npz', ['patch_id', 'region', 'centre', 'normal', 'prior_height_m', 'mvs_mean_m', 'area'])
        look = {s: i for i, s in enumerate(dec['patch_id'])}; cp = z['current_patch_id'][pos_in_site]
        fi = np.array([look.get(s, -1) for s in cp]); h = fi >= 0; rr = rows[h]; pj = fi[h]
        fr = dec['region'][4][pj]; hh = np.where(fr == 2, dec['mvs_mean_m'][pj], np.where(fr == 1, dec['prior_height_m'][pj], np.nan))
        dist = plane_distance(G['xyz'][rr], G['normal'][rr], dec['centre'][pj], dec['normal'][pj], hh, G['gt_kind'][rr] == 2)
        f3[rr] = True; f_reg[rr] = fr; f_dist[rr] = dist
        FCHK.append(dict(prior=prior, site=site, gt_rows_all=len(allrows), gt_rows=len(rows), with_JA_patch=int(h.sum()), fusion_image_area_m2=float(dec['area'][dec['region'][4] == 2].sum()), fusion_prior_area_m2=float(dec['area'][dec['region'][4] == 1].sum())))
    del gall, gx
    code = ((((ci*2 + ki)*2 + gi)*4 + pi)*3 + xi)*2 + f3.astype(int); NC = 4*2*2*4*3*2
    bu, bidx = np.unique(G['building'], return_inverse=True); bcode = bidx*8 + ci*2 + ki
    ok0 = G['target_ok_v'][mi]; d0 = G['target_distance_v'][mi]; po = G['target_ok_v'][0]; io = G['target_ok_v'][1]
    exp_reg = np.array([MATCH[c] for c in CASES])[ci]; ncell = np.bincount(code, minlength=NC); nb = np.bincount(bcode, minlength=len(bu)*8)
    CROSS, BLD, TRN, P44 = [], [], [], []; OKBITS = {}
    def score(name, reg, h, stored_j=None):
        if stored_j is not None: ok = G['target_ok_v'][stored_j].copy(); dist = G['target_distance_v'][stored_j].astype(float); rg = G['region_v'][stored_j]
        else:
            hc = ~((h == hb) | (np.isnan(h) & np.isnan(hb))); ok = ok0.copy(); dist = d0.astype(float).copy(); sel = np.flatnonzero(hc[gid]); pg = gid[sel]
            if len(sel):
                ds = plane_distance(G['xyz'][sel], G['normal'][sel], d['centre'][pg], d['normal'][pg], h[pg], G['gt_kind'][sel] == 2); ok[sel] = np.abs(ds) <= G['tau'][sel]; dist[sel] = ds
            rg = reg[gid]
        return ok, dist, rg
    def record(name, ok, dist, rg, fam, patch_reg=None):
        CROSS.append(dict(variant=name, family=fam, ok=np.bincount(code, weights=ok, minlength=NC), name=np.bincount(code, weights=(rg == exp_reg), minlength=NC), made=np.bincount(code, weights=~ok & (po | io), minlength=NC)))
        if fam != 'old4_3':
            BLD.append(dict(variant=name, ok=np.bincount(bcode, weights=ok, minlength=len(bu)*8)))
        c0 = ci == 0
        for sn, sm in ([('지붕', ki == 0), ('벽', ki == 1), ('모두', np.ones(Ng, bool))] if prior == 'LoD2' else [('지붕', ki == 0)]):
            x = np.abs(dist[c0 & sm]); x = x[np.isfinite(x)]
            P44.append(dict(prior=prior, variant=name, surface=sn, n_case0=int((c0 & sm).sum()), n_finite=len(x), abs_dist_median_m=float(np.median(x)) if len(x) else np.nan,
                            abs_dist_nmad_m=float(1.4826*np.median(np.abs(x - np.median(x)))) if len(x) else np.nan))
        OKBITS[name] = np.packbits(ok)
        if patch_reg is not None:
            tr = np.bincount(((d['kind'] - 1)*100 + rb.astype(int)*10 + patch_reg.astype(int)), weights=A, minlength=200)
            for kk in range(2):
                for a in range(10):
                    for b in range(10):
                        v = tr[kk*100 + a*10 + b]
                        if v > 0 and a != b: TRN.append(dict(prior=prior, variant=name, kind='지붕' if kk == 0 else '벽', from_judgment=JUD.get(a, str(a)), to_judgment=JUD.get(b, str(b)), area_m2=float(v)))
    stored_j = {'본 방법': mi, '사전 정보 단독': 0, '영상 단독': 1, '기하 일관성 검사 단독': 2, '광도 일관성 검사 단독': 3, '유보 2 기본 판정의 반대': 5, '패치 다수결 상한': 7}
    for name, (reg, why, h, meta) in V.items():
        ok, dist, rg = score(name, reg, h, stored_j.get(name)); fam = meta.get('family', 'stored')
        if name == '본 방법':
            ok_chk, _, _ = score(name, reg, h); CHK.append(dict(prior=prior, check='본값 목표 맞음 다시 셈 = JC 저장 값', equal_pct=100*float(np.mean(ok_chk == ok)), n=Ng))
        if name in ('식별 1 없음·영상 깊이 사용', '식별 2 없음·사전정보 사용'):
            CHK.append(dict(prior=prior, check=f'{name} = JC 기하 일관성 검사 단독 (판정, 목표 맞음)', equal_pct=100*float(np.mean(reg == d['j_region'][:, 2])), equal_ok_pct=100*float(np.mean(ok == G['target_ok_v'][2])), n=N))
        if name == '기존 2 배수 1.96':
            r2 = V['기존 2 대표(저장된 L)'][0]; CHK.append(dict(prior=prior, check='기존 2 배수 1.96 = 기존 2 대표(저장된 L) 판정', equal_pct=100*float(np.mean(reg == r2)), n=N))
        if name == '유보 1 없음' or name.startswith('식별'):
            pass
        record(name, ok, dist, rg, fam, patch_reg=reg)
        NOTES[name] = {k: v for k, v in meta.items()}
        NOTES[name]['changed_area_m2'] = float(A[reg != rb].sum()); NOTES[name]['changed_patches'] = int((reg != rb).sum())
    # 기존 4 세 실험 지역
    okf = np.abs(f_dist) <= G['tau']; okf[~f3] = False; rgf = np.where(f3, f_reg, -1)
    record('기존 4 결합(세 실험 지역)', okf, np.where(f3, f_dist, np.nan), rgf, 'old4_3'); NOTES['기존 4 결합(세 실험 지역)'] = dict(family='old4_3', scope='세 실험 지역 GT rows with a JUDGEAPPLY patch', sites=FCHK)
    # 쓰기
    dims = []
    for c in range(NC):
        r = c; f = r % 2; r //= 2; x = r % 3; r //= 3; p = r % 4; r //= 4; gg = r % 2; r //= 2; k = r % 2; r //= 2; cc = r
        dims.append(dict(case=CASE[CASES[cc]], kind='지붕' if k == 0 else '벽', group='세 실험 지역' if gg else '나머지', place={0: '없음', 1: '면 안쪽', 2: '면 경계', 3: '건물 가장자리'}[p], textureless={0: '없음', 1: '무늬 있음', 2: '무늬 없음'}[x], fusion3=bool(f), n=int(ncell[c])))
    dimdf = pd.DataFrame(dims); out = []
    for e in CROSS:
        df = dimdf.copy(); df['variant'] = e['variant']; df['family'] = e['family']; df['ok'] = e['ok']; df['name_ok'] = e['name']; df['made'] = e['made']; out.append(df[df['n'] > 0])
    pd.concat(out).assign(prior=prior).to_csv(O/f'cross_{prior}.csv', index=False)
    brows = []
    for e in BLD:
        for b in range(len(bu)):
            for c in range(4):
                for k in range(2):
                    j = b*8 + c*2 + k
                    if nb[j]: brows.append(dict(prior=prior, variant=e['variant'], building=bu[b], case=CASE[CASES[c]], kind='지붕' if k == 0 else '벽', n=int(nb[j]), ok=float(e['ok'][j])))
    pd.DataFrame(brows).to_csv(O/f'building_{prior}.csv', index=False)
    pd.DataFrame(TRN).to_csv(O/f'trans_{prior}.csv', index=False); pd.DataFrame(P44).to_csv(O/f'process44_{prior}.csv', index=False); pd.DataFrame(five).to_csv(O/f'five_{prior}.csv', index=False)
    np.savez(O/f'okbits_{prior}.npz', names=np.array(list(OKBITS)), bits=np.stack(list(OKBITS.values())), n=Ng, keep=keep)
    pd.DataFrame(trows).to_csv(O/f'photo_refs_{prior}.csv', index=False); pd.DataFrame(det3_rows).to_csv(O/f'det3_{prior}.csv', index=False)
    dump(O/f'a1_{prior}.json', dict(at=now(), prior=prior, patches=N, gt_points=Ng, variants=list(V) + ['기존 4 결합(세 실험 지역)'], checks=CHK, fusion3=FCHK, notes=NOTES, seconds=T.s(), scientific_verdict=None))
    # 패치마다 판별 판정 (탐색 지역마다)
    names = list(V); (O/'variants').mkdir(exist_ok=True)
    for reg_ in REGIONS + ['none']:
        m = np.flatnonzero(d['region'] == reg_)
        if not len(m): continue
        np.savez(O/'variants'/f'{reg_}__{prior}.npz', patch_id=d['patch_id'][m], variants=np.array(names), region=np.stack([V[n][0][m] for n in names]).astype(np.int8),
                 reason=np.stack([V[n][1][m] for n in names]).astype(np.int8), target_h=np.stack([V[n][2][m] for n in names]).astype(np.float32))
    for c in CHK: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False), flush=True)
    progress(f'a1 {prior} 끝: 판 {len(V) + 1}개, 참값 점 {Ng}, {round(T.s())} 초')
if __name__ == '__main__': main(sys.argv[1])
