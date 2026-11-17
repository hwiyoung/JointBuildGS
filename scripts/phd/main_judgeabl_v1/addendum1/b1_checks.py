"""덧붙임 1 확인 1~4, 5의 1 (저장된 값만, 참값 없음). 사용: addendum1/b1_checks.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import poisson
TAB = D/'tables/addendum1'; TAB.mkdir(parents=True, exist_ok=True); A1 = O/'addendum1'; A1.mkdir(exist_ok=True)
W0 = PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
UNITS3 = [('LoD2', 1, 'LoD2 지붕'), ('LoD2', 2, 'LoD2 벽'), ('ALS', 1, '항공 LiDAR 지붕')]
QS = [.1, .25, .5, .75, .9]; RADII = [1.0, 1.5, 3.0]; BINS = np.arange(0, 6.0001, .25)
def acfg():
    lock = json.loads((C/'judgeabl_v1_addendum1.lock.json').read_text()); assert sha(C/'judgeabl_v1_addendum1.json') == lock['config_sha256']; return json.loads((C/'judgeabl_v1_addendum1.json').read_text())
def wqs(x, w, pre=''):
    m = np.isfinite(x) & np.isfinite(w) & (w > 0); return {f'{pre}q{int(q*100)}': (J.quantile(x[m], w[m], q) if m.any() else np.nan) for q in QS} | {f'{pre}n': int(m.sum())}
def write(name, df, note=''):
    df.to_csv(TAB/f'{name}.csv', index=False); (TAB/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df; lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False): lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.4g}' if isinstance(x, float) else str(x)) for x in r) + ' |')
    (TAB/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
def load(prior):
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'centre', 'kind', 'area', 'region', 'building', 'face', 'place', 'd_for_check', 'r_m', 'u_M', 'sigma_P', 'sigma_W', 'n', 'geometry', 'tiles', 'fit_count', 'fit_nmad', 'prior_height_m', 'mvs_mean_m'])
    ts = list(d['tiles']); pid, same, agree, extra = [], [], [], {k: [] for k in ['u10', 'u30', 'usf', 'p10', 'p30', 'psf']}
    for t in ts:
        g = loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'widen0_same_centre']); pid.append(g['patch_id']); same.append(g['widen0_same_centre'])
        agree.append(loadz(JC/'geometry/base'/f'{t}__{prior}.npz', ['agreement_for_calibration'])['agreement_for_calibration'])
        for v, a, b in [('ring_1.0', 'u10', 'p10'), ('ring_3.0', 'u30', 'p30'), ('same_face_ring', 'usf', 'psf')]:
            z = loadz(JC/'geometry'/v/f'{t}__{prior}.npz', ['u_M', 'sigma_P']); extra[a].append(z['u_M']); extra[b].append(z['sigma_P'])
    d['patch_id'] = np.concatenate(pid); d['same'] = np.concatenate(same); d['agree'] = np.concatenate(agree)
    for k, v in extra.items(): d[k] = np.concatenate(v)
    # WIDEN0 고리 값 (R1.5), 같은 중심 패치만
    cols = {k: np.full(len(d['n']), np.nan) for k in ['m_s0', 'm_nring', 'm_found', 'm_ninner', 'a_s0', 'a_nring', 'a_found', 'a_ninner']}
    pos = {s: i for i, s in enumerate(d['patch_id'])}
    for root in [W0/'patch_values', W0/'holdout/patch_values']:
        for f in sorted(root.glob(f'*__{prior}__R1.5.npz')):
            with np.load(f, allow_pickle=True) as z:
                if not len(z['patch_id']): continue
                ii = np.array([pos.get(s, -1) for s in z['patch_id']]); h = ii >= 0
                for pre, key in [('m', 'mvs_a'), ('a', 'als')]:
                    if f'{key}_s0' not in z.files: continue
                    for a, b in [('s0', 's0'), ('nring', 'n_ring'), ('found', 'ring_found'), ('ninner', 'n_inner_all')]: cols[f'{pre}_{a}'][ii[h]] = z[f'{key}_{b}'][h]
    for k, v in cols.items(): v[~d['same']] = np.nan; d[k] = v
    return d
def variogram(d, m, rng, max_pairs=2_000_000, anchors=3000):
    """같은 건물·같은 면의 패치 쌍, 3차원 중심 거리. e = d - r."""
    e = d['d_for_check'] - d['r_m']; idx = np.flatnonzero(m & np.isfinite(e))
    if len(idx) < 50: return None
    grp = pd.factorize(pd.Series(d['building'][idx]).astype(str) + '|' + pd.Series(d['face'][idx]).astype(str))[0]
    tree = cKDTree(d['centre'][idx]); an = rng.choice(len(idx), min(anchors, len(idx)), replace=False)
    nb = tree.query_ball_point(d['centre'][idx][an], 6.0); I, Jn = [], []
    for a, L in zip(an, nb):
        L = np.asarray(L); L = L[(grp[L] == grp[a]) & (L != a)]; I.append(np.full(len(L), a)); Jn.append(L)
    I = np.concatenate(I); Jn = np.concatenate(Jn)
    if len(I) > max_pairs: s = rng.choice(len(I), max_pairs, replace=False); I, Jn = I[s], Jn[s]
    dist = np.linalg.norm(d['centre'][idx][I] - d['centre'][idx][Jn], axis=1); diff = e[idx][I] - e[idx][Jn]
    return dist, diff
def semiv(dist, diff):
    rows = []
    for k in range(len(BINS) - 1):
        m = (dist >= BINS[k]) & (dist < BINS[k + 1]); x = diff[m]
        g = (1.4826*np.median(np.abs(x - np.median(x))))**2/2 if len(x) >= 30 else np.nan
        rows.append(dict(bin_lo=BINS[k], bin_mid=BINS[k] + .125, pairs=int(m.sum()), semivariance=g))
    df = pd.DataFrame(rows); pl = df[(df.bin_lo >= 4)]['semivariance'].mean()
    def first(frac):
        h = df[df.semivariance >= frac*pl]; return float(h.iloc[0]['bin_mid']) if len(h) else np.nan
    return df, dict(plateau=pl, L95=first(.95), L50=first(.5), first_over_plateau=df.iloc[0]['semivariance']/pl if pl else np.nan)
def main():
    cf = acfg(); T = Timer(); rng = np.random.default_rng(20261117)
    VG, VS, C1, C1R, ST, C2, C3, C4R, C4F, C4B, C5 = [], [], [], [], [], [], [], [], [], [], []
    P = {p: load(p) for p in ['LoD2', 'ALS']}; print('LOADED', round(T.s()), flush=True)
    jt = {(r['region'], r['prior'], r['kind']): r['t'] for r in json.loads((JC/'judge/base.json').read_text())['t_rows']}
    sw = float(json.loads((JC/'calib/base.json').read_text())['sigma_W_m'])
    # ---- 확인 1 (가) 반변동도
    Lc = {}
    for prior, kind, lab in UNITS3:
        d = P[prior]; inl = (d['geometry'] == 0) & (d['kind'] == kind); pool = []
        for reg in REGIONS + ['전체']:
            if reg == '전체':
                if not pool: continue
                dist = np.concatenate([x[0] for x in pool]); diff = np.concatenate([x[1] for x in pool])
            else:
                r = variogram(d, inl & (d['region'] == reg), rng)
                if r is None: continue
                dist, diff = r; pool.append(r)
            df, s = semiv(dist, diff); df.insert(0, 'region', reg); df.insert(0, 'unit', lab); VG.append(df)
            VS.append(dict(unit=lab, region=reg, pairs=len(dist), **s)); Lc[(lab, reg)] = s
    VS = pd.DataFrame(VS); print('VARIOGRAM', round(T.s()), flush=True)
    # ---- 확인 1 (나)(다) 그리고 맞는지
    for prior, kind, lab in UNITS3:
        d = P[prior]; inl = (d['geometry'] == 0) & (d['kind'] == kind); A = d['area']
        # (다) 면 경계까지 거리
        c = d['centre']; fin = np.isfinite(c).all(1); gk = pd.factorize(pd.Series(d['building']).astype(str) + '|' + pd.Series(d['face']).astype(str))[0].astype(float)
        X4 = np.c_[np.nan_to_num(c), gk*1e5]; tr = cKDTree(X4[fin]); cnt = np.zeros(len(c), int)
        cnt[fin] = tr.query_ball_point(X4[fin], .36, return_length=True) - 1; bnd = fin & (cnt < 8)
        dist_b = np.full(len(c), np.nan); dist_b[fin] = cKDTree(X4[bnd]).query(X4[fin])[0]
        d[f'dist_b'] = dist_b; print('BOUNDARY', lab, round(T.s()), flush=True)
        for ring, s0k, nk, fk, uk in [('영상 깊이 고리(u_M)', 'm_s0', 'm_nring', 'm_found', {1.0: 'u10', 1.5: 'u_M', 3.0: 'u30'})] + ([('항공 LiDAR 고리(σ_P)', 'a_s0', 'a_nring', 'a_found', {1.0: 'p10', 1.5: 'sigma_P', 3.0: 'p30'})] if prior == 'ALS' else []):
            for reg in REGIONS + ['전체']:
                rm = inl & ((d['region'] == reg) if reg != '전체' else np.isin(d['region'], REGIONS + ['none']))
                if not rm.any(): continue
                La = Lc.get(('항공 LiDAR 지붕', reg if reg != '전체' else '전체'), {}).get('L95', np.nan); Lown = Lc.get((lab, reg), {})
                L50 = Lown.get('L50', np.nan)
                for R in RADII:
                    s = d[s0k]; N = d[nk] if R == 1.5 else np.minimum(8000, d[fk]*(R**2 - .25)/(1.5**2 - .25))
                    sig = s/np.sqrt(N)*np.sqrt(1 + 4*.25/(R**2 + .25)); Neff = np.minimum(N, np.pi*(R**2 - .25)/L50**2) if np.isfinite(L50) and L50 > 0 else np.full(len(N), np.nan)
                    sige = s/np.sqrt(Neff)*np.sqrt(1 + 4*.25/(R**2 + .25)); u = d[uk[R]]
                    ca = (.5 + R)/2 >= La if np.isfinite(La) else False
                    has = rm & np.isfinite(sig) & np.isfinite(u); a_has = A[has].sum()
                    cb = has & (sig <= u/3); cbe = has & (sige <= u/3); cc = rm & (dist_b >= R)
                    row = dict(unit=lab, ring=ring, region=reg, R=R, patches=int(rm.sum()), area_m2=float(A[rm].sum()), ring_values_area_share=100*a_has/A[rm].sum(),
                               L95_image_error=La, L50_unit=L50, cond_a=bool(ca), cond_a_area_pct=100.0 if ca else 0.0,
                               cond_b_area_pct=100*A[cb].sum()/a_has if a_has else np.nan, cond_b_eff_area_pct=100*A[cbe].sum()/a_has if a_has else np.nan,
                               cond_c_area_pct=100*A[cc].sum()/A[rm].sum(), all_three_area_pct=100*A[has & cb & cc].sum()/a_has*(1 if ca else 0) if a_has else np.nan,
                               all_three_eff_area_pct=100*A[has & cbe & cc].sum()/a_has*(1 if ca else 0) if a_has else np.nan,
                               **wqs(sig, A*has, 'sigma_face_'), **{k: v for k, v in wqs(sig/u, A*has, 'sigma_over_u_').items() if not k.endswith('_n')}, **{k: v for k, v in wqs(sige/u, A*has, 'sigma_eff_over_u_').items() if not k.endswith('_n')})
                    if R == 1.5:
                        row.update(**{k: v for k, v in wqs(25*s, A*has, 's25_').items() if not k.endswith('_n')}, s25_le_1p5_area_pct=100*A[has & (25*s <= 1.5)].sum()/a_has if a_has else np.nan,
                                   s20_le_1p5_area_pct=100*A[has & (20*s <= 1.5)].sum()/a_has if a_has else np.nan)
                    C1.append(row)
            # 어느 반지름도 셋을 만족하지 못한 넓이와 까닭 (전체, N 그대로)
        for reg in REGIONS + ['전체']:
            rm = inl & ((d['region'] == reg) if reg != '전체' else np.ones(len(A), bool))
            if not rm.any(): continue
            C1R.append(dict(unit=lab, region=reg, **wqs(dist_b, A*rm, 'dist_boundary_'), dist_ge_1p5_area_pct=100*A[rm & (dist_b >= 1.5)].sum()/A[rm].sum(),
                            place_inside_area_pct=100*A[rm & (d['place'] == 0)].sum()/A[rm].sum(), dist_ge_1p5_and_inside_pct=100*A[rm & (dist_b >= 1.5) & (d['place'] == 0)].sum()/A[rm].sum()))
        # 5. 고리 크기에 따른 정밀도
        uk = 'u_M'
        for pl in [-1, 0, 1, 2]:
            m = inl & ((d['place'] == pl) if pl >= 0 else True)
            for nm, num in [('u_M(1.0)/u_M(1.5)', d['u10']), ('u_M(3.0)/u_M(1.5)', d['u30']), ('u_M(같은 면)/u_M(1.5)', d['usf'])]:
                ST.append(dict(unit=lab, place='모든 자리' if pl < 0 else PLACE[pl], ratio=nm, **wqs(num/d[uk], A*m)))
        print('C1', lab, round(T.s()), flush=True)
        # ---- 확인 2
        r0 = .075 if kind == 1 else .125
        for reg in REGIONS + ['전체']:
            m0 = (d['kind'] == kind) & np.isfinite(d['prior_height_m']) & ((d['region'] == reg) if reg != '전체' else True) & (d['n'] >= 0)
            rho = d['n']/(np.pi*r0**2); lam = 7.754
            for ver, m in [('n < 4 넣음', m0), ('n < 4 뺌', m0 & (d['n'] >= 4))]:
                q = wqs(rho, A*m, 'density_')
                C2.append(dict(unit=lab, region=reg, version=ver, radius_now_m=r0, **q, r_rule_at_q10_m=np.sqrt(lam/(np.pi*q['density_q10'])) if q['density_q10'] > 0 else np.inf,
                               r_rule_at_q50_m=np.sqrt(lam/(np.pi*q['density_q50'])) if q['density_q50'] > 0 else np.inf, n_lt4_area_pct=100*A[m0 & (d['n'] < 4)].sum()/A[m0].sum() if A[m0].sum() else np.nan,
                               **{k: v for k, v in wqs(d['n'].astype(float), A*m, 'n_').items() if not k.endswith('_n')}))
        # ---- 확인 3
        Lend = 10. if kind == 1 else 5.
        for reg in REGIONS + ['전체']:
            m = (d['kind'] == kind) & (d['n'] >= 4) & np.isfinite(d['d_for_check']) & ((d['region'] == reg) if reg != '전체' else True)
            if not m.any(): continue
            ad = np.abs(d['d_for_check'])
            C3.append(dict(unit=lab, region=reg, half_length_m=Lend, patches=int(m.sum()), q90=J.quantile(ad[m], A[m], .9), q99=J.quantile(ad[m], A[m], .99), q999=J.quantile(ad[m], A[m], .999), max=float(ad[m].max()),
                           within_1m_of_end_area_pct=100*A[m & (ad >= Lend - 1)].sum()/A[m].sum(), wall_10m='확인 불가(저장 값 없음)' if kind == 2 else ''))
        # ---- 확인 4
        for reg in REGIONS + ['전체']:
            rm = inl & ((d['region'] == reg) if reg != '전체' else True)
            if not rm.any(): continue
            has = rm & np.isfinite(d['m_found'])
            for nm, x, edges in [('고리 점 수(찾은 수)', d['m_found'], [20, 40, 80, 160, np.inf]), ('안쪽 점 수', d['m_ninner'], [5, 10, 20, 40, np.inf])]:
                for a, b in zip(edges[:-1], edges[1:]):
                    m = has & (x >= a) & (x < b)
                    C4R.append(dict(unit=lab, region=reg, count=nm, bin=f'{a:g}~{b:g}', area_pct=100*A[m].sum()/A[has].sum() if A[has].sum() else np.nan, **{k: v for k, v in wqs(d['u_M'], A*m, 'u_M_').items()}))
                m = has & (x < edges[1]); C4R.append(dict(unit=lab, region=reg, count=nm, bin='문턱 가까이', area_pct=100*A[m].sum()/A[has].sum() if A[has].sum() else np.nan))
            fm = rm & np.isfinite(d['fit_count'])
            for a, b in [(20, 40), (40, 80), (80, np.inf)]:
                m = fm & (d['fit_count'] >= a) & (d['fit_count'] < b)
                C4F.append(dict(unit=lab, region=reg, fit_points=f'{a:g}~{b:g}', area_pct=100*A[m].sum()/A[fm].sum() if A[fm].sum() else np.nan, **wqs(d['fit_nmad'], A*m, 'fit_nmad_')))
        e = d['d_for_check'] - d['r_m']; am = d['agree'] & (d['kind'] == kind) & np.isfinite(e); df = pd.DataFrame(dict(b=d['building'][am], e=e[am], a=A[am], reg=d['region'][am]))
        for b, q in df.groupby('b'):
            nb_ = len(q); nm_ = 1.4826*np.median(np.abs(q.e - q.e.median())); se = 1.2533*nm_/np.sqrt(nb_); reg = q.reg.iloc[0]
            L50 = Lc.get((lab, reg), {}).get('L50', np.nan); neff = min(nb_, q.a.sum()/L50**2) if np.isfinite(L50) and L50 > 0 else np.nan
            C4B.append(dict(unit=lab, building=b, region=reg, n_b=nb_, nmad_m=nm_, se_m=se, n_eff=neff, se_eff_m=1.2533*nm_/np.sqrt(neff) if np.isfinite(neff) and neff > 0 else np.nan,
                            n_needed=(1.2533*nm_/(sw/3))**2, meets_100=nb_ >= 100, se_le_sw3=se <= sw/3))
    # ---- 확인 5의 1
    for prior, kind, lab in UNITS3:
        Ph = loadz(JP/f'photo_{prior}.npz', ['kind', 'area', 'region', 'all_within', 's_P', 'texture'])
        rk = np.where(np.isin(Ph['region'], REGIONS), Ph['region'], 'none'); tt = np.array([jt.get((r, prior, kind), np.nan) for r in rk]); tex = Ph['texture'][:, 0]
        edges = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, np.inf]
        for reg in REGIONS + ['전체']:
            m0 = (Ph['kind'] == kind) & Ph['all_within'] & np.isfinite(Ph['s_P']) & np.isfinite(tex) & ((rk == reg) if reg != '전체' else True); A_ = Ph['area']
            if not m0.any(): continue
            rows = []
            for a, b in zip(edges[:-1], edges[1:]):
                m = m0 & (tex >= a) & (tex < b); n = A_[m].sum()
                rows.append(dict(unit=lab, region=reg, texture_bin=f'{a:g}~{b:g}', lo=a, area_pct=100*n/A_[m0].sum(), points=int(m.sum()), **{k: v for k, v in wqs(Ph['s_P'], A_*m, 's_P_').items() if not k.endswith('_n')},
                                 below_t_pct=100*A_[m & (Ph['s_P'] < tt)].sum()/n if n else np.nan))
            df = pd.DataFrame(rows); ok = (df['below_t_pct'] < 10) | (df['points'] == 0)
            thr = next((float(df.lo[i]) for i in range(len(df)) if ok.iloc[i:].all() and df.points.iloc[i] > 0), np.nan)
            df['rule1_threshold'] = thr; df['textureless_area_pct_now'] = 100*A_[m0 & (tex < 5)].sum()/A_[m0].sum(); C5.append(df)
    out = dict(variogram_bins=(pd.concat(VG), '확인 1 (가): 한계 안 패치 (d − r), 같은 건물·같은 면의 쌍, 구간마다 강건 반변동도 (m²).'),
               variogram_summary=(VS, '확인 1 (가): 고원(4~6 m 평균), 95 %·50 %에 처음 닿는 거리(구간 가운데, m), 첫 구간 ÷ 고원.'),
               check1_conditions=(pd.DataFrame(C1), '확인 1: 바깥 반지름마다 (가) 고리 가운데 반지름 ≥ 항공 LiDAR 지붕(영상 깊이 오차)의 95 % 닮는 거리, (나) σ_면 ≤ u/3 (N 그대로·N_유효), (다) 면 경계까지 ≥ R 의 넓이 비율. 고리 값은 WIDEN0 같은 중심 패치만(ring_values_area_share). R 1.0·3.0 의 N 은 넓이 비로 어림.'),
               check1_boundary=(pd.DataFrame(C1R), '확인 1 (다): 패치 중심에서 같은 면의 경계 패치(0.36 m 안 같은 면 이웃 < 8)까지 거리(m). JC 자리 면 안쪽과 비교.'),
               check1_stability=(pd.DataFrame(ST), '확인 1의 5: 한계 안 패치의 u_M 비 (JC ring_1.0, ring_3.0, same_face_ring ÷ base).'),
               check2_cylinder_radius=(pd.DataFrame(C2), '확인 2: 영상 깊이 점 밀도 n ÷ 원통 단면적(점/m²), 규칙 반지름 = P(포아송 ≥ 4) = 0.95 (λ = 7.754).'),
               check3_cylinder_length=(pd.DataFrame(C3), '확인 3: n ≥ 4 패치의 |d| (m), 길이 끝 1 m 안 넓이 비율. 벽 10 m 원통은 캠퍼스 패치에 저장 값 없음.'),
               check4_ring_counts=(pd.DataFrame(C4R), '확인 4: 한계 안 패치, WIDEN0 같은 중심 패치의 고리 점 수(찾은 수)·안쪽 점 수 구간마다 넓이 비율과 u_M (m).'),
               check4_fit_counts=(pd.DataFrame(C4F), '확인 4: 영상 깊이 면 맞춤 점 수 구간마다 넓이 비율, 맞춤 잔차 NMAD (m). 한계 안 패치(사진 점 값).'),
               check4_buildings=(pd.DataFrame(C4B), f'확인 4: 건물마다 일치 핵심점(agreement_for_calibration) n_b, (d − r) NMAD, 중앙값 표준 오차, 유효 표본 수, σ_W/3 ({sw/3:.4f} m) 에 필요한 n.'),
               check5_texture=(pd.concat(C5), '확인 5의 1: 한계 안 사진 점, 무늬 세기(사전 정보 쪽) 구간마다 넓이 비율, s_P 분위, s_P < t 비율, 규칙 1 문턱.'))
    for k, (df, note) in out.items(): write(k, df, note)
    b = pd.DataFrame(C4B); summ = b.groupby('unit').agg(buildings=('n_b', 'size'), n_needed_q50=('n_needed', 'median'), n_needed_q90=('n_needed', lambda x: x.quantile(.9)), meets_100_pct=('meets_100', 'mean'), se_le_sw3_pct=('se_le_sw3', 'mean')).reset_index()
    write('check4_buildings_summary', summ, '확인 4 건물 요약.')
    np.savez(A1/'boundary_dist.npz', **{p: P[p]['dist_b'] for p in P})
    progress(f'덧붙임 1 확인 1~5의 1 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
