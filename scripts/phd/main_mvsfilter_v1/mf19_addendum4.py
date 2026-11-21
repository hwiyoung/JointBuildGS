"""덧붙임 4(11/22): 차이가 유의한 패치를 차이의 크기 |d| 와 경계 T 로 나눔. 학습·새 광도 점수·새 화소 셈 없음, CPU. 판에는 참값을 쓰지 않음.
대상 = 차이가 유의한 패치(지금 점군), 그 밖은 구조 하한 그대로.
  큰 차이(|d| ≥ T): 영상 깊이 사용, 덧붙임 3 판 다(combo_D)가 되돌리는 패치만 사전정보 사용.
  작은 차이(|d| < T): 처리 P = 사전정보 사용(1), 처리 W = 일치(0) 와 같은 목표(정밀도 가중 평균, jc2_judge.target_height 의 region 0 그대로).
T: 고정 0.3·0.5·0.75·1.0·1.5·2.0 m, 한계의 배수 2L·3L·5L(패치마다 L_m), 혼합 경계(log|d| 에 정규 분포 둘을 넓이 가중 EM 으로 맞춤, 사전 정보·지붕/벽마다).
혼합 경계 = 작은 무리 평균 위에서 큰 무리(평균이 큰 쪽)의 사후 확률이 작은 무리보다 처음 커지는 log|d| (격자 20,000 점). 자료 최솟값부터 찾은 값도 json 에 적음.
판 열 가지 × 처리 둘 = 스무 판, 모두 세션 판(T 를 고르지 않음).
사용: mf19_addendum4.py tables | figs <prior>"""
import sys, gzip, io
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mf11_check as M11
from mf11_check import *
from jscommon import *
from common import wq, PLACE
import js3_figs as J3
import mf18_addendum3 as M18
DOCT = Path('/docs/tables'); DOCF = Path('/docs/figures')
FIXED = [.3, .5, .75, 1., 1.5, 2.]; MULT = [2, 3, 5]
TS = [(f'T = {t:g} m', ('fixed', t)) for t in FIXED] + [(f'T = {k} L', ('mult', k)) for k in MULT] + [('T = 혼합 경계', ('mix', None))]
QS = [.1, .25, .5, .75, .9]
SESSION0 = {('항공 LiDAR', '두 자료 모두 유효'): [.08, .10, .15, .33, 2.38], ('항공 LiDAR', '사전정보 오류'): [1.82, 3.73, 4.34, 4.95, 5.77], ('항공 LiDAR', '영상 깊이 오류'): [.19, .27, .49, 1.26, 2.85],
            ('LoD2', '두 자료 모두 유효'): [.39, .52, .76, 2.04, 4.63], ('LoD2', '사전정보 오류'): [.65, .88, 1.44, 3.25, 4.64], ('LoD2', '영상 깊이 오류'): [.58, .81, 1.45, 2.33, 3.22]}
KN = {1: '지붕', 2: '벽'}

def gmm2(x, w, iters=2000, tol=1e-12):
    """넓이 가중 EM, 정규 분포 둘. 시작 = 가중 25 %·75 % 값, 가중 표준 편차, 무게 반반."""
    w = w/w.sum(); mu = np.array([wq(x, w, .25), wq(x, w, .75)]); s0 = np.sqrt(np.sum(w*(x - np.sum(w*x))**2)); sd = np.array([s0, s0]); pi = np.array([.5, .5]); ll0 = -np.inf
    for it in range(iters):
        p = np.stack([pi[k]*np.exp(-.5*((x - mu[k])/sd[k])**2)/(sd[k]*np.sqrt(2*np.pi)) for k in range(2)]); tot = p.sum(0); ll = np.sum(w*np.log(np.maximum(tot, 1e-300)))
        r = p/np.maximum(tot, 1e-300); rw = r*w; nk = rw.sum(1); pi = nk; mu = (rw*x).sum(1)/nk; sd = np.sqrt((rw*(x - mu[:, None])**2).sum(1)/nk); sd = np.maximum(sd, 1e-6)
        if abs(ll - ll0) < tol: break
        ll0 = ll
    o = np.argsort(mu); mu, sd, pi = mu[o], sd[o], pi[o]
    g = np.linspace(x.min(), x.max(), 20000); post = [pi[k]*np.exp(-.5*((g - mu[k])/sd[k])**2)/sd[k] for k in range(2)]; big = post[1] > post[0]
    a = np.flatnonzero(big & (g >= mu[0])); b0 = np.flatnonzero(big)
    return dict(mu_log=mu.tolist(), sd_log=sd.tolist(), weight=pi.tolist(), iters=it + 1, loglik=float(ll), boundary_log=float(g[a[0]]) if len(a) else np.nan, boundary_m=float(np.exp(g[a[0]])) if len(a) else np.nan,
                boundary_from_min_m=float(np.exp(g[b0[0]])) if len(b0) else np.nan, mu_m=np.exp(mu).tolist())

