"""덧붙임 1 3절(점검으로 쓰는 판)·2절(A2 패치 값의 AUC, 패치 표 열). 참값은 처음 상태·채점에만(mf4 와 같은 쓰임). 걸러내기에는 쓰지 않음.
판 '점검': 점군·패치 값 = 지금 점군 그대로, 판정 = 지금 점군의 구조 하한에서 출발. 차이가 유의한 패치 가운데 그 방법에서 원통 안 살아남은 점(n, 판정에 쓰는 면 가까이 점)이 4개 미만인 패치만
  사전정보 사용(1)으로 바꿈. 곡선: 살아남은 비율(원통 안 모든 점 raw_n 의 비) ≤ 문턱 이면 바꿈, 문턱 0 · 0.05 · 0.1 · 0.2 · 0.3 · 0.5 (고르지 않음).
바뀐 넓이 비율(차이가 유의한 패치, 처음 상태마다): 영상 깊이 오류 = 찾은 비율, 사전정보 오류 = 잘못 되돌린 비율, 두 자료 모두 유효.
  JUDGESTRUCT-v1 셈 1-4 와 같은 분모의 F(차이가 유의한 패치 가운데 영상 깊이 오류가 아닌 모든 넓이, 처음 상태 없는 패치 포함)도 함께 냄.
사용: mf11_check.py <method> [...]"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import a1_variants as A1
import js3_figs as J3
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mfcommon as MC
from mf4_judge import load_method
sys.path.insert(0, '/repo/scripts/phd/main_judgeprobe_v1')
import importlib.util
_s = importlib.util.spec_from_file_location('jp_common', '/repo/scripts/phd/main_judgeprobe_v1/common.py'); JPC = importlib.util.module_from_spec(_s); _s.loader.exec_module(JPC)
wauc = JPC.wauc
THR = [0, .05, .1, .2, .3, .5]
DOC = Path('/docs/tables'); FIG = Path('/docs/figures')

def setup(prior):
    d = A1.load(prior); N = len(d['kind']); A = d['area']; mi = J.VARIANTS.index('method'); hP = d['prior_height_m']; sP, sW = d['sigma_P'], d['sigma_W']; hb = d['target_h'][:, mi]
    pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int)
    g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'target_ok_v'])
    keep = np.flatnonzero(g['paired'] & np.isin(g['case'], CASES)); gid = g['gid'][keep]; cs = g['case'][keep]
    ok0 = g['target_ok_v'][mi][keep]; xyz = g['xyz'][keep]; nor = g['normal'][keep]; wall = g['gt_kind'][keep] == 2; tau = g['tau'][keep]; del g
    v = load_method(d, prior, 'none'); hM = v['mvs_mean_m']; u = v['u_M']
    def score(lo):   # mf4.score 와 같은 식
        h = J.target_height(lo, hP, hM, u, sP, sW); hc = ~((h == hb) | (np.isnan(h) & np.isnan(hb))); ok = ok0.copy(); sel = np.flatnonzero(hc[gid]); pg = gid[sel]
        if len(sel): ds = plane_distance(xyz[sel], nor[sel], d['centre'][pg], d['normal'][pg], h[pg], wall[sel]); ok[sel] = np.abs(ds) <= tau[sel]
        return ok
    same = cs == pc[gid]; valid_pc = np.isin(pc, CASES)
    def pok_of(ok):
        num = np.bincount(gid[same], weights=ok[same], minlength=N); den = np.bincount(gid[same], minlength=N); return (den > 0) & (num/np.maximum(den, 1) >= .5)
    return dict(d=d, A=A, pc=pc, gid=gid, cs=cs, score=score, pok_of=pok_of, valid_pc=valid_pc, pkind=d['kind'][gid])

JN = {0: '일치', 1: '사전정보 사용', 2: '영상 깊이 사용', 3: '제거', 4: '결측', 9: '미판정'}
def detail(S, prior, sn, kk, lo_u, ok_u, lo_l, ok_l, line):
    """회신 1 3절: 구조 상한과 그 줄을 처음 상태(참값 점의 경우) x 패치 판정으로 나눔 — 점 수·맞은 점 수, 그리고 패치 넓이(처음 상태 x 판정, 차이가 유의한 패치)."""
    d, A, pc, gid, cs = S['d'], S['A'], S['pc'], S['gid'], S['cs']; kp = np.isin(S['pkind'], kk); rows = []
    for c in CASES:
        for j in sorted(set(np.unique(lo_u[gid][kp & (cs == c)])) | set(np.unique(lo_l[gid][kp & (cs == c)]))):
            mu = kp & (cs == c) & (lo_u[gid] == j); ml = kp & (cs == c) & (lo_l[gid] == j)
            rows.append(dict(prior=PN[prior], surface=sn, line=line, table='점', state=CASE[c], judgment=JN.get(int(j), str(j)), upper_points=int(mu.sum()), upper_ok=int(ok_u[mu].sum()), line_points=int(ml.sum()), line_ok=int(ok_l[ml].sum())))
    km = np.isin(d['kind'], kk)
    for s_ in STATE_ORDER:
        for j in sorted(set(np.unique(lo_u[km & (pc == s_)])) | set(np.unique(lo_l[km & (pc == s_)]))):
            rows.append(dict(prior=PN[prior], surface=sn, line=line, table='패치 넓이', state=STATE[s_], judgment=JN.get(int(j), str(j)), upper_area_m2=float(A[km & (pc == s_) & (lo_u == j)].sum()), line_area_m2=float(A[km & (pc == s_) & (lo_l == j)].sum())))
    return rows

def summary(S, prior, lo, label, extra):
    d, A, pc, gid, cs = S['d'], S['A'], S['pc'], S['gid'], S['cs']; ok = S['score'](lo); pok = S['pok_of'](ok); rows = []
    for sn, kk in SURF[prior]:
        kp = np.isin(S['pkind'], kk); km = np.isin(d['kind'], kk); r = dict(prior=PN[prior], surface=sn, line=label, **extra)
        for c in CASES:
            m = kp & (cs == c); r[f'ok_{CASE[c]}'] = 100*ok[m].mean(); mp = km & (pc == c); r[f'patch_ok_{CASE[c]}'] = 100*A[mp & pok].sum()/A[mp].sum()
        r['ok_전체'] = 100*ok[kp].mean(); mp = km & S['valid_pc']; r['patch_ok_전체'] = 100*A[mp & pok].sum()/A[mp].sum()
        for lv in ['ok', 'patch_ok']:
            vals = np.array([r[f'{lv}_{CASE[c]}'] for c in CASES]); r[f'{lv}_네 경우 평균'] = float(vals.mean()); r[f'{lv}_최솟값'] = float(vals.min()); r[f'{lv}_최대 격차'] = float(vals.max() - vals.min())
        rows.append(r)
    return rows, ok

def flip_rates(S, prior, sig, flip):
    """회신 1 2절: 비율 옆에 넓이(m²)·참값 점 수(그 패치에 속한 네 경우 참값 점), 분모도."""
    d, A, pc = S['d'], S['A'], S['pc']; out = []; gp = np.bincount(S['gid'], minlength=len(A))
    for sn, kk in SURF[prior]:
        km = np.isin(d['kind'], kk) & sig; r = dict(surface=sn)
        for s_, nm in [(2, 'found_imgerr_pct'), (1, 'wrong_priorerr_pct'), (0, 'changed_bothvalid_pct'), (4, 'changed_missing_pct')]:
            mm = km & (pc == s_); a = A[mm].sum(); r[nm] = 100*A[mm & flip].sum()/a if a else np.nan
            b = nm.replace('_pct', ''); r[f'{b}_area_m2'] = float(A[mm & flip].sum()); r[f'{b}_gt_points'] = int(gp[mm & flip].sum()); r[f'den_{b}_area_m2'] = float(a); r[f'den_{b}_gt_points'] = int(gp[mm].sum())
        oth = km & (pc != 2); r['F_js_pct'] = 100*A[oth & flip].sum()/A[oth].sum(); r['changed_area_m2'] = float(A[km & flip].sum()); r['changed_patches'] = int((km & flip).sum())
        out.append(r)
    return out

def load_pm(prior, m, d):
    """판정 결과(judge/patch_<m>)가 있으면 그것, 없으면(회신 1 의 문턱 판, 원통 값만) patch/<m> 구역 값을 d 차례로 모음."""
    f = MC.O/'judge'/prior/f'patch_{m}.npz'
    if f.exists(): return dict(np.load(f))
    out = {k: np.full(len(d['kind']), -1) for k in ['n', 'raw_n']}
    for ti, t in enumerate(d['tiles']):
        mm = np.flatnonzero(d['tile'] == ti); z = loadz(MC.O/'patch'/m/f'{t}.npz')
        if f'{prior}__patch_id' not in z: continue
        assert np.array_equal(z[f'{prior}__patch_id'], d['patch_id'][mm])
        for k in out: out[k][mm] = z[f'{prior}__{k}']
    return out

def a2_patch(prior, d, sub='a2_patch'):
    keys = ['raw_n', 'c_median', 'c_ge5_frac', 'f_ratio_mean']; out = {k: np.full(len(d['kind']), np.nan) for k in keys}
    for ti, t in enumerate(d['tiles']):
        m = np.flatnonzero(d['tile'] == ti); z = loadz(MC.O/sub/f'{t}.npz'); assert np.array_equal(z[f'{prior}__patch_id'], d['patch_id'][m])
        for k in keys: out[k][m] = z[f'{prior}__{k}']
    return out

def main(methods):
    MC.cfg(); T = Timer(); RM, RF, RC, AUC, OVER, DET = [], [], [], [], [], []
    js = pd.read_csv(Path('/repo/docs/experiments/phd/main_judgestruct_v1/tables/t6_rejudge.csv')) if False else None
    for prior in ['LoD2', 'ALS']:
        S = setup(prior); jd = MC.O/'judge'/prior; b = np.load(jd/'patch_none.npz'); lo0 = b['lo']; sig = b['sig']; rn0 = b['raw_n']
        base_rows, ok_base = summary(S, prior, lo0, '구조 하한 (지금 점군)', dict(method='none', mode='-', threshold=np.nan)); RM += base_rows
        # 검산: 아무 패치도 바꾸지 않으면 구조 하한(지금)과 같다
        zero_rows, ok_zero = summary(S, prior, lo0.copy(), '점검 판, 바꾼 패치 0 (검산)', dict(method='-', mode='check0', threshold=np.nan))
        RC.append(dict(prior=PN[prior], check='점검 판에서 바꾼 패치 0 = 구조 하한(지금)', points=len(ok_zero), equal=int((ok_zero == ok_base).sum()), passed=bool(np.array_equal(ok_zero, ok_base))))
        up = np.load(MC.JS/prior/'fig_arrays.npz')['up']; up_rows, ok_up = summary(S, prior, up, '구조 상한 (지금, 참값으로) — 이 셈에서 다시 냄', dict(method='upper', mode='-', threshold=np.nan))
        t6 = pd.read_csv(DOC/'t6_rejudge.csv'); t6u = t6[(t6.prior == PN[prior]) & (t6.line == '구조 상한 (지금 점군, 참값으로; JUDGESTRUCT-v1)')].set_index('surface')
        RC.append(dict(prior=PN[prior], check='구조 상한 다시 냄(JS fig_arrays up) = t6 구조 상한 (점 단위 전체, 면마다)', diffs={r['surface']: float(r['ok_전체'] - t6u.loc[r['surface'], 'ok_전체']) for r in up_rows},
                       passed=bool(all(abs(r['ok_전체'] - t6u.loc[r['surface'], 'ok_전체']) < 1e-9 for r in up_rows))))
        UPT = {r['surface']: r for r in up_rows}
        def over(rows, okl, lo_l, label, mode, thr):
            for r in rows:
                u = UPT[r['surface']]
                for lv in ['ok_전체', 'patch_ok_전체']:
                    if r[lv] > u[lv] + 1e-9: OVER.append(dict(prior=PN[prior], surface=r['surface'], line=label, mode=mode, threshold=thr, level='점' if lv == 'ok_전체' else '패치', line_value=r[lv], upper_value=u[lv]))
                if mode == '점 4개 미만' and (r['ok_전체'] > u['ok_전체'] + 1e-9 or r['patch_ok_전체'] > u['patch_ok_전체'] + 1e-9):
                    DET.extend(detail(S, prior, r['surface'], dict(SURF[prior])[r['surface']], up, ok_up, lo_l, okl, label))
        for m in methods:
            q = load_pm(prior, m, S['d'])
            flip = sig & (q['n'] >= 0) & (q['n'] < 4); lo = lo0.copy(); lo[flip] = 1
            rows, okl = summary(S, prior, lo, f'점검 판 ({MC.MNAME[m]})', dict(method=m, mode='점 4개 미만', threshold=np.nan))
            for r, fr in zip(rows, flip_rates(S, prior, sig, flip)): assert r['surface'] == fr['surface']; r.update({k: v for k, v in fr.items() if k != 'surface'})
            RM += rows; over(rows, okl, lo, f'점검 판 ({MC.MNAME[m]})', '점 4개 미만', np.nan)
            with np.errstate(invalid='ignore', divide='ignore'): ratio = np.where(rn0 > 0, q['raw_n']/np.maximum(rn0, 1), np.nan)
            for t in THR:
                flip = sig & np.isfinite(ratio) & (ratio <= t); lo = lo0.copy(); lo[flip] = 1
                rows, okl = summary(S, prior, lo, f'곡선 ({MC.MNAME[m]})', dict(method=m, mode='살아남은 비율 ≤ 문턱', threshold=t))
                for r, fr in zip(rows, flip_rates(S, prior, sig, flip)): r.update({k: v for k, v in fr.items() if k != 'surface'})
                RF += rows; over(rows, okl, lo, f'곡선 ({MC.MNAME[m]})', '살아남은 비율 ≤ 문턱', t)
            print('CHECKMODE', prior, m, round(T.s()), flush=True)
        for a2m, sub, tl in [('A2', 'a2_patch', '1 % (본 판)'), ('A2d0p5', 'a2_patch_t0p5', '0.5 % (세션 판)'), ('A2d0p2', 'a2_patch_t0p2', '0.2 % (세션 판)'), ('A2d0p1', 'a2_patch_t0p1', '0.1 % (세션 판)')]:
            if a2m not in methods or not (MC.O/sub).is_dir(): continue
            d = S['d']; a2 = a2_patch(prior, d, sub); A = S['A']; pc = S['pc']
            RC.append(dict(prior=PN[prior], check=f'{a2m} 패치 값의 원통 점 수 = patch/none raw_n', patches=int((rn0 >= 0).sum()), equal=int((a2['raw_n'][rn0 >= 0] == rn0[rn0 >= 0]).sum()), passed=bool(np.array_equal(a2['raw_n'][rn0 >= 0], rn0[rn0 >= 0]))))
            for sn, kk in SURF[prior]:
                km = np.isin(d['kind'], kk) & sig
                for k, lab in [('c_median', 'c 중앙값'), ('c_ge5_frac', 'c ≥ 5 인 점의 비율'), ('f_ratio_mean', 'f ÷ (c + f) 평균')]:
                    x = a2[k]; e = km & (pc == 2); p = km & (pc == 1); v = km & (pc == 0)
                    AUC.append(dict(prior=PN[prior], surface=sn, depth_tol=tl, method=a2m, value=lab, auc_imgerr_vs_priorerr=wauc(x[e], A[e], x[p], A[p]), auc_imgerr_vs_bothvalid=wauc(x[e], A[e], x[v], A[v]),
                                    n_imgerr=int(e.sum()), n_priorerr=int(p.sum()), n_bothvalid=int(v.sum()),
                                    **{f'median_{nm}': wq(x[g_ & np.isfinite(x)], A[g_ & np.isfinite(x)], .5) for nm, g_ in [('imgerr', e), ('priorerr', p), ('bothvalid', v)]}))
            if a2m != 'A2': continue
            f = MC.O/'judge'/f'patches_{prior}.csv.gz'; df = pd.read_csv(f); assert np.array_equal(df['patch_id'].values, d['patch_id'])
            df['A2_c_median'] = a2['c_median']; df['A2_c_ge5_frac'] = a2['c_ge5_frac']; df['A2_f_over_c_plus_f_mean'] = a2['f_ratio_mean']
            df.to_csv(f, index=False, compression='gzip')
    tab = lambda rows, name, note: (pd.DataFrame(rows).to_csv(DOC/f'{name}.csv', index=False), dump(DOC/f'{name}.json', dict(rows=json.loads(pd.DataFrame(rows).to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None)))
    f1 = lambda v: '' if v is None or not np.isfinite(v) else f'{v:.1f}'
    # t8_check_mode
    js = pd.read_csv(DOC/'t6_rejudge.csv'); JS_LINES = ['본 방법 (JUDGESTRUCT-v1)', '구조 하한 (JUDGESTRUCT-v1)', '구조 상한 (지금 점군, 참값으로; JUDGESTRUCT-v1)']
    keep = js[js.line.isin(JS_LINES)].to_dict('records'); allrows = keep + RM
    tab(allrows, 't8_check_mode', '판 점검(덧붙임 1 3절). 앞의 셋은 t6_rejudge 에서 읽음.')
    L = ['# t8_check_mode', '', '덧붙임 1 3절 판 \'점검\': 점군·패치 값은 지금 그대로, 지금 점군의 구조 하한에서 출발해 차이가 유의한 패치 가운데 그 방법에서 원통 안 살아남은 점(n)이 4개 미만인 패치만 사전정보 사용으로 바꿈. '
         '찾은 = 처음 상태 영상 깊이 오류 넓이 가운데 바뀐 %, 잘못 되돌린 = 사전정보 오류 가운데, 유효 = 두 자료 모두 유효 가운데(분모는 차이가 유의한 패치). F(JS) = JUDGESTRUCT 셈 1-4 와 같은 분모(영상 깊이 오류 아닌 유의 넓이 전체).', '', 'scientific_verdict: null', '',
         '바뀐 넓이·참값 점: 괄호 (m², 그 패치들에 속한 네 경우 참값 점 수). 분모 줄 = 처음 상태마다 차이가 유의한 패치의 넓이와 참값 점 수. 문턱을 줄인 A2 판은 세션이 정한 판(COLMAP 기본값 아님).', '',
         '| 사전 정보 | 면 | 줄 | 점: 유효/사전오류/영상오류/결측 · 전체 | 점: 평균·최솟값·격차 | 패치: … · 전체 | 패치: 평균·최솟값·격차 | 찾은 % (m², 점) | 잘못 되돌린 % (m², 점) | 유효 바뀜 % (m², 점) | F(JS) % |', '|---|---|---|---|---|---|---|---|---|---|---|']
    seen_den = set()
    for r in allrows:
        if not ((r['prior'] == 'LoD2' and r['surface'] in ['지붕', '벽', '모두']) or (r['prior'] == '항공 LiDAR' and r['surface'] == '지붕')): continue
        has = r.get('found_imgerr_pct') is not None and np.isfinite(r.get('found_imgerr_pct', np.nan))
        cell = lambda b: f"{f1(r[b + '_pct'])} ({r[b + '_area_m2']:,.0f}, {r[b + '_gt_points']:,})"
        fl = f"{cell('found_imgerr')} | {cell('wrong_priorerr')} | {cell('changed_bothvalid')} | {f1(r['F_js_pct'])}" if has else ' | | | '
        if has and (r['prior'], r['surface']) not in seen_den:
            seen_den.add((r['prior'], r['surface']))
            L.append(f"| {r['prior']} | {r['surface']} | 분모 (차이가 유의한 패치) | | | | | 영상 깊이 오류 {r['den_found_imgerr_area_m2']:,.0f} m², {r['den_found_imgerr_gt_points']:,} 점 | 사전정보 오류 {r['den_wrong_priorerr_area_m2']:,.0f} m², {r['den_wrong_priorerr_gt_points']:,} 점 | 두 자료 모두 유효 {r['den_changed_bothvalid_area_m2']:,.0f} m², {r['den_changed_bothvalid_gt_points']:,} 점 | |")
        L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | " + ' / '.join(f1(r[f'ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['ok_전체'])} | {f1(r['ok_네 경우 평균'])} · {f1(r['ok_최솟값'])} · {f1(r['ok_최대 격차'])} | "
                 + ' / '.join(f1(r[f'patch_ok_{CASE[c]}']) for c in CASES) + f" · {f1(r['patch_ok_전체'])} | {f1(r['patch_ok_네 경우 평균'])} · {f1(r['patch_ok_최솟값'])} · {f1(r['patch_ok_최대 격차'])} | {fl} |")
    (DOC/'t8_check_mode.md').write_text('\n'.join(L) + '\n')
    tab(RF, 't8_check_curve', '살아남은 비율(raw_n 비) ≤ 문턱이면 사전정보 사용으로 바꿈. 문턱을 고르지 않음.')
    L = ['# t8_check_curve', '', '덧붙임 1 3절 곡선: 차이가 유의한 패치 가운데 그 방법의 살아남은 비율(원통 안 모든 점 raw_n 의 비) ≤ 문턱이면 사전정보 사용으로 바꿈(문턱 0 = 하나도 살아남지 않은 패치). 문턱을 고르지 않음. 점 단위 전체 목표 맞음.', '', 'scientific_verdict: null', '',
         '괄호 = (바뀐 넓이 m², 그 패치들의 참값 점 수). 분모는 t8_check_mode 의 분모 줄.', '',
         '| 사전 정보 | 면 | 방법 | 문턱 | 찾은 % (m², 점) | 잘못 되돌린 % (m², 점) | 유효 바뀜 % (m², 점) | F(JS) % | 바뀐 넓이 m² | 전체 목표 맞음(점) | 네 경우 평균(점) |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in RF:
        if not ((r['prior'] == 'LoD2' and r['surface'] == '모두') or (r['prior'] == '항공 LiDAR' and r['surface'] == '지붕')): continue
        cell = lambda b: f"{f1(r[b + '_pct'])} ({r[b + '_area_m2']:,.0f}, {r[b + '_gt_points']:,})"
        L.append(f"| {r['prior']} | {r['surface']} | {MC.MNAME[r['method']]} | {r['threshold']:g} | {cell('found_imgerr')} | {cell('wrong_priorerr')} | {cell('changed_bothvalid')} | {f1(r['F_js_pct'])} | {r['changed_area_m2']:.0f} | {f1(r['ok_전체'])} | {f1(r['ok_네 경우 평균'])} |")
    (DOC/'t8_check_curve.md').write_text('\n'.join(L) + '\n')
    if AUC:
        tab(AUC, 't5_A2_auc', '넓이 가중 AUC = P(영상 깊이 오류 패치 값 > 비교 무리 값) + 0.5 P(같음) (JUDGEPROBE-v1 common.wauc). 대상 = 차이가 유의한 패치(지금 점군), 무리 = 처음 상태.')
        L = ['# t5_A2_auc', '', '덧붙임 1 2절. 방법 A2(세션 판) 패치 값의 구별 정도. 넓이 가중 AUC = P(영상 깊이 오류 패치의 값 > 비교 무리의 값) + 0.5·P(같음) — JUDGEPROBE-v1 `common.wauc` 그대로. 대상 = 차이가 유의한 패치(지금 점군), 무리 = 처음 상태. 0.5 에서 멀수록 구별됨(방향은 값마다 다름). 넓이 가중 중앙값 함께.', '', 'scientific_verdict: null', '',
             '| 사전 정보 | 면 | 깊이 일치 문턱 | 값 | AUC 영상 오류 대 사전 오류 | AUC 영상 오류 대 유효 | 중앙값 영상 오류 / 사전 오류 / 유효 | 패치 수 영상 오류 / 사전 오류 / 유효 |', '|---|---|---|---|---|---|---|---|']
        for r in AUC:
            L.append(f"| {r['prior']} | {r['surface']} | {r['depth_tol']} | {r['value']} | {r['auc_imgerr_vs_priorerr']:.3f} | {r['auc_imgerr_vs_bothvalid']:.3f} | {r['median_imgerr']:.2f} / {r['median_priorerr']:.2f} / {r['median_bothvalid']:.2f} | {r['n_imgerr']:,} / {r['n_priorerr']:,} / {r['n_bothvalid']:,} |")
        (DOC/'t5_A2_auc.md').write_text('\n'.join(L) + '\n')
    # 그림 fig8
    B = pd.read_csv(Path('/repo/docs/experiments/phd/main_judgestruct_v1/tables/t14_boundary.csv'))
    FM = [m for m in methods if not m.startswith('A2d')]   # 회신 1: 그림은 본 판(1 %)만
    for prior, pn, sn in [('LoD2', 'LoD2', '모두'), ('ALS', '항공 LiDAR', '지붕')]:
        fig, axs = plt.subplots(1, 2, figsize=(11, 4.6)); meta = dict(prior=prior, surface=sn, lines=[])
        for ax, xk, xl in [(axs[0], 'wrong_priorerr_pct', '잘못 되돌린 비율 % (사전정보 오류 넓이 가운데)'), (axs[1], 'F_js_pct', 'F % (JUDGESTRUCT 셈 1-4 분모: 영상 깊이 오류가 아닌 유의 넓이)')]:
            for k, m in enumerate(FM):
                rr = [r for r in RF if r['prior'] == pn and r['surface'] == sn and r['method'] == m]; col = plt.get_cmap('tab10')(k)
                ax.plot([r[xk] for r in rr], [r['found_imgerr_pct'] for r in rr], '-o', ms=3, color=col, label=MC.MNAME[m])
                for r in rr: ax.annotate(f"{r['threshold']:g}", (r[xk], r['found_imgerr_pct']), fontsize=5, color=col, xytext=(2, 2), textcoords='offset points')
                pt = [r for r in RM if r['prior'] == pn and r['surface'] == sn and r.get('method') == m and r.get('mode') == '점 4개 미만']
                if pt: ax.plot([pt[0][xk]], [pt[0]['found_imgerr_pct']], 's', ms=6, mfc='none', color=col)
                if xk == 'wrong_priorerr_pct': meta['lines'].append(dict(method=m, curve=[dict(threshold=r['threshold'], found=r['found_imgerr_pct'], wrong=r['wrong_priorerr_pct'], F_js=r['F_js_pct'], ok_total=r['ok_전체']) for r in rr],
                                                                       lt4=dict(found=pt[0]['found_imgerr_pct'], wrong=pt[0]['wrong_priorerr_pct'], F_js=pt[0]['F_js_pct']) if pt else None))
            if xk == 'F_js_pct':
                bb = B[(B.prior == prior) & (B.surface == sn) & (B.unit == '점')].sort_values('F'); xs = 100*bb.F.values; ys = 100*bb.R_total_exact.values
                ax.plot(xs, ys, 'k--', lw=1, label='JS 셈 1-4 경계 (전체 목표 맞음 > 본 방법, 점)'); meta['boundary'] = dict(F_pct=list(map(float, xs)), R_pct=[float(y) for y in ys])
            ax.set_xlabel(xl, fontsize=7); ax.set_ylabel('찾은 비율 % (영상 깊이 오류 넓이 가운데)', fontsize=7); ax.set_xlim(left=0); ax.set_ylim(0, 100); ax.tick_params(labelsize=6)
        axs[0].legend(fontsize=6, frameon=False, loc='lower right'); axs[1].legend(fontsize=6, frameon=False, loc='lower right')
        fig.suptitle(f'{pn} {sn}: 판 점검의 곡선 — 점 옆 숫자 = 살아남은 비율 문턱, 네모 = 점 4개 미만 규칙 (문턱을 고르지 않음)', fontsize=8); fig.tight_layout(rect=[0, 0, 1, .95])
        J3.save(fig, f'fig8_check_curve_{prior}', meta)
    # 회신 1 3절: 구조 상한을 넘는 줄
    tab(OVER, 't8_over_upper_lines', '구조 상한(지금, 참값으로)보다 전체 목표 맞음이 높은 줄(점·패치 단위).')
    tab(DET, 't8_over_upper', '구조 상한을 넘는 점검 판 줄(점 4개 미만 규칙)을 처음 상태 x 판정으로 나눔.')
    L = ['# t8_over_upper', '', '회신 1 3절. 구조 상한(지금 점군, 참값으로)보다 전체 목표 맞음이 높은 줄. 값은 그대로 두고 나눠 적음. 상한 판정 = JUDGESTRUCT-v1 fig_arrays `up`(이 셈에서 다시 채점해 t6 와 같음을 확인, t8_checks).', '', 'scientific_verdict: null', '',
         '## 상한을 넘는 줄 모두', '', '| 사전 정보 | 면 | 줄 | 문턱 | 단위 | 그 줄 | 구조 상한 |', '|---|---|---|---|---|---|---|']
    for r in OVER:
        ts = '' if not np.isfinite(r['threshold']) else f"{r['threshold']:g}"
        L.append(f"| {r['prior']} | {r['surface']} | {r['line']} | {ts} | {r['level']} | {r['line_value']:.2f} | {r['upper_value']:.2f} |")
    for (pr, sn, ln), g in pd.DataFrame(DET).groupby(['prior', 'surface', 'line'], sort=False) if DET else []:
        L += ['', f'## {pr} {sn} · {ln} 대 구조 상한', '', '### 참값 점 (점의 경우 x 그 점이 속한 패치의 판정)', '', '| 처음 상태(점) | 판정 | 상한: 점 · 맞음 | 그 줄: 점 · 맞음 | 맞은 점 차(그 줄 − 상한) |', '|---|---|---|---|---|']
        for _, r in g[g.table == '점'].iterrows(): L.append(f"| {r.state} | {r.judgment} | {int(r.upper_points):,} · {int(r.upper_ok):,} | {int(r.line_points):,} · {int(r.line_ok):,} | {int(r.line_ok - r.upper_ok):+,} |")
        for c in CASES:
            gg = g[(g.table == '점') & (g.state == CASE[c])]; L.append(f"| {CASE[c]} 합 | | {int(gg.upper_points.sum()):,} · {int(gg.upper_ok.sum()):,} | {int(gg.line_points.sum()):,} · {int(gg.line_ok.sum()):,} | {int(gg.line_ok.sum() - gg.upper_ok.sum()):+,} |")
        L += ['', '### 패치 넓이 (처음 상태 x 판정, m²)', '', '| 처음 상태 | 판정 | 상한 | 그 줄 |', '|---|---|---|---|']
        for _, r in g[g.table == '패치 넓이'].iterrows(): L.append(f"| {r.state} | {r.judgment} | {r.upper_area_m2:,.1f} | {r.line_area_m2:,.1f} |")
    (DOC/'t8_over_upper.md').write_text('\n'.join(L) + '\n')
    dump(DOC/'t8_checks.json', dict(at=now(), checks=RC, seconds=T.s(), scientific_verdict=None))
    for c in RC: print('CHECK', json.dumps(jsafe(c), ensure_ascii=False), flush=True)
    MC.progress(f'mf11 점검 판·곡선 {methods} 끝, {round(T.s())} 초')

if __name__ == '__main__': main(sys.argv[1:])
