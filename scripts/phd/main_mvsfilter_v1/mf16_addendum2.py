"""덧붙임 2(11/21): A2 본 판(1 %) 점검이 '못 찾은 영상 깊이 오류'와 '잘못 되돌린 사전정보 오류'를 나눠 봄. 학습·새 광도 점수·새 화소 셈 없음, CPU.
점검 규칙 = 묶음 나2 판 '점검' A2 본 판 그대로: 차이가 유의한 패치(지금 점군) 가운데 judge/<prior>/patch_A2 의 n < 4 이면 사전정보 사용으로 바꿈(= 되돌림).
참값은 처음 상태(pc)·채점·표의 참값 열에만 쓴다(점검·걸러내기에는 쓰지 않음).
사용: mf16_addendum2.py cols | tables | figs <prior>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mf11_check as M11
from mf11_check import *
from jscommon import *
from common import wq, PLACE, JUD
import js3_figs as J3
DOCT = Path('/docs/tables'); DOCF = Path('/docs/figures')
NEW = ['building', 'region', 'place', 'd_m', 'L_m', 'u_M', 'fit_nmad', 's_P', 's_M', 'texture_M', 'views_M',
       'A2_m_median', 'A2_cm_median', 'A2_om_mean', 'A2_c_p10', 'A2_c_p90', 'A2_half_or5_frac',
       'gt_mvs_dist_median_m', 'gt_prior_dist_median_m']
GROUPS_MISS = [('찾음', None), ('못 찾음 · c≥5 비율 < 0.2', (-1, .2)), ('못 찾음 · 0.2 ~ 0.5', (.2, .5)), ('못 찾음 · ≥ 0.5', (.5, 9))]
MBINS = [(1, 4), (5, 9), (10, 19), (20, 39), (40, 10**6)]

def a2more(prior, d):
    keys = ['raw_n', 'c_median', 'c_ge5_frac', 'f_ratio_mean', 'm_median', 'cm_median', 'om_mean', 'c_p10', 'c_p90', 'half_or5_frac']; out = {k: np.full(len(d['kind']), np.nan) for k in keys}
    for ti, t in enumerate(d['tiles']):
        m = np.flatnonzero(d['tile'] == ti); z = loadz(MC.O/'a2_patch2'/f'{t}.npz'); assert np.array_equal(z[f'{prior}__patch_id'], d['patch_id'][m])
        for k in keys: out[k][m] = z[f'{prior}__{k}']
    return out

def base(prior):
    """패치 값(새 열 포함), 처음 상태, 점검 판 A2 의 되돌림. 참값 열은 채점용."""
    S = M11.setup(prior); d = S['d']; N = len(d['kind'])
    x = loadz(JP/f'patch_{prior}.npz', ['building', 'place', 'd_m', 'fit_nmad', 'views_M', 'mvs_mean_m'])
    assert np.allclose(x['mvs_mean_m'], d['mvs_mean_m'], equal_nan=True)
    jd = MC.O/'judge'/prior; b = np.load(jd/'patch_none.npz'); q = np.load(jd/'patch_A2.npz'); sig = b['sig']
    flip = sig & (q['n'] >= 0) & (q['n'] < 4)
    a2 = a2more(prior, d); a1 = M11.a2_patch(prior, d)
    for k in ['raw_n', 'c_median', 'c_ge5_frac', 'f_ratio_mean']:
        assert np.array_equal(np.isnan(a2[k]), np.isnan(a1[k])) and np.nanmax(np.abs(a2[k] - a1[k])) < 1e-9, k
    # 참값 열: 패치에 속한 참값 점(paired, 네 경우 — 채점과 같은 점)에서 법선 방향 거리의 중앙값. JC plane_distance: + = 그 면이 참값 점보다 법선 쪽(지붕 위, 벽 밖)
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind'])
    keep = np.flatnonzero(g['paired'] & np.isin(g['case'], CASES)); gid = g['gid'][keep]; xyz = g['xyz'][keep]; nor = g['normal'][keep]; wall = g['gt_kind'][keep] == 2; del g
    def med_by(v):
        ok = np.isfinite(v); o = np.argsort(gid[ok], kind='stable'); gg = gid[ok][o]; vv = v[ok][o]; out = np.full(N, np.nan)
        if len(gg):
            cut = np.flatnonzero(np.diff(gg)) + 1
            for seg_g, seg_v in zip(np.split(gg, cut), np.split(vv, cut)): out[seg_g[0]] = np.median(seg_v)
        return out
    dm = plane_distance(xyz, nor, d['centre'][gid], d['normal'][gid], d['mvs_mean_m'][gid], wall)
    dp = plane_distance(xyz, nor, d['centre'][gid], d['normal'][gid], d['prior_height_m'][gid], wall)
    cols = dict(building=x['building'], region=d['region'], place=np.array([PLACE.get(int(p), '') for p in x['place']]), d_m=x['d_m'], L_m=d['L_m'], u_M=d['u_M'], fit_nmad=x['fit_nmad'],
                s_P=d['s_P'], s_M=d['s_M'], texture_M=d['texture_M'], views_M=x['views_M'],
                A2_m_median=a2['m_median'], A2_cm_median=a2['cm_median'], A2_om_mean=a2['om_mean'], A2_c_p10=a2['c_p10'], A2_c_p90=a2['c_p90'], A2_half_or5_frac=a2['half_or5_frac'],
                gt_mvs_dist_median_m=med_by(dm), gt_prior_dist_median_m=med_by(dp))
    return S, d, sig, flip, a2, cols, q

def cols_mode():
    T = Timer(); rec = {}
    for prior in ['LoD2', 'ALS']:
        S, d, sig, flip, a2, cols, q = base(prior)
        f = MC.O/'judge'/f'patches_{prior}.csv.gz'; import gzip, io
        lines = gzip.open(f, 'rt', newline='').read().split('\n'); assert lines[-1] == ''; lines = lines[:-1]
        pid = pd.read_csv(f, usecols=['patch_id'])['patch_id'].values; assert np.array_equal(pid, d['patch_id'])
        nd = pd.DataFrame({k: cols[k] for k in NEW}); buf = io.StringIO(); nd.to_csv(buf, index=False); nl = buf.getvalue().split('\n')[:-1]; assert len(nl) == len(lines)
        out = '\n'.join(a + ',' + b for a, b in zip(lines, nl)) + '\n'
        dst = MC.O/'judge'/f'patches2_{prior}.csv.gz'
        with gzip.open(dst, 'wt', newline='') as w: w.write(out)
        # 검산 3: 새 파일에서 더한 열(뒤 len(NEW) 칸)을 떼면 묶음 나2 판의 풀린 바이트와 같다
        back = gzip.open(dst, 'rt', newline='').read().split('\n')[:-1]; k_ = len(NEW)
        old_again = '\n'.join(','.join(x.split(',')[:-k_]) if x.count(',') >= k_ else x for x in back) + '\n'
        df = pd.read_csv(dst, usecols=NEW + ['patch_id'])
        rec[prior] = dict(rows=len(df), added=NEW, same_bytes_without_new_cols=old_again == '\n'.join(lines) + '\n', empty={k: int(pd.isna(df[k]).sum()) for k in NEW}, empty_sig={k: int(pd.isna(df[k][sig]).sum()) for k in NEW}, sig_patches=int(sig.sum()))
        print('COLS', prior, json.dumps(jsafe(rec[prior]), ensure_ascii=False), flush=True)
    rec['seconds'] = T.s(); rec['scientific_verdict'] = None; dump(MC.O/'masks/addendum2_cols.json', rec)
    MC.progress(f'mf16 cols(덧붙임 2 1절) 끝, {round(T.s())} 초')

def q3(v, w):
    ok = np.isfinite(v) & (w > 0)
    return [float(wq(v[ok], w[ok], p)) if ok.any() else np.nan for p in (.1, .5, .9)]

def pf(v): return '—' if not np.isfinite(v) else f'{v:.1f}'
def tf(v): return '' if not np.isfinite(v) else f'{v:g}'
def f3(x): return ' / '.join('—' if not np.isfinite(v) else (f'{v:.2f}' if abs(v) < 100 else f'{v:.0f}') for v in x)

def tables_mode():
    T = Timer(); OUT = {}; Lm, Lf, Lr = [], [], []; CK = []
    t8 = pd.read_csv(DOCT/'t8_check_mode.csv'); t8 = t8[(t8.method == 'A2') & (t8['mode'] == '점 4개 미만')]
    DEN = {(r['prior'], r['surface']): (r['den_found_imgerr_area_m2'], r['den_wrong_priorerr_area_m2']) for _, r in t8.iterrows()}
    for prior in ['LoD2', 'ALS']:
        S, d, sig, flip, a2, cols, q = base(prior); A = S['A']; pc = S['pc']; gp = np.bincount(S['gid'], minlength=len(A)); rn0 = np.load(MC.O/'judge'/prior/'patch_none.npz')['raw_n'].astype(float)
        frac = a2['c_ge5_frac']; dev = cols['gt_mvs_dist_median_m']; bld = cols['building']; reg = cols['region']; plc = cols['place']
        V = dict(rn=rn0, uM=d['u_M'], fit=cols['fit_nmad'], sM=d['s_M'], tex=d['texture_M'], m=a2['m_median'], cm=a2['cm_median'], om=a2['om_mean'])
        VK = {'rn': '원통 안 점 수', 'uM': 'u_M (m)', 'fit': '면 맞춤 잔차 (m)', 'sM': 's_M', 'tex': '무늬 세기(영상)', 'm': 'm 중앙값', 'cm': 'c ÷ m 중앙값', 'om': 'o ÷ m 평균'}
        for sn, kk in SURF[prior]:
            km = np.isin(d['kind'], kk) & sig
            # 2.1 가
            ie = km & (pc == 2); den = A[ie].sum(); grp = {}
            for gname, rng in GROUPS_MISS:
                grp[gname] = ie & flip if rng is None else ie & ~flip & (frac >= rng[0]) & (frac < rng[1]) if rng[0] >= 0 else ie & ~flip & ~(frac >= .2)
            t8d = DEN[(PN[prior], sn)][0]; sm_ = float(sum(A[m].sum() for m in grp.values()))
            CK.append(dict(prior=PN[prior], surface=sn, check='2.1 찾음 + 못 찾음 넓이 = t8_check_mode 영상 깊이 오류 분모', sum_m2=sm_, den_m2=float(t8d), passed=bool(abs(sm_ - t8d) < 1e-6)))
            for gname, m in grp.items():
                a = A[m].sum(); up = A[m & (dev > 0)].sum(); dn = A[m & (dev < 0)].sum(); na = A[m & ~np.isfinite(dev)].sum()
                r = dict(prior=PN[prior], surface=sn, group=gname, area_m2=float(a), area_pct=100*a/den if den else np.nan, patches=int(m.sum()), gt_points=int(gp[m].sum()),
                         dev_abs_q=q3(np.abs(dev[m]), A[m]), up_pct=100*up/a if a else np.nan, down_pct=100*dn/a if a else np.nan, dev_na_pct=100*na/a if a else np.nan)
                for k in VK: r[f'{k}_q'] = q3(V[k][m], A[m])
                Lm.append(r)
            # 자리·지역
            for keyname, arr, levels in [('자리', plc, list(PLACE.values())), ('탐색 지역', reg, sorted(set(reg[ie])))]:
                for lv in levels:
                    r = dict(prior=PN[prior], surface=sn, split=keyname, level=lv, total_m2=float(A[ie & (arr == lv)].sum()))
                    for gname, m in grp.items(): r[gname] = float(A[m & (arr == lv)].sum())
                    OUT.setdefault('miss_split', []).append(r)
            # 건물 스무 동
            miss = ie & ~flip; ub = np.unique(bld[miss]); rows = []
            for b_ in ub:
                mb = bld == b_; rows.append(dict(prior=PN[prior], surface=sn, building=str(b_), missed_m2=float(A[miss & mb].sum()), missed_ge05_m2=float(A[grp['못 찾음 · ≥ 0.5'] & mb].sum()), imgerr_m2=float(A[ie & mb].sum())))
            OUT.setdefault('miss_bld', []).extend(sorted(rows, key=lambda r: -r['missed_m2'])[:20])
            # 2.2 나
            pe = km & (pc == 1); denp = A[pe].sum(); g2 = {'되돌림': pe & flip, '그대로': pe & ~flip}
            t8d = DEN[(PN[prior], sn)][1]; sm_ = float(A[g2_r := (pe & flip)].sum() + A[pe & ~flip].sum())
            CK.append(dict(prior=PN[prior], surface=sn, check='2.2 되돌림 + 그대로 넓이 = t8_check_mode 사전정보 오류 분모', sum_m2=sm_, den_m2=float(t8d), passed=bool(abs(sm_ - t8d) < 1e-6)))
            for gname, m in g2.items():
                a = A[m].sum(); r = dict(prior=PN[prior], surface=sn, group=gname, area_m2=float(a), area_pct=100*a/denp if denp else np.nan, patches=int(m.sum()), gt_points=int(gp[m].sum()))
                for k in ['rn', 'm', 'cm', 'om', 'uM', 'sM', 'tex']: r[f'{k}_q'] = q3(V[k][m], A[m])
                Lf.append(r)
            mmed = a2['m_median']
            for lo_, hi_ in MBINS + [(None, None)]:
                mb = (mmed >= lo_) & (mmed <= hi_) if lo_ is not None else ~np.isfinite(mmed)
                r = dict(prior=PN[prior], surface=sn, m_bin=f'{lo_}~{hi_}' if hi_ < 10**6 else f'{lo_} 이상') if lo_ is not None else dict(prior=PN[prior], surface=sn, m_bin='값 없음(원통 점 0)')
                for s_, nm in [(1, '사전정보 오류'), (2, '영상 깊이 오류'), (0, '두 자료 모두 유효')]:
                    mm = km & (pc == s_) & mb; a = A[mm].sum(); r[f'{nm}_m2'] = float(a); r[f'{nm}_returned_pct'] = 100*A[mm & flip].sum()/a if a else np.nan
                OUT.setdefault('mbin', []).append(r)
            for keyname, arr, levels in [('자리', plc, list(PLACE.values())), ('탐색 지역', reg, sorted(set(reg[pe])))]:
                for lv in levels:
                    mm = pe & (arr == lv); a = A[mm].sum()
                    OUT.setdefault('fr_split', []).append(dict(prior=PN[prior], surface=sn, split=keyname, level=lv, priorerr_m2=float(a), returned_m2=float(A[mm & flip].sum()), returned_pct=100*A[mm & flip].sum()/a if a else np.nan))
            fr = pe & flip; rows = [dict(prior=PN[prior], surface=sn, building=str(b_), returned_m2=float(A[fr & (bld == b_)].sum()), priorerr_m2=float(A[pe & (bld == b_)].sum())) for b_ in np.unique(bld[fr])]
            OUT.setdefault('fr_bld', []).extend(sorted(rows, key=lambda r: -r['returned_m2'])[:20])
            # 검산 2: 0절 표(c≥5 비율 0 / 0~0.2 / 0.2~0.5 / 0.5~0.8 / 0.8~1, 넓이 %) — 지붕·벽 모두(LoD2), 지붕(ALS)
            if sn in ('모두',) or prior == 'ALS':
                for s_, nm in [(2, '영상 깊이 오류'), (1, '사전정보 오류')]:
                    mm = km & (pc == s_); a = A[mm].sum(); f_ = frac
                    bins = [A[mm & (f_ == 0)].sum(), A[mm & (f_ > 0) & (f_ < .2)].sum(), A[mm & (f_ >= .2) & (f_ < .5)].sum(), A[mm & (f_ >= .5) & (f_ < .8)].sum(), A[mm & (f_ >= .8)].sum()]
                    rb = [A[mm & (f_ == 0)].sum(), A[mm & (f_ > 0) & (f_ <= .2)].sum(), A[mm & (f_ > .2) & (f_ <= .5)].sum(), A[mm & (f_ > .5) & (f_ <= .8)].sum(), A[mm & (f_ > .8)].sum()]
                    OUT.setdefault('zero_table', []).append(dict(prior=PN[prior], state=nm, pct=[100*v/a for v in bins], pct_right_closed=[100*v/a for v in rb], nan_pct=100*A[mm & ~np.isfinite(f_)].sum()/a))
        # 2.3 값 셋의 AUC 와 곡선
        AUCV = [('cm', 'c ÷ m 중앙값', a2['cm_median']), ('ge5', 'c ≥ 5 인 점의 비율', a2['c_ge5_frac']), ('h5', "'2c ≥ m 또는 c ≥ 5' 인 점의 비율", a2['half_or5_frac'])]
        b0 = np.load(MC.O/'judge'/prior/'patch_none.npz'); lo0 = b0['lo']
        for sn, kk in SURF[prior]:
            km = np.isin(d['kind'], kk) & sig
            for key, lab, x in AUCV:
                e = km & (pc == 2); p = km & (pc == 1); v = km & (pc == 0)
                OUT.setdefault('ratio_auc', []).append(dict(prior=PN[prior], surface=sn, value=lab, auc_imgerr_vs_priorerr=wauc(x[e], A[e], x[p], A[p]), auc_imgerr_vs_bothvalid=wauc(x[e], A[e], x[v], A[v]),
                                                            med=[float(wq(x[m][np.isfinite(x[m])], A[m][np.isfinite(x[m])], .5)) for m in (e, p, v)], n=[int(m.sum()) for m in (e, p, v)]))
        def line(lo_flip, label, extra):
            lo = lo0.copy(); lo[lo_flip] = 1; rows, _ = summary(S, prior, lo, label, extra)
            for r, fr_ in zip(rows, flip_rates(S, prior, sig, lo_flip)): r.update({k: v for k, v in fr_.items() if k != 'surface'})
            OUT.setdefault('ratio_curve', []).extend(rows)
        line(flip, '점검 판 A2 (점 4개 미만, 본 판)', dict(value='-', threshold=np.nan))
        line(flip & ~(a2['m_median'] < 10), '점검 판 A2, m 중앙값 < 10 인 패치는 빼고(되돌리지 않음)', dict(value='-', threshold=np.nan))
        for key, lab, x in AUCV:
            for t in THR:
                line(sig & np.isfinite(x) & (x <= t), f'곡선: {lab} ≤ 문턱', dict(value=lab, threshold=t))
        print('TABLES', prior, round(T.s()), flush=True)
    OUT['checks'] = CK; OUT['seconds'] = T.s(); OUT['scientific_verdict'] = None
    dump(DOCT/'t10_addendum2.json', OUT)
    write_md(OUT, Lm, Lf); MC.progress(f'mf16 tables(덧붙임 2 2절) 끝, {round(T.s())} 초')

def write_md(OUT, Lm, Lf):
    pd.DataFrame(Lm).to_csv(DOCT/'t10_missed.csv', index=False); pd.DataFrame(Lf).to_csv(DOCT/'t10_false_return.csv', index=False)
    for k in ['miss_split', 'miss_bld', 'mbin', 'fr_split', 'fr_bld', 'ratio_auc', 'ratio_curve']: pd.DataFrame(OUT[k]).to_csv(DOCT/f't10_{k}.csv', index=False)
    VK = [('rn', '원통 안 점 수'), ('uM', 'u_M (m)'), ('fit', '면 맞춤 잔차 (m)'), ('sM', 's_M'), ('tex', '무늬 세기(영상)'), ('m', 'm 중앙값'), ('cm', 'c ÷ m 중앙값')]
    H = ['scientific_verdict: null', '', '대상 = 차이가 유의한 패치(지금 점군). 점검 규칙 = 묶음 나2 판 \'점검\' A2 본 판(1 %) 그대로(원통 안 판정용 점 n < 4 → 사전정보 사용 = 되돌림). '
         '10 / 50 / 90 % 값 = 넓이 가중 분위(JUDGEABL `wq`). c·m 은 자기 포함. 참값에서 벗어난 거리 = 패치의 참값 점(채점과 같은 점)마다 JC `plane_distance` 로 잰 영상 깊이 평균 높이 면까지의 법선 방향 거리의 중앙값; '
         '+ = 영상 깊이 면이 참값보다 법선 쪽(지붕은 위로 뜸, 벽은 밖으로), − = 아래로 꺼짐(벽은 안으로). 참값은 이 표의 채점 열에만 쓰고 점검에는 쓰지 않음.', '']
    L = ['# t10_missed — 가. 못 찾은 영상 깊이 오류 (덧붙임 2 2.1절)', ''] + H
    L += ['## 무리마다', '', '못 찾음은 원통 안 점의 \'c ≥ 5 인 점의 비율\'로 셋(0.2 미만 / 0.2 이상 0.5 미만 / 0.5 이상). 비율 값이 없는 패치(원통 점 0)는 n = 0 이라 모두 \'찾음\'.', '',
          '| 사전 정보 | 면 | 무리 | 넓이 m² (%) | 패치 | 참값 점 | 벗어난 거리 크기 m 10/50/90 | 위로 뜸 / 아래로 꺼짐 / 값 없음 % | ' + ' | '.join(f'{v} 10/50/90' for _, v in VK) + ' |', '|' + '---|'*(8 + len(VK))]
    for r in Lm:
        L.append(f"| {r['prior']} | {r['surface']} | {r['group']} | {r['area_m2']:,.0f} ({r['area_pct']:.1f}) | {r['patches']:,} | {r['gt_points']:,} | {f3(r['dev_abs_q'])} | {r['up_pct']:.1f} / {r['down_pct']:.1f} / {r['dev_na_pct']:.1f} | " + ' | '.join(f3(r[f'{k}_q']) for k, _ in VK) + ' |')
    gn = [g for g, _ in GROUPS_MISS]
    L += ['', '## 자리·탐색 지역마다 (넓이 m²)', '', '| 사전 정보 | 면 | 나눔 | 값 | 영상 깊이 오류 전체 | ' + ' | '.join(gn) + ' |', '|' + '---|'*(5 + len(gn))]
    for r in OUT['miss_split']: L.append(f"| {r['prior']} | {r['surface']} | {r['split']} | {r['level']} | {r['total_m2']:,.1f} | " + ' | '.join(f"{r[g]:,.1f}" for g in gn) + ' |')
    L += ['', '## 건물마다 — 못 찾은 넓이가 큰 차례 스무 동', '', '| 사전 정보 | 면 | 건물 | 못 찾은 m² | 그 가운데 ≥ 0.5 무리 m² | 그 건물의 영상 깊이 오류 m² |', '|---|---|---|---|---|---|']
    for r in OUT['miss_bld']: L.append(f"| {r['prior']} | {r['surface']} | {r['building']} | {r['missed_m2']:,.1f} | {r['missed_ge05_m2']:,.1f} | {r['imgerr_m2']:,.1f} |")
    L += ['', '## 검산 (덧붙임 2 4절 1·2)', '']
    for c in OUT['checks']: L.append(f"- {c['prior']} {c['surface']}: {c['check']} — {c['sum_m2']:,.2f} 대 {c['den_m2']:,.2f} m², {'같음' if c['passed'] else '다름'}")
    L += ['', '0절 표와 같은 나눔(c ≥ 5 비율 0 / 0~0.2 / 0.2~0.5 / 0.5~0.8 / 0.8~1, 넓이 %; LoD2 = 지붕·벽 모두, 항공 LiDAR = 지붕). 앞 = 구간 왼쪽 닫힘([0.2, 0.5), 이 표 2.1절 나눔과 같은 규약), 뒤 = 오른쪽 닫힘((0.2, 0.5]):', '']
    for r in OUT['zero_table']: L.append(f"- {r['prior']} {r['state']}: " + ' / '.join(f'{v:.1f}' for v in r['pct']) + ' · 오른쪽 닫힘 ' + ' / '.join(f'{v:.1f}' for v in r['pct_right_closed']) + f" (값 없음 {r['nan_pct']:.1f})")
    L += ['', '오른쪽 닫힘으로 세면 0절 표와 모든 칸이 소수 첫째 자리까지 같다. 왼쪽 닫힘과의 차이는 칸마다 1 %p 안(가장 큼: 항공 LiDAR 영상 깊이 오류 0~0.2 칸 0.9 %p). 경계에 놓인 값(0.2·0.5·0.8)의 넓이 몫이다.']
    (DOCT/'t10_missed.md').write_text('\n'.join(L) + '\n')
    VF = [('rn', '원통 안 점 수'), ('m', 'm 중앙값'), ('cm', 'c ÷ m 중앙값'), ('om', 'o ÷ m 평균'), ('uM', 'u_M (m)'), ('sM', 's_M'), ('tex', '무늬 세기(영상)')]
    L = ['# t10_false_return — 나. 잘못 되돌린 사전정보 오류 (덧붙임 2 2.2절)', ''] + H
    L += ['## 무리마다 (처음 상태 사전정보 오류)', '', '| 사전 정보 | 면 | 무리 | 넓이 m² (%) | 패치 | 참값 점 | ' + ' | '.join(f'{v} 10/50/90' for _, v in VF) + ' |', '|' + '---|'*(6 + len(VF))]
    for r in Lf: L.append(f"| {r['prior']} | {r['surface']} | {r['group']} | {r['area_m2']:,.0f} ({r['area_pct']:.1f}) | {r['patches']:,} | {r['gt_points']:,} | " + ' | '.join(f3(r[f'{k}_q']) for k, _ in VF) + ' |')
    L += ['', '## m 중앙값 구간마다 — 넓이 m², 되돌린 비율 %', '', '| 사전 정보 | 면 | m 구간 | 사전정보 오류 m² · 되돌림 % | 영상 깊이 오류 m² · 되돌림 % | 두 자료 모두 유효 m² · 되돌림 % |', '|---|---|---|---|---|---|']
    fmt = lambda a, p: f"{a:,.1f} · {p:.1f}" if np.isfinite(p) else f"{a:,.1f} · —"
    for r in OUT['mbin']: L.append(f"| {r['prior']} | {r['surface']} | {r['m_bin']} | {fmt(r['사전정보 오류_m2'], r['사전정보 오류_returned_pct'])} | {fmt(r['영상 깊이 오류_m2'], r['영상 깊이 오류_returned_pct'])} | {fmt(r['두 자료 모두 유효_m2'], r['두 자료 모두 유효_returned_pct'])} |")
    L += ['', '## 자리·탐색 지역마다 되돌린 비율', '', '| 사전 정보 | 면 | 나눔 | 값 | 사전정보 오류 m² | 되돌린 m² | 되돌린 % |', '|---|---|---|---|---|---|---|']
    for r in OUT['fr_split']: L.append(f"| {r['prior']} | {r['surface']} | {r['split']} | {r['level']} | {r['priorerr_m2']:,.1f} | {r['returned_m2']:,.1f} | {pf(r['returned_pct'])} |")
    L += ['', '## 건물마다 — 되돌린 넓이가 큰 차례 스무 동', '', '| 사전 정보 | 면 | 건물 | 되돌린 m² | 그 건물의 사전정보 오류 m² |', '|---|---|---|---|---|']
    for r in OUT['fr_bld']: L.append(f"| {r['prior']} | {r['surface']} | {r['building']} | {r['returned_m2']:,.1f} | {r['priorerr_m2']:,.1f} |")
    (DOCT/'t10_false_return.md').write_text('\n'.join(L) + '\n')
    L = ['# t10_ratio — 본 영상 수로 나눈 값의 구별 정도와 곡선 (덧붙임 2 2.3절)', '', 'scientific_verdict: null', '',
         '이 절의 값·문턱은 세션이 정한 것이다(COLMAP 기본값 아님). 문턱을 고르지 않는다. 값 셋 = 원통 안 점의 c ÷ m 중앙값, c ≥ 5 인 점의 비율(덧붙임 1, 나란히), \'2c ≥ m 또는 c ≥ 5\'(일치 수가 본 영상 수의 절반 이상이거나 5장 이상) 인 점의 비율. '
         'AUC = 넓이 가중(JUDGEPROBE `wauc`, t5_A2_auc 와 같은 방식). 곡선: 차이가 유의한 패치 가운데 값 ≤ 문턱이면 되돌림(t8_check_curve 와 같은 \'≤\'; 값 없음 = 원통 점 0 은 되돌리지 않음, t8 곡선과 같음).', '',
         '## AUC', '', '| 사전 정보 | 면 | 값 | AUC 영상 오류 대 사전 오류 | AUC 영상 오류 대 유효 | 넓이 가중 중앙값 영상 오류 / 사전 오류 / 유효 | 패치 수 |', '|---|---|---|---|---|---|---|']
    for r in OUT['ratio_auc']: L.append(f"| {r['prior']} | {r['surface']} | {r['value']} | {r['auc_imgerr_vs_priorerr']:.3f} | {r['auc_imgerr_vs_bothvalid']:.3f} | {f3(r['med'])} | {' / '.join(f'{x:,}' for x in r['n'])} |")
    L += ['', '## 점검 판·곡선 (점 단위; 패치 단위는 csv)', '', '괄호 = (바뀐 넓이 m², 그 패치들의 참값 점 수). 분모 = t8_check_mode 의 분모 줄과 같음.', '',
          '| 사전 정보 | 면 | 줄 | 문턱 | 네 경우 목표 맞음 유효/사전오류/영상오류/결측 · 전체 | 찾은 % | 잘못 되돌린 % | 유효 바뀜 % | F(JS) % |', '|---|---|---|---|---|---|---|---|---|']
    cell = lambda r, b: f"{r[b + '_pct']:.1f} ({r[b + '_area_m2']:,.0f}, {r[b + '_gt_points']:,})"
    for r in OUT['ratio_curve']:
        L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | {tf(r['threshold'])} | " + ' / '.join(f"{r[f'ok_{CASE[c]}']:.1f}" for c in CASES) + f" · {r['ok_전체']:.1f} | {cell(r, 'found_imgerr')} | {cell(r, 'wrong_priorerr')} | {cell(r, 'changed_bothvalid')} | {r['F_js_pct']:.1f} |")
    (DOCT/'t10_ratio.md').write_text('\n'.join(L) + '\n')


def figs_mode(prior):
    """덧붙임 2 3절. 짜임은 fig7_examples_<prior>_A2_c 와 같음(mf8.examples, c 세 색). 참값은 표시에만."""
    import mf8_figs as F8
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    T = Timer(); S, d0, sig, flip, a2, cols, q = base(prior); A = S['A']; pc = S['pc']; frac = a2['c_ge5_frac']; dev = cols['gt_mvs_dist_median_m']
    d = loadz(JP/f'patch_{prior}.npz', ['tile', 'tiles', 'centre', 'normal', 'tangent1', 'prior_height_m', 'mvs_mean_m', 'building', 'place', 'kind', 'area'])
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['xyz', 'gid', 'case', 'paired', 'gt_kind']); Z = np.load(MC.JS/prior/'fig_arrays.npz')
    assert np.array_equal(Z['pc'], pc), 'JS fig_arrays pc = JABL patch_case'
    jd = MC.O/'judge'/prior; Pn = dict(np.load(jd/'patch_none.npz')); Pn['mean'] = d['mvs_mean_m']; Pm = dict(np.load(jd/'patch_A2.npz')); Pm['mean'] = F8.load_mean(prior, 'A2', d)
    def xlab(i, bname):
        dv = dev[i]; return (f"{bname} · {PLACE.get(int(d['place'][i]), '')} · c≥5 비율 {frac[i]:.2f} · m 중앙값 {a2['m_median'][i]:.0f} · 참값에서 벗어난 거리 "
                             + ('—' if not np.isfinite(dv) else f"{dv:+.2f} m") + f" · 판정 {JUD.get(int(Pn['lo'][i]))} → {'사전정보 사용(되돌림)' if flip[i] else JUD.get(int(Pn['lo'][i]))}")
    F8.COLOR_C = True; meta_all = {}
    ie = sig & (pc == 2); miss = ie & ~flip
    p1 = F8.groups(miss & (frac >= .5), d, A, n=4); used = {str(d['building'][m[0]]) for _, m, _ in p1}
    p2 = F8.groups(miss & (frac >= .2) & (frac < .5), d, A, n=2, exclude=used)
    for name, pick, title, rule in [('fig10_missed', p1 + p2, '못 찾은 영상 깊이 오류(점검 판 A2 가 되돌리지 않음) 본보기 — 위 넷 = c≥5 비율 ≥ 0.5 무리, 아래 둘 = 0.2~0.5 무리', '≥ 0.5 무리에서 넷, 0.2~0.5 무리에서 둘; 넓은 모임 차례(0.36 m 이어짐, 같은 건물), 그림 전체에서 한 건물에 하나'),
                                    ('fig10_false_return', F8.groups(sig & (pc == 1) & flip, d, A, n=6), '잘못 되돌린 사전정보 오류(점검 판 A2 가 사전정보 사용으로 바꿈) 본보기', '넓은 모임 차례(0.36 m 이어짐, 같은 건물), 한 건물에 하나')]:
        fig, meta = F8.examples(prior, 'A2', 'image', d, g, Z, Pn, Pm, f"{PN[prior]} · 방법 A2(세션 판, 1 %): {title} — 단면의 영상 깊이 점을 c(일치 시점 수, 자기 포함)로 칠함", pick=pick, xlab=xlab)
        for mm_, (cc, mem, area) in zip(meta, pick):
            i = mm_['section_patch_gid']; mm_.update(place=PLACE.get(int(d['place'][i]), ''), c_ge5_frac=float(frac[i]), m_median=float(a2['m_median'][i]), gt_mvs_dist_median_m=float(dev[i]), returned=bool(flip[i]), group_c_ge5_frac_areaweighted=float(np.nansum(frac[mem]*A[mem])/A[mem][np.isfinite(frac[mem])].sum()))
        J3.save(fig, f'{name}_{prior}', dict(prior=prior, method='A2', rule=rule, colors={lab: col_ for _, col_, lab in F8.C_COL}, groups=meta)); meta_all[name] = len(meta)
    F8.COLOR_C = False
    # 지도
    O_ = J3.ortho(); SC = [(nm, ext, 'scene') for nm, ext, _ in J3.scenes(prior)[:3]]
    bm = {}
    for b_ in np.unique(cols['building'][miss]): bm[b_] = A[miss & (cols['building'] == b_)].sum()
    for b_ in sorted(bm, key=lambda k: -bm[k])[:3]:
        mb = cols['building'] == b_; c_ = d['centre'][mb]; pad = 3.; ext = (c_[:, 0].min() - pad, c_[:, 0].max() + pad, c_[:, 1].min() - pad, c_[:, 1].max() + pad); SC.append((str(b_).replace('DEBY_LOD2_', '') + f' (못 찾은 {bm[b_]:.0f} m²)', ext, 'building'))
    COL = {'found': '#1a9850', 'miss_lo': '#fd8d3c', 'miss_hi': '#d7301f', 'fr': '#7b3294'}
    cls = np.full(len(A), -1); cls[ie & flip] = 0; cls[miss & ~(frac >= .5)] = 1; cls[miss & (frac >= .5)] = 2; cls[sig & (pc == 1) & flip] = 3
    CM = {0: COL['found'], 1: COL['miss_lo'], 2: COL['miss_hi'], 3: COL['fr']}
    nr = (len(SC) + 1)//2; fig, axs = plt.subplots(nr, 2, figsize=(9, 4.3*nr), squeeze=False); meta = []
    for k, (name, ext, kind_) in enumerate(SC):
        ax = axs[k//2, k % 2]; J3.background(ax, ext, O_)
        pm = (d['centre'][:, 0] >= ext[0]) & (d['centre'][:, 0] <= ext[1]) & (d['centre'][:, 1] >= ext[2]) & (d['centre'][:, 1] <= ext[3])
        for kk in [1, 2]:
            m = pm & (d['kind'] == kk) & sig & (cls < 0); J3.paint(ax, d['centre'][m, :2], np.zeros(m.sum()), {0: '#dddddd'}, ext, alpha=.35)
        for kk in [1, 2]:
            m = pm & (d['kind'] == kk) & (cls >= 0)
            if m.any(): J3.paint(ax, d['centre'][m, :2], cls[m], CM, ext)
        sh = {lab: float(A[pm & (cls == c)].sum()) for c, lab in [(0, '찾음'), (1, '못 찾음 < 0.5'), (2, '못 찾음 ≥ 0.5'), (3, '잘못 되돌림')]}
        ax.set_title(name, fontsize=8); ax.set_xlabel(' · '.join(f'{a} {v:.0f} m²' for a, v in sh.items()), fontsize=6.3); meta.append(dict(name=name, kind=kind_, extent=list(map(float, ext)), area_m2=sh))
    for k in range(len(SC), nr*2): axs[k//2, k % 2].axis('off')
    h = [Patch(color=COL['found'], label='영상 깊이 오류 · 찾음(되돌림)'), Patch(color=COL['miss_lo'], label='영상 깊이 오류 · 못 찾음, c≥5 비율 < 0.5'), Patch(color=COL['miss_hi'], label='영상 깊이 오류 · 못 찾음, c≥5 비율 ≥ 0.5'),
         Patch(color=COL['fr'], label='사전정보 오류 · 잘못 되돌림'), Patch(color='#dddddd', label='그 밖의 차이가 유의한 패치')]
    fig.legend(handles=h, ncol=3, fontsize=6.5, loc='lower center', bbox_to_anchor=(.5, -.01), frameon=False)
    fig.suptitle(f'{PN[prior]} · 점검 판 A2(세션 판, 1 %): 세 실험 지역과 못 찾은 넓이가 가장 큰 세 동 — 지붕·벽 패치 중심(벽은 위에서 본 선)', fontsize=8.5, y=1.0); fig.tight_layout(rect=[0, .03, 1, .99])
    J3.save(fig, f'fig10_maps_{prior}', dict(prior=prior, panels=meta, colors={'found': COL['found'], 'missed_lt_0.5': COL['miss_lo'], 'missed_ge_0.5': COL['miss_hi'], 'false_return': COL['fr']}))
    MC.progress(f'mf16 figs {prior}(덧붙임 2 3절) 끝, {round(T.s())} 초')

if __name__ == '__main__':
    MC.cfg()
    {'cols': lambda: cols_mode(), 'tables': lambda: tables_mode(), 'figs': lambda: figs_mode(sys.argv[2])}[sys.argv[1]]()