def base4(prior):
    S, d, sig, lo0, flipA2, pres, stored, F, ck = M18.base3(prior); N = len(d['kind'])
    x = loadz(JP/f'patch_{prior}.npz', ['d_m', 'place', 'building']); dabs = np.abs(x['d_m']); L = d['L_m']
    with np.errstate(divide='ignore', invalid='ignore'): ratio = dabs/L
    MIX = {}; Tmix = np.full(N, np.nan)
    for k in ([1, 2] if prior == 'LoD2' else [1]):
        m = sig & (d['kind'] == k) & (dabs > 0); MIX[KN[k]] = dict(gmm2(np.log(dabs[m]), S['A'][m]), patches=int(m.sum()), area_m2=float(S['A'][m].sum()))
        Tmix[d['kind'] == k] = MIX[KN[k]]['boundary_m']
    return S, d, sig, lo0, flipA2, pres, F, dabs, L, ratio, Tmix, MIX, x

def Tof(spec, L, Tmix, N):
    kind, v = spec
    if kind == 'fixed': return np.full(N, v)
    if kind == 'mult': return v*L
    if kind == 'mix': return Tmix
    return np.full(N, v)

def panel_lo(lo0, sig, da, dabs, T, treat):
    with np.errstate(invalid='ignore'): big = sig & (dabs >= T)
    small = sig & ~big; lo = lo0.copy(); lo[big & da] = 1; lo[small] = 1 if treat == 'P' else 0
    return lo, small

def f1(v): return '' if v is None or not np.isfinite(v) else f'{v:.1f}'

def tables_mode():
    T_ = Timer(); RM, CK, DIST, SMALL, SPL, BLD = [], [], [], [], [], []; MIXALL = {}
    t6 = pd.read_csv(DOCT/'t6_rejudge.csv'); t11 = pd.read_csv(DOCT/'t11_combo.csv'); mi = J.VARIANTS.index('method')
    for prior in ['LoD2', 'ALS']:
        S, d, sig, lo0, flipA2, pres, F, dabs, L, ratio, Tmix, MIX, x = base4(prior); A = S['A']; pc = S['pc']; N = len(A); gp = np.bincount(S['gid'], minlength=N); MIXALL[prior] = MIX; da = F['da']
        # 읽은 값 대조: 판 다 = 묶음 나4 combo_D_returned
        cd = pd.read_csv(MC.O/'judge'/f'patches3_{prior}.csv.gz', usecols=['combo_D_returned'])['combo_D_returned'].values.astype(bool)
        CK.append(dict(prior=PN[prior], check='판 다 되돌림 = 묶음 나4 패치 열 combo_D_returned', equal=int((cd == da).sum()), patches=N, passed=bool(np.array_equal(cd, da))))
        nou = int((sig & ~np.isfinite(d['u_M'])).sum()); CK.append(dict(prior=PN[prior], check='차이가 유의한 패치 가운데 u_M 없음(처리 W 의 무게를 못 셈)', patches=nou, passed=nou == 0))
        CK.append(dict(prior=PN[prior], check='차이가 유의한 패치 가운데 |d| 또는 L 없음', d_missing=int((sig & ~np.isfinite(dabs)).sum()), L_missing=int((sig & ~np.isfinite(L)).sum()), d_zero=int((sig & (dabs == 0)).sum())))
        bm = t6[(t6.prior == PN[prior]) & (t6.line == '본 방법 (JUDGESTRUCT-v1)')].set_index('surface')
        def add(lo, label, key, extra, changed=None):
            rows, _ = summary(S, prior, lo, label, {}); ch = sig & (lo != lo0) if changed is None else changed
            for r, fr in zip(rows, flip_rates(S, prior, sig, ch)):
                r.update({k: v for k, v in fr.items() if k != 'surface'}); r.update(key=key, **extra)
                r['above_method_point'] = bool(r['ok_전체'] > bm.loc[r['surface'], 'ok_전체'] + 1e-9); r['above_method_patch'] = bool(r['patch_ok_전체'] > bm.loc[r['surface'], 'patch_ok_전체'] + 1e-9)
            RM.extend(rows); return rows
        jm = d['j_region'][:, mi]
        # 본 방법 목표 맞음은 t6(JUDGESTRUCT-v1) 값, 바뀐 비율은 JC 본값 판정
        for r, fr in zip([dict(x_) for x_ in t6[(t6.prior == PN[prior]) & (t6.line == '본 방법 (JUDGESTRUCT-v1)')].to_dict('records')], flip_rates(S, prior, sig, sig & np.isin(jm, [0, 1]))):
            r.update({k: v for k, v in fr.items() if k != 'surface'}); r.update(key='method', T='', treat='', above_method_point=False, above_method_patch=False); RM.append(r)
        add(lo0, '구조 하한 (지금 점군)', 'lower', dict(T='', treat=''))
        up = np.load(MC.JS/prior/'fig_arrays.npz')['up']; add(up, '구조 상한 (지금, 참값으로)', 'upper', dict(T='', treat=''), changed=sig & np.isin(up, [0, 1]))
        lga = lo0.copy(); lga[F['ga']] = 1; add(lga, '덧붙임 3 판 가. A2만', 'ga', dict(T='', treat=''))
        lda = lo0.copy(); lda[da] = 1; rda = add(lda, '덧붙임 3 판 다. A2 + 구제 + 추가', 'da', dict(T='', treat=''))
        for tl, spec in TS:
            T = Tof(spec, L, Tmix, N)
            for treat, tn in [('P', '처리 P 사전정보 사용'), ('W', '처리 W 가중 평균')]:
                lo, small = panel_lo(lo0, sig, da, dabs, T, treat); add(lo, f'{tl} · {tn} (세션 판)', f'{spec[0]}_{spec[1]}_{treat}', dict(T=tl, treat=treat))
        # 검산 1: T = 0 → 판 다
        lo, _ = panel_lo(lo0, sig, da, dabs, np.zeros(N), 'P'); rows, _ = summary(S, prior, lo, 'x', {}); ref = t11[(t11.prior == PN[prior]) & (t11.panel == 'da')].set_index('surface'); diffs = {}
        for r, fr in zip(rows, flip_rates(S, prior, sig, sig & (lo != lo0))):
            r.update({k: v for k, v in fr.items() if k != 'surface'}); rr = ref.loc[r['surface']]
            num = [k for k in r if k not in ('prior', 'surface', 'line') and isinstance(r[k], (int, float, np.floating, np.integer))]
            diffs[r['surface']] = max(abs(float(r[k]) - float(rr[k])) if np.isfinite(float(r[k])) else (0. if not np.isfinite(float(rr[k])) else 1e9) for k in num)
        CK.append(dict(prior=PN[prior], check='검산 1: T = 0(모두 큰 차이) = 덧붙임 3 판 다(t11_combo), 모든 값', max_abs_diff=diffs, passed=bool(max(diffs.values()) < 1e-9)))
        # 검산 2: T = 무한대 · 처리 P
        lo, _ = panel_lo(lo0, sig, da, dabs, np.full(N, np.inf), 'P'); ab = np.ones(N, np.int8)   # JUDGEABL-v1 '식별 2 없음·사전정보 사용' = 모든 패치 판정 1 (a1_variants.py:152)
        notsig_diff = ~sig & (lo != ab); geom = d['geometry']; nolim = ~np.isfinite(L) | (geom == 9)
        CK.append(dict(prior=PN[prior], check="검산 2: T = 무한대·처리 P 에서 차이가 유의한 패치 = 모두 사전정보 사용, JUDGEABL-v1 '식별 2 없음·사전정보 사용'(모든 패치 1)과 차이가 유의한 패치의 판정 같음",
                       sig_all_prior=bool((lo[sig] == 1).all()), sig_equal_jabl=int((lo[sig] == ab[sig]).sum()), sig_patches=int(sig.sum()), passed=bool((lo[sig] == ab[sig]).all()),
                       not_sig_differ_area_m2=float(A[notsig_diff].sum()), no_limit_differ_area_m2=float(A[notsig_diff & nolim].sum()), no_limit_differ_by_judgment_m2={M11.JN.get(int(j), str(j)): float(A[notsig_diff & nolim & (lo == j)].sum()) for j in np.unique(lo[notsig_diff & nolim])}))
        # 2.2 분포
        for sn, kk in SURF[prior]:
            km = np.isin(d['kind'], kk) & sig
            for s_ in [0, 1, 2, 4]:
                mm = km & (pc == s_); ok = mm & np.isfinite(dabs); okr = mm & np.isfinite(ratio)
                r = dict(prior=PN[prior], surface=sn, state=STATE[s_], area_m2=float(A[mm].sum()), gt_points=int(gp[mm].sum()), patches=int(mm.sum()),
                         d_q=[float(wq(dabs[ok], A[ok], q)) for q in QS] if ok.any() else [np.nan]*5, ratio_q=[float(wq(ratio[okr], A[okr], q)) for q in QS] if okr.any() else [np.nan]*5)
                sv = SESSION0.get((PN[prior], STATE[s_])) if sn == '지붕' else None; r['session0'] = sv
                if sv: r['max_diff_m'] = float(max(abs(a - b) for a, b in zip(r['d_q'], sv)))
                for tl, spec in TS:
                    T = Tof(spec, L, Tmix, N)
                    with np.errstate(invalid='ignore'): sm = mm & ~(dabs >= T)
                    r[f'small_pct::{tl}'] = 100*A[sm].sum()/A[mm].sum() if A[mm].sum() else np.nan
                DIST.append(r)
            for tl, spec in [('T = 1 m', ('fixed', 1.)), ('T = 혼합 경계', ('mix', None))]:
                T = Tof(spec, L, Tmix, N)
                with np.errstate(invalid='ignore'): sp = km & (pc == 1) & ~(dabs >= T)
                for pk, pnm in PLACE.items():
                    mm = sp & (x['place'] == pk); SPL.append(dict(prior=PN[prior], surface=sn, T=tl, place=pnm, area_m2=float(A[mm].sum()), gt_points=int(gp[mm].sum()), patches=int(mm.sum()), priorerr_place_m2=float(A[km & (pc == 1) & (x['place'] == pk)].sum())))
                bl = x['building']; rows = [dict(prior=PN[prior], surface=sn, T=tl, building=str(b_), area_m2=float(A[sp & (bl == b_)].sum()), gt_points=int(gp[sp & (bl == b_)].sum()), priorerr_m2=float(A[km & (pc == 1) & (bl == b_)].sum())) for b_ in np.unique(bl[sp])]
                BLD.extend(sorted(rows, key=lambda r: -r['area_m2'])[:10])
        for r in DIST:
            if r['prior'] == PN[prior] and r.get('session0'):
                CK.append(dict(prior=PN[prior], surface=r['surface'], state=r['state'], check='검산 3: |d| 넓이 가중 10/25/50/75/90 % = 0절 세션 값 (0.02 m 안)', here=[round(v, 4) for v in r['d_q']], session=r['session0'], max_diff_m=r['max_diff_m'], passed=bool(r['max_diff_m'] <= .02)))
        # 검산 4 · 패치 열 둘
        src = MC.O/'judge'/f'patches3_{prior}.csv.gz'; lines = gzip.open(src, 'rt', newline='').read().split('\n'); assert lines[-1] == ''; lines = lines[:-1]
        pid = pd.read_csv(src, usecols=['patch_id'])['patch_id'].values; assert np.array_equal(pid, d['patch_id'])
        with np.errstate(invalid='ignore'): mixbig = np.where(np.isfinite(dabs) & np.isfinite(Tmix), (dabs >= Tmix).astype(float), np.nan)
        nd = pd.DataFrame(dict(d_abs_over_L=ratio, mix_large=['' if np.isnan(v) else str(int(v)) for v in mixbig]))
        buf = io.StringIO(); nd.to_csv(buf, index=False); nl = buf.getvalue().split('\n')[:-1]; assert len(nl) == len(lines)
        dst = MC.O/'judge'/f'patches4_{prior}.csv.gz'
        with gzip.open(dst, 'wt', newline='') as w: w.write('\n'.join(a + ',' + b for a, b in zip(lines, nl)) + '\n')
        back = gzip.open(dst, 'rt', newline='').read().split('\n')[:-1]
        CK.append(dict(prior=PN[prior], check='검산 4: 더한 열 둘을 뗀 패치 값 = 묶음 나4(patches3) 바이트까지', rows=len(back) - 1, passed=('\n'.join(','.join(y.split(',')[:-2]) for y in back) == '\n'.join(lines))))
        print('TABLES4', prior, round(T_.s()), flush=True)
    tab = lambda rows, name, note: (pd.DataFrame(rows).to_csv(DOCT/f'{name}.csv', index=False), dump(DOCT/f'{name}.json', dict(rows=json.loads(pd.DataFrame(rows).to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None)))
    tab(RM, 't12_magnitude', '덧붙임 4 2.1절. 판 스무 가지(T 열 가지 x 처리 둘)는 모두 세션 판. 본 방법 목표 맞음은 t6_rejudge(JUDGESTRUCT-v1).')
    tab(DIST, 't12_magnitude_dist', '덧붙임 4 2.2절 분포·작은 차이 쪽 넓이 비율.'); tab(SPL, 't12_small_priorerr_place', '작은 차이 쪽 사전정보 오류, 자리마다.'); tab(BLD, 't12_small_priorerr_bld', '작은 차이 쪽 사전정보 오류, 건물 열 동.')
    dump(DOCT/'t12_mixture.json', dict(mixture=MIXALL, rule=__doc__, scientific_verdict=None))
    dump(DOCT/'t12_checks.json', dict(at=now(), checks=CK, seconds=T_.s(), scientific_verdict=None))
    for c in CK: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False)[:700], flush=True)
    write_md(RM, DIST, SPL, BLD, MIXALL, CK); MC.progress(f'mf19 tables(덧붙임 4 2절) 끝, {round(T_.s())} 초')

def write_md(RM, DIST, SPL, BLD, MIXALL, CK):
    show = lambda r: (r['prior'] == 'LoD2') or (r['surface'] == '지붕')
    cell = lambda r, b: f"{f1(r[b + '_pct'])} ({r[b + '_area_m2']:,.0f}, {int(r[b + '_gt_points']):,})"
    L = ['# t12_magnitude', '', '덧붙임 4 2.1절. 대상 = 차이가 유의한 패치(지금 점군), 그 밖은 구조 하한 그대로. 큰 차이(|d| ≥ T) = 영상 깊이 사용, 덧붙임 3 판 다가 되돌리는 패치만 사전정보 사용. 작은 차이(|d| < T) = 처리 P 사전정보 사용 / 처리 W 일치와 같은 목표(정밀도 가중 평균, 본값의 무게).', '',
         '- **판 스무 가지(T 열 가지 × 처리 둘)는 모두 세션이 정한 판이다. T 를 고르지 않는다.** 혼합 경계의 맞춘 값은 아래 끝 절과 t12_mixture.json.',
         '- 바뀐 비율 = 차이가 유의한 패치 가운데 사전정보 사용 또는 가중 평균(일치 목표)이 된 넓이 %, 처음 상태마다. 본 방법 줄 = JUDGECHECK-v2 본값 판정이 사전정보 사용·일치인 넓이(목표 맞음은 t6_rejudge), 구조 상한 줄 = fig_arrays up 이 사전정보 사용·일치인 넓이.',
         '- ▲ = 전체 목표 맞음이 본 방법보다 높음(점 단위 ▲점, 패치 단위 ▲패치). 값만 표시하며 고르지 않음.', '', 'scientific_verdict: null', '',
         '네 경우 차례 = 두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측. 괄호 = (바뀐 넓이 m², 그 패치들의 네 경우 참값 점 수).', '',
         '| 사전 정보 | 면 | 줄 | 점: 네 경우 · 전체 | 점: 평균·최솟값·격차 | 패치: 네 경우 · 전체 | 패치: 평균·최솟값·격차 | 영상 깊이 오류 바뀜 % (m², 점) | 사전정보 오류 바뀜 % (m², 점) | 두 자료 모두 유효 바뀜 % (m², 점) | 본 방법보다 높음 |', '|---|---|---|---|---|---|---|---|---|---|---|']
    seen = set()
    for r in RM:
        if not show(r): continue
        if (r['prior'], r['surface']) not in seen:
            seen.add((r['prior'], r['surface']))
            L.append(f"| {r['prior']} | {r['surface']} | 분모 (차이가 유의한 패치) | | | | | {r['den_found_imgerr_area_m2']:,.0f} m², {int(r['den_found_imgerr_gt_points']):,} 점 | {r['den_wrong_priorerr_area_m2']:,.0f} m², {int(r['den_wrong_priorerr_gt_points']):,} 점 | {r['den_changed_bothvalid_area_m2']:,.0f} m², {int(r['den_changed_bothvalid_gt_points']):,} 점 | |")
        mk = ' '.join(x for x, f in [('▲점', r.get('above_method_point')), ('▲패치', r.get('above_method_patch'))] if f)
        L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | " + ' / '.join(f1(r[f'ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['ok_전체'])} | {f1(r['ok_네 경우 평균'])} · {f1(r['ok_최솟값'])} · {f1(r['ok_최대 격차'])} | "
                 + ' / '.join(f1(r[f'patch_ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['patch_ok_전체'])} | {f1(r['patch_ok_네 경우 평균'])} · {f1(r['patch_ok_최솟값'])} · {f1(r['patch_ok_최대 격차'])} | {cell(r, 'found_imgerr')} | {cell(r, 'wrong_priorerr')} | {cell(r, 'changed_bothvalid')} | {mk} |")
    L += ['', '## 혼합 경계 (log|d| 에 정규 분포 둘, 넓이 가중 EM; 참값 쓰지 않음)', '', '| 사전 정보 | 면 | 패치 · 넓이 m² | 두 평균 (m) | 두 표준 편차 (log) | 무게 | 경계 m (작은 무리 평균 위 첫 교차) | 자료 최솟값부터 첫 교차 m | 반복 |', '|---|---|---|---|---|---|---|---|---|']
    for p, M in MIXALL.items():
        for sn, m in M.items(): L.append(f"| {PN[p]} | {sn} | {m['patches']:,} · {m['area_m2']:,.0f} | {m['mu_m'][0]:.3f} / {m['mu_m'][1]:.3f} | {m['sd_log'][0]:.3f} / {m['sd_log'][1]:.3f} | {m['weight'][0]:.3f} / {m['weight'][1]:.3f} | {m['boundary_m']:.3f} | {m['boundary_from_min_m']:.3f} | {m['iters']} |")
    L += ['', '## 검산', ''] + [f"- {c['check']} ({c.get('prior', '')} {c.get('surface', '')} {c.get('state', '')}): " + json.dumps(jsafe({k: v for k, v in c.items() if k not in ('check', 'prior', 'surface', 'state')}), ensure_ascii=False) for c in CK]
    (DOCT/'t12_magnitude.md').write_text('\n'.join(L) + '\n')
    pq = lambda v: ' / '.join('—' if not np.isfinite(x) else f'{x:.2f}' for x in v)
    L = ['# t12_magnitude_dist', '', '덧붙임 4 2.2절. 차이가 유의한 패치(지금 점군)의 |d|(= |d_m|, d_m = 영상 깊이 평균 − 사전 정보 높이)와 |d| ÷ L 의 넓이 가중 10 / 25 / 50 / 75 / 90 % 값(JUDGEABL common.wq), 처음 상태마다. 0절 표(세션 값)를 나란히.', '', 'scientific_verdict: null', '',
         '## 1. 분포', '', '| 사전 정보 | 면 | 처음 상태 | 넓이 m² (참값 점) | |d| m: 10/25/50/75/90 % | 0절 표 | 가장 큰 차 m | |d| ÷ L: 10/25/50/75/90 % |', '|---|---|---|---|---|---|---|---|']
    for r in DIST:
        if show(r): L.append(f"| {r['prior']} | {r['surface']} | {r['state']} | {r['area_m2']:,.0f} ({r['gt_points']:,}) | {pq(r['d_q'])} | {pq(r['session0']) if r.get('session0') else ''} | {r['max_diff_m']:.3f} |" if r.get('session0') else f"| {r['prior']} | {r['surface']} | {r['state']} | {r['area_m2']:,.0f} ({r['gt_points']:,}) | {pq(r['d_q'])} | | |" )
        if show(r): L[-1] += f" {pq(r['ratio_q'])} |"
    TL = [t for t, _ in TS]
    L += ['', '## 2. 작은 차이 쪽(|d| < T)에 든 넓이 비율 %, 처음 상태마다', '', '| 사전 정보 | 면 | 처음 상태 | ' + ' | '.join(TL) + ' |', '|---|---|---|' + '---|'*len(TL)]
    for r in DIST:
        if show(r): L.append(f"| {r['prior']} | {r['surface']} | {r['state']} | " + ' | '.join(f1(r[f'small_pct::{t}']) for t in TL) + ' |')
    L += ['', '## 3. 작은 차이 쪽에 든 사전정보 오류 — 자리마다', '', '| 사전 정보 | 면 | T | 자리 | 넓이 m² (참값 점) | 그 자리 사전정보 오류 넓이 m² |', '|---|---|---|---|---|---|']
    for r in SPL:
        if show(r): L.append(f"| {r['prior']} | {r['surface']} | {r['T']} | {r['place']} | {r['area_m2']:,.1f} ({r['gt_points']:,}) | {r['priorerr_place_m2']:,.1f} |")
    L += ['', '## 4. 작은 차이 쪽에 든 사전정보 오류 — 건물(넓은 차례 열 동)', '', '| 사전 정보 | 면 | T | 건물 | 넓이 m² (참값 점) | 그 건물 사전정보 오류 넓이 m² |', '|---|---|---|---|---|---|']
    for r in BLD:
        if show(r): L.append(f"| {r['prior']} | {r['surface']} | {r['T']} | {r['building']} | {r['area_m2']:,.1f} ({r['gt_points']:,}) | {r['priorerr_m2']:,.1f} |")
    (DOCT/'t12_magnitude_dist.md').write_text('\n'.join(L) + '\n')

def figs_mode(prior):
    import mf8_figs as F8, mf16_addendum2 as M16
    import matplotlib, matplotlib.ticker, matplotlib.pyplot as plt
    T_ = Timer(); S, d0, sig, lo0, flipA2, pres, F, dabs, L, ratio, Tmix, MIX, x = base4(prior); A = S['A']; pc = S['pc']; meta_all = {}
    COLS = {0: '#1a9850', 1: '#d7301f', 2: '#2c7fb8', 4: '#999999'}
    # fig12_dist
    kinds = [1, 2] if prior == 'LoD2' else [1]; fig, axs = plt.subplots(1, len(kinds), figsize=(6*len(kinds), 4.2), squeeze=False); meta = dict(prior=prior, panels=[])
    bins = np.linspace(np.log10(.01), np.log10(30), 81)
    for ax, k in zip(axs[0], kinds):
        pm = dict(kind=KN[k], states={})
        for s_ in [0, 1, 2, 4]:
            m = sig & (d0['kind'] == k) & (pc == s_) & (dabs > 0); h, _ = np.histogram(np.log10(dabs[m]), bins=bins, weights=A[m]); ax.step(10**bins[:-1], h, where='post', color=COLS[s_], label=f'{STATE[s_]} ({A[m].sum():,.0f} m²)', lw=1.1)
            pm['states'][STATE[s_]] = dict(area_m2=float(A[m].sum()), hist_area_m2=h.tolist())
        for t in FIXED: ax.axvline(t, color='k', lw=.6, ls=':')
        tb = MIX[KN[k]]['boundary_m']; ax.axvline(tb, color='m', lw=1.2, ls='--', label=f'혼합 경계 {tb:.2f} m')
        ax.set_xscale('log'); ax.set_xlabel('|d| (m, 로그) — 점선 = 고정 T 0.3·0.5·0.75·1·1.5·2 m', fontsize=7); ax.set_ylabel('넓이 m² (구간마다)', fontsize=7); ax.set_title(f'{PN[prior]} {KN[k]}: 차이가 유의한 패치의 |d|, 처음 상태마다', fontsize=8); ax.legend(fontsize=6, frameon=False); ax.tick_params(labelsize=6)
        pm['bins_log10'] = bins.tolist(); pm['mixture'] = MIX[KN[k]]; meta['panels'].append(pm)
    fig.tight_layout(); J3.save(fig, f'fig12_dist_{prior}', meta); meta_all['dist'] = 1
    # fig12_curve
    R = pd.read_csv(DOCT/'t12_magnitude.csv'); sn = '모두' if prior == 'LoD2' else '지붕'; R = R[(R.prior == PN[prior]) & (R.surface == sn)]
    ys = [('ok_전체', '전체')] + [(f'ok_{CASE[c]}', CASE[c]) for c in CASES]; fig, axs = plt.subplots(1, len(ys), figsize=(3.3*len(ys), 3.4)); meta = dict(prior=prior, surface=sn, lines={})
    hl = [('method', '본 방법', 'k', '-'), ('lower', '구조 하한', '#888888', ':'), ('da', '덧붙임 3 판 다', '#984ea3', '--')]
    for ax, (yk, yn) in zip(axs, ys):
        for treat, col in [('P', '#d7301f'), ('W', '#2c7fb8')]:
            rr = R[R.key.isin([f'fixed_{t}_{treat}' for t in FIXED])].copy(); rr['Tv'] = [float(k.split('_')[1]) for k in rr.key]; rr = rr.sort_values('Tv')
            ax.plot(rr.Tv, rr[yk], '-o', ms=3, color=col, label=f'처리 {treat}'); meta['lines'].setdefault(treat, {})[yk] = dict(T=rr.Tv.tolist(), value=rr[yk].tolist())
        for key, lab, col, ls in hl:
            v = float(R[R.key == key][yk].iloc[0]); ax.axhline(v, color=col, ls=ls, lw=.9, label=lab); meta.setdefault('hlines', {}).setdefault(key, {})[yk] = v
        ax.set_xscale('log'); ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.set_xticks(FIXED); ax.set_xticklabels([f'{t:g}' for t in FIXED], fontsize=6); ax.set_xlabel('T (m)', fontsize=7); ax.set_title(f'{yn} 목표 맞음 % (점)', fontsize=7.5); ax.tick_params(labelsize=6)
    axs[0].legend(fontsize=5.5, frameon=False); fig.suptitle(f'{PN[prior]} {sn}: 고정 T 마다 판 둘(처리 P·W, 세션 판) — 가로선 = 본 방법·구조 하한·덧붙임 3 판 다 (T 를 고르지 않음)', fontsize=8); fig.tight_layout(rect=[0, 0, 1, .92])
    J3.save(fig, f'fig12_curve_{prior}', meta); meta_all['curve'] = 1
    # fig12_small_change
    a2 = M16.a2more(prior, d0); frac = a2['c_ge5_frac']; cols = M16.base(prior)[5]; dev = cols['gt_mvs_dist_median_m']
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'building', 'place', 'kind', 'area'])
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gid', 'case', 'paired', 'gt_kind']); Z = np.load(MC.JS/prior/'fig_arrays.npz'); assert np.array_equal(Z['pc'], pc)
    jd = MC.O/'judge'/prior; Pn = dict(np.load(jd/'patch_none.npz')); Pn['mean'] = d['mvs_mean_m']; Pm = dict(np.load(jd/'patch_A2.npz')); Pm['mean'] = F8.load_mean(prior, 'A2', d)
    def xlab(i, bname):
        dv = dev[i]; return (f"{bname} · {PLACE.get(int(d['place'][i]), '')} · |d| {dabs[i]:.2f} m · L {L[i]:.2f} m · 광도 {M18.PCODE[int(pres[i])]} · 참값 거리 " + ('—' if not np.isfinite(dv) else f"{dv:+.2f} m"))
    F8.COLOR_C = True
    with np.errstate(invalid='ignore'): pick = F8.groups(sig & (pc == 1) & (dabs < 1.), d, A, n=6)
    fig, meta = F8.examples(prior, 'A2', 'image', d, g, Z, Pn, Pm, f"{PN[prior]} · 작은 차이 쪽(|d| < 1 m)에 든 사전정보 오류 — 단면의 영상 깊이 점을 c(일치 시점 수, 자기 포함)로 칠함", pick=pick, xlab=xlab)
    for mm_, (cc, mem, area) in zip(meta, pick):
        i = mm_['section_patch_gid']; mm_.update(place=PLACE.get(int(d['place'][i]), ''), d_abs_m=float(dabs[i]), L_m=float(L[i]), photo_result=M18.PCODE[int(pres[i])], gt_mvs_dist_median_m=float(dev[i]), c_ge5_frac=float(frac[i]),
                                                 group_d_abs_median_areaweighted=float(wq(dabs[mem], A[mem], .5)))
    J3.save(fig, f'fig12_small_change_{prior}', dict(prior=prior, rule='차이가 유의한 사전정보 오류 패치 가운데 |d| < 1 m, 넓은 모임 차례(0.36 m 이어짐, 같은 건물), 한 건물에 하나', note='단면의 걸러낸 뒤 점선·json 의 judgment_before/after·survive 값은 fig10 짜임 그대로 A2 걸러내기 값', groups=meta)); meta_all['small'] = len(meta)
    F8.COLOR_C = False
    print('FIGS4', prior, json.dumps(meta_all), round(T_.s()), flush=True); MC.progress(f'mf19 figs {prior}(덧붙임 4 3절) 끝, {round(T_.s())} 초')

if __name__ == '__main__':
    MC.cfg()
    {'tables': lambda: tables_mode(), 'figs': lambda: figs_mode(sys.argv[2])}[sys.argv[1]]()
