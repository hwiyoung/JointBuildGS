"""덧붙임 1 1·2·3·5절 채점(참값은 정답·목표 맞음에서만). 판단은 g8_score.Data 와 judge_lib 그대로(규칙·값 안 바꿈).
1 판정 넷과 판정을 정한 단계(judge4, judge_stage), 4 x 4 행렬(칸마다 넓이, 줄 안 %, 목표 맞음 줄 안 %, 칸 안 목표 맞음 %), 셋으로 합친 행렬 = 묶음 나 t74_confusion 점검.
2 목표 높이 h_T, τ_T, 목표 맞음(heights_<prior>.npz 의 후보에서 판정·길로 고름), 고른 자료 정확도(앞 묶음 '목표 정확도').
3 경우별 추적 표(①만 판 1 -> ② 더함 판 2 -> ③ 더함 판 4, 학습 전 목표, 학습 뒤 비움, 비교 열 넷), 상한 보조표, 문턱 곡선.
5 정답 영상 틀림인데 판 4 가 두 자료인 패치의 |h_I|, |d|, L, (가)·(나) 넓이, 목표 맞음.
사용: GT_STAGE=ga3 g15_score_add1.py"""
from common import *
import pandas as pd
import judge_lib as JL
import g8_score as G8
from target_check import J4, T4
A1 = json.loads((C/'judgeeval_v1_add1.json').read_text()); assert sha(C/'judgeeval_v1_add1.json') == json.loads((C/'judgeeval_v1_add1.lock.json').read_text())['config_sha256'], 'add1 config changed after lock'
TD = D/'tables/다'; TN4 = J4; OUTR = [(4, '둘 다 틀림'), (5, '정답 없음'), (-1, '사전 정보 높이 없음')]
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def name1(k): return ('두 번 재기' if k['two_pass'] else f"길이 {['짧음', '중간', '긺(본)'][k['h']]}") + f" · {'평균' if k['rep'] == 'mean' else '중앙값'} · 크기 경계 {'넣음' if k['size'] else '뺌'} · 한계 {'PM' if k['Lver'] == 'pm' else '원문'}"
CAND1 = [dict(h=h, rep=rp, size=sz, Lver=lv, two_pass=tp) for tp, hs in [(False, [0, 1, 2]), (True, [2])] for h in hs for rp in ['mean', 'median'] for sz in [False, True] for lv in ['pm', 'orig']]
def judge4(r1, r2, a, b, use2, use3):
    """판정 넷(0 두 자료, 1 영상, 2 영상 없음, 3 영상 틀림), 단계(1,2,3), 기본 판정 여부, 영상의 h_M 출처(0 ① d, 1 ③ 일관 평균, 2 ③ 시작 점 모두 평균)."""
    N = len(r1); j = np.full(N, -1, np.int8); st = np.zeros(N, np.int8); df = np.zeros(N, bool); src = np.full(N, -1, np.int8)
    m = r1 == JL.SAME; j[m] = 0; st[m] = 1
    m = r1 == JL.DIFF; st[m] = 3
    if use3: j[m & (a == 1)] = 1; j[m & (a != 1)] = 3; src[m & (a == 1)] = 0
    else: j[m] = 1; df[m] = True; src[m] = 0
    m = r1 == JL.NONE
    if use2:
        g = m & (r2 == 0); j[g] = 2; st[g] = 2; g = m & (r2 == 1); st[g] = 3
        if use3: j[g & (b == 1)] = 1; j[g & (b != 1)] = 3; src[g & (b == 1)] = 1
        else: j[g] = 1; df[g] = True; src[g] = 2
    else: j[m] = 2; st[m] = 2; df[m] = True
    return j, st, df, src
def merge3(j4): return np.where(j4 == 0, 0, np.where(j4 == 1, 1, np.where(np.isin(j4, [2, 3]), 2, 3)))
class Plan:
    def __init__(s, name, j4, hcol, split=True, st=None, df=None): s.name, s.j4, s.hcol, s.split, s.st, s.df = name, j4, hcol, split, st, df
def build_plans(d, Hn):
    col = {n: i for i, n in enumerate(Hn)}; N = len(d.t); out = []
    def hcols(j4, src, rep='mean', hh=None):
        hh = np.full(N, 2) if hh is None else hh; rp = 'mean' if rep == 'mean' else 'med'
        dcol = np.array([col[f'd_{rp}_{x}'] for x in range(3)])[hh]; mcol = np.array([col[f'mix_{rp}_{x}'] for x in range(3)])[hh]
        h = np.full(N, col['0']); h[j4 == 0] = mcol[j4 == 0]; h[(j4 == 1) & (src == 0)] = dcol[(j4 == 1) & (src == 0)]; h[(j4 == 1) & (src == 1)] = col['hM3c']; h[(j4 == 1) & (src == 2)] = col['hM3a']; return h
    r1 = d.r1(); r2 = d.r2(); a, b = d.r3()
    for k in [1, 2, 3, 4]:
        j, st, df, src = judge4(r1, r2, a, b, k in (2, 4), k in (3, 4)); assert np.array_equal(merge3(j)[j >= 0], d.plan(k)[j >= 0]); out.append(Plan(f'판 {k}', j, hcols(j, src), True, st, df))
    none = r1 == 2; o1 = r1.copy(); o1[d.t == 0] = 0; o1[np.isin(d.t, [1, 2, 4])] = 1; o1[d.t == 3] = 2
    o2 = r2.copy(); o2[none & (d.t == 1)] = 1; o2[none & np.isin(d.t, [0, 2, 3, 4])] = 0
    oa = a.copy(); ob = b.copy(); img_ok = np.isin(d.t, [0, 1]); bad = np.isin(d.t, [2, 3]); oa[img_ok] = 1; oa[bad] = 0; ob[img_ok] = 1; ob[bad] = 0
    for nm, args in [('상한: ①만 정답', (o1, r2, a, b)), ('상한: ②만 정답', (r1, o2, a, b)), ('상한: ③만 정답', (r1, r2, oa, ob))]:
        j, st, df, src = judge4(*args, True, True); out.append(Plan(nm, j, hcols(j, src), True, st, df))
    best = json.loads((D/'tables/나/checks.json').read_text())[d.prior]['best']; k1 = [k for k in CAND1 if name1(k) == best['step1']][0]
    rb1 = d.r1(**k1); rb2 = d.r2(**best['step2']); ab, bb = d.r3(best['step3']); j, st, df, src = judge4(rb1, rb2, ab, bb, True, True)
    if k1['two_pass']: hh = np.where(d.r1(**dict(k1, two_pass=False, h=0)) != 2, 0, 2)
    else: hh = np.full(N, k1['h'])
    out.append(Plan('판 4(가장 나은 후보)', j, hcols(j, src, k1['rep'], hh), True, st, df))
    jc = d.S1['jc2']; j = np.array([{0: 0, 1: 3, 2: 1, 4: 2}.get(int(x), -1) for x in jc], np.int8); h = np.full(N, col['0']); h[j == 0] = col['curmix']; h[j == 1] = col['cur']; out.append(Plan('JUDGECHECK-v2 본 방법', j, h))
    tab = pd.read_csv(inp('patch_table', prior=d.prior), usecols=['combo_D_judgment']).combo_D_judgment.values[d.idx]; mp = {'일치': 0, '영상 깊이 사용': 1, '사전정보 사용': 3, '결측': 2}
    j = np.array([mp.get(x, -1) for x in tab], np.int8); h = np.full(N, col['0']); h[j == 0] = col['curmix']; h[j == 1] = col['cur']; out.append(Plan('11/22 구조', j, h))
    out.append(Plan('늘 사전 정보', np.full(N, 2, np.int8), np.full(N, col['0']), split=False)); out.append(Plan('늘 영상', np.full(N, 1, np.int8), np.full(N, col['d_mean_2'])))
    return out
def main():
    c = cfg(); T = Timer(); rows_m = []; rows_tr = []; rows_up = []; rows_cur = []; rows5 = []; rows_chk = []; rec = dict(at=now(), scientific_verdict=None); old = pd.read_csv(D/'tables/나/t74_confusion.csv')
    for prior in PRIORS:
        d = G8.Data(prior, c); Hz = loadz(O/'work'/STAGE/f'heights_{prior}.npz'); assert np.array_equal(Hz['patch_index'], d.idx); Hn = [str(x) for x in Hz['names']]; OK = Hz['ok']; HH = Hz['H']; TT = Hz['TAU']
        Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz', ['n_b0']); tm = np.array([T4.get(int(x), -1) for x in d.t]); N = len(d.t); rr = np.arange(N)
        plans = build_plans(d, Hn); per = {}
        for p in plans:
            ok = OK[rr, p.hcol]; hT = HH[rr, p.hcol]; tT = TT[rr, p.hcol]; srcok = G8.tcorrect(d.t, merge3(p.j4)); per[p.name] = (ok, hT, tT, srcok)
            for sn, sm in G8.surfaces(d):
                for (vn, vm), (un, w) in G8.UV(d):
                    m = sm & vm
                    # 셋 합친 행렬 점검
                    if un in ('넓이', '점'):
                        o = old[(old.plan == p.name) & (old.prior == PN[prior]) & (old.surface == sn) & (old.version == vn) & (old.unit == un)]
                        if len(o):
                            j3 = merge3(p.j4); bad = []
                            for ti, tn in enumerate(G8.TN[:-1] + [FWD_X]):
                                tv = ti if ti < 6 else -1; orow = o[o.truth == tn]
                                for k3, cn in enumerate(['두 자료', '영상', '사전 정보', '그 밖']):
                                    v = w[m & (d.t == tv) & (j3 == k3)].sum()
                                    if len(orow) and not np.isclose(v, float(orow[cn].iloc[0]), rtol=1e-9, atol=1e-6): bad.append((tn, cn, v, float(orow[cn].iloc[0])))
                            rows_chk.append(dict(plan=p.name, prior=PN[prior], surface=sn, version=vn, unit=un, cells_different=len(bad), first=str(bad[:2])))
                    cols = TN4 if p.split else ['두 자료', '영상', '사전 정보(나누지 않음)']; jj = p.j4 if p.split else merge3(p.j4)
                    for ti, tn in list(enumerate(TN4)) + [(None, x) for x in ['둘 다 틀림', '정답 없음', '사전 정보 높이 없음']]:
                        mm = m & ((tm == ti) if ti is not None else (d.t == dict(OUTR)[0] if False else d.t == {x[1]: x[0] for x in OUTR}[tn])); tot = w[mm].sum()
                        r = dict(plan=p.name, prior=PN[prior], surface=sn, version=vn, unit=un, truth=tn, in_matrix=ti is not None, total=tot, target_ok_total=w[mm & ok].sum(), target_acc_row=100*w[mm & ok].sum()/tot if tot else np.nan)
                        for k, cn in enumerate(cols + ['그 밖']):
                            kk = k if k < len(cols) else -1; cm = mm & ((jj == kk) if kk >= 0 else ~np.isin(jj, range(len(cols)))); x = w[cm].sum()
                            r[f'{cn}'] = x; r[f'{cn} 줄 %'] = 100*x/tot if (tot and ti is not None) else np.nan; r[f'{cn} 목표 맞음 줄 %'] = 100*w[cm & ok].sum()/tot if (tot and ti is not None) else np.nan; r[f'{cn} 칸 안 목표 맞음 %'] = 100*w[cm & ok].sum()/x if x else np.nan
                        rows_m.append(r)
                    tot = w[m & (tm >= 0)].sum(); s_ = dict(plan=p.name, prior=PN[prior], surface=sn, version=vn, unit=un, truth='행렬 합', in_matrix=False, total=tot, target_ok_total=w[m & (tm >= 0) & ok].sum(), target_acc_row=100*w[m & (tm >= 0) & ok].sum()/tot if tot else np.nan)
                    for k, cn in enumerate(cols + ['그 밖']):
                        kk = k if k < len(cols) else -1; s_[cn] = w[m & (tm >= 0) & ((jj == kk) if kk >= 0 else ~np.isin(jj, range(len(cols))))].sum()
                    rows_m.append(s_)
        # 3 추적 표
        J = {p.name: p for p in plans}
        for sn, sm in G8.surfaces(d):
            for (vn, vm), (un, w) in G8.UV(d):
                m = sm & vm; base = w[m].sum()
                for k, cn in list(enumerate(TN4)) + [(None, '전체(채점한 넓이)')]:
                    mm = m & ((tm == k) if k is not None else (tm >= 0)); tot = w[mm].sum()
                    def ja(pn): p = J[pn]; return 100*w[mm & (p.j4 == (k if k is not None else tm))].sum()/tot if tot else np.nan
                    def ja3(pn): p = J[pn]; return 100*w[mm & G8.jcorrect(d.t, merge3(p.j4))].sum()/tot if tot else np.nan
                    def ta(pn): return 100*w[mm & per[pn][0]].sum()/tot if tot else np.nan
                    def sa(pn): return 100*w[mm & per[pn][3]].sum()/tot if tot else np.nan
                    lab = f'{cn} ({tot:,.1f}, {100*tot/base:.1f} %)' if un == '넓이' else f'{cn} ({tot:,.0f} 점, {100*tot/base:.1f} %)'
                    for acc, f in [('판단', ja), ('판단(셋, 앞 묶음 정의)', ja3), ('목표', ta), ('고른 자료', sa)]:
                        r = dict(prior=PN[prior], surface=sn, version=vn, unit=un, case=cn, case_label=lab, case_total=tot, case_share=100*tot/base if base else np.nan, accuracy=acc, **{'①만 (판 1)': f('판 1'), '② 더함 (판 2)': f('판 2'), '③ 더함 (판 4)': f('판 4')})
                        r['학습 전 목표'] = ta('판 4') if acc == '목표' else np.nan; r['학습 뒤'] = np.nan
                        for cmp_ in ['판 3', '늘 영상', '늘 사전 정보', 'JUDGECHECK-v2 본 방법']: r[f'비교: {cmp_}'] = f(cmp_) if acc in ('목표', '고른 자료') or (acc == '판단(셋, 앞 묶음 정의)') else np.nan
                        if acc == '판단(셋, 앞 묶음 정의)' and k is not None and k in (2, 3): pass
                        rows_tr.append(r)
                        if acc in ('판단', '목표'):
                            rows_up.append(dict(prior=PN[prior], surface=sn, version=vn, unit=un, case=cn, case_total=tot, accuracy=acc, **{'판 4': f('판 4'), '상한: ①만 정답': f('상한: ①만 정답'), '상한: ②만 정답': f('상한: ②만 정답'), '상한: ③만 정답': f('상한: ③만 정답'), '판 4(가장 나은 후보)': f('판 4(가장 나은 후보)')}))
                out_ = m & (tm < 0)
                for tv, tn in OUTR:
                    mm = m & (d.t == tv); rows_tr.append(dict(prior=PN[prior], surface=sn, version=vn, unit=un, case=f'채점 밖: {tn}', case_label=f'채점 밖: {tn} ({w[mm].sum():,.1f})', case_total=w[mm].sum(), case_share=100*w[mm].sum()/base if base else np.nan, accuracy='목표 맞음 넓이(분모 밖)', **{'③ 더함 (판 4)': w[mm & per['판 4'][0]].sum()}))
        # 문턱 곡선
        okc = Hz['ok_curve']; cn_ = [str(x) for x in Hz['curve_names']]; tc = d.tc
        for kk, x in enumerate(c['truth']['threshold_curve_m']):
            tt = tc[:, 1+kk]; tmk = np.array([T4.get(int(v), -1) for v in tt]); ok0 = Z['n_b0'][:, 1+kk] >= c['truth']['min_points'][0]
            for pn in ['판 1', '판 4', 'JUDGECHECK-v2 본 방법', '11/22 구조']:
                p = J[pn]; hn = np.array(Hn)[p.hcol]; okk = np.zeros(N, bool)
                for hi, h in enumerate(cn_): okk[hn == h] = okc[hn == h, hi, kk]
                okk[hn == '0'] = ok0[hn == '0']; miss = ~np.isin(hn, cn_ + ['0'])
                if miss.any(): okk[miss] = False
                for sn, sm in G8.surfaces(d):
                    for (vn, vm), (un, w) in G8.UV(d):
                        mm = sm & vm & (tmk >= 0); tot = w[mm].sum()
                        rows_cur.append(dict(tau_m=x, plan=pn, prior=PN[prior], surface=sn, version=vn, unit=un, judgment_acc4=100*w[mm & (p.j4 == tmk)].sum()/tot if tot else np.nan, target_acc=100*w[mm & okk].sum()/tot if tot else np.nan, height_outside_curve_m2=float(d.area[miss].sum())))
        # 5절
        p4 = J['판 4']; ok4 = per['판 4'][0]; Zh = loadz(O/'work'/STAGE/f'truth_{prior}.npz', ['h_I'])['h_I'][:, 0]; dd = d.S1['d_mean'][:, 2]; L = d.S1['L_m']
        for sn, sm in [('지붕', d.kind == 1), ('벽', d.kind == 2)]:
            for (vn, vm), (un, w) in G8.UV(d):
                m = sm & vm & (d.t == 2) & (p4.j4 == 0)
                if not m.any(): continue
                a_ = np.abs(Zh); r = dict(prior=PN[prior], surface=sn, version=vn, unit=un, total=w[m].sum(), patches=int(m.sum()))
                for lo, hi in [(0, .15), (.15, .30), (.30, .50), (.50, 1.0), (1.0, np.inf)]: r[f'|h_I| {lo:g}~{hi:g} m'] = w[m & (a_ >= lo) & (a_ < hi)].sum()
                r['|d| 중앙값 m'] = float(np.median(np.abs(dd[m]))); r['L 중앙값 m'] = float(np.median(L[m])); r['|h_I| 중앙값 m'] = float(np.median(a_[m]))
                r['(가) |h_I| ≤ L'] = w[m & (a_ <= L)].sum(); r['(나) |h_I| > L, |d| ≤ L'] = w[m & (a_ > L)].sum(); r['목표 맞음 %'] = 100*w[m & ok4].sum()/w[m].sum()
                r['(가) 목표 맞음 %'] = 100*w[m & (a_ <= L) & ok4].sum()/max(w[m & (a_ <= L)].sum(), 1e-12); r['(나) 목표 맞음 %'] = 100*w[m & (a_ > L) & ok4].sum()/max(w[m & (a_ > L)].sum(), 1e-12); rows5.append(r)
        # 패치마다 파일
        sv = dict(patch_index=d.idx, answer=d.t, two_layer=d.two)
        for p in plans:
            if p.name.startswith('판') or p.name.startswith('상한') or p.name in ('JUDGECHECK-v2 본 방법', '11/22 구조'):
                ok, hT, tT, so = per[p.name]; sv.update({f'J4_{p.name}': p.j4, f'hT_{p.name}': hT, f'tauT_{p.name}': tT, f'ok_{p.name}': ok, f'srcok_{p.name}': so})
                if p.st is not None: sv[f'stage_{p.name}'] = p.st; sv[f'default_{p.name}'] = p.df
        savez(O/'work'/STAGE/f'judge4_{prior}.npz', **sv)
        fwd = pd.read_csv(O/f'forward_{prior}_ga3.csv.gz', usecols=['patch_index', 'patch_id', 'building', 'surface', 'place', 'area_m2', 'answer']); fwd = fwd.set_index('patch_index').loc[d.idx].reset_index()
        ok, hT, tT, so = per['판 4']; p = J['판 4']; stn = {1: '①', 2: '②', 3: '③'}
        fwd['judge4'] = [J4[x] if x >= 0 else '그 밖' for x in p.j4]; fwd['judge_stage'] = [stn[x] + ('(기본)' if f else '') for x, f in zip(p.st, p.df)]; fwd['h_T'] = hT; fwd['tau_T'] = tT; fwd['target_ok'] = ok; fwd['src_ok'] = so
        fwd.to_csv(O/f'judge4_plan4_{prior}_ga3.csv.gz', index=False)
        rec[prior] = dict(patches=N, plan4_target_acc_area=float(100*d.area[(tm >= 0) & per['판 4'][0]].sum()/d.area[tm >= 0].sum()), plan4_judgment4_area=float(100*d.area[(tm >= 0) & (p.j4 == tm)].sum()/d.area[tm >= 0].sum()))
    chk = pd.DataFrame(rows_chk); write('t1_check_merge3', chk, '판정 넷을 셋으로 합친 행렬 = 묶음 나 t74_confusion 점검(다른 칸 수)'); rec['merge3_cells_different'] = int(chk.cells_different.sum())
    if rec['merge3_cells_different']: issue(f'셋으로 합친 행렬이 t74_confusion 과 다름: {chk[chk.cells_different > 0].head().to_dict("records")}'); dump(TD/'checks.json', rec); raise SystemExit('merge3 differs: stop')
    mx = pd.DataFrame(rows_m); write('t1_matrix4', mx, '4 x 4 오류 행렬(긴 꼴): 줄 = 정답 넷 + 채점 밖 셋, 칸 = 판정 넷 + 그 밖. 칸마다 넓이(또는 점), 줄 안 %, 목표 맞음 줄 안 %(줄마다 더하면 그 경우 목표 정확도), 칸 안 목표 맞음 %. 늘 사전 정보는 사전 정보를 나누지 않은 3열')
    tr = pd.DataFrame(rows_tr); write('t3_trace', tr, '경우별 추적 표(긴 꼴). 판단 = 판정 넷 대각선, 판단(셋) = 앞 묶음 판정 정확도 정의, 목표 = 목표 높이가 참값 τ_T 안, 고른 자료 = 앞 묶음 목표 정확도. 학습 뒤는 비움(target_check.py 로 채움)')
    write('t3_upper', pd.DataFrame(rows_up), '바꿔 끼운 상한 보조표(판정 넷 판단·목표 정확도)'); write('t3_threshold_curve', pd.DataFrame(rows_cur), '문턱 곡선: 정답과 τ_T 모두 같은 τ, 판정 넷 판단 정확도와 목표 정확도')
    write('t5_image_error', pd.DataFrame(rows5), '5절: 정답 사전 정보·영상 틀림인데 판 4 가 두 자료. |h_I| = 정답의 영상 자리 크기, d = ① 본 판 평균(지붕 10 / 벽 5 m), L = 저장 한계')
    for (r_, s_) in [(mx, 'm'), (tr, 't')]: assert (pd.to_numeric(r_.filter(like='%').stack(), errors='coerce').dropna() <= 100 + 1e-9).all() if s_ == 'm' else True
    trn = tr[tr.accuracy.isin(['판단', '목표', '판단(셋, 앞 묶음 정의)', '고른 자료'])][['①만 (판 1)', '② 더함 (판 2)', '③ 더함 (판 4)']].to_numpy(float); assert np.nanmax(trn) <= 100 + 1e-9, 'over 100 %'
    # 행렬과 추적 표 맞댐
    for _, r in tr[(tr.accuracy == '목표') & ~tr.case.str.startswith('전체') & ~tr.case.str.startswith('채점')].iterrows():
        g = mx[(mx.plan == '판 4') & (mx.prior == r.prior) & (mx.surface == r.surface) & (mx.version == r.version) & (mx.unit == r.unit) & (mx.truth == r.case)].iloc[0]
        s = sum(g[f'{cn} 목표 맞음 줄 %'] for cn in TN4 + ['그 밖'] if np.isfinite(g[f'{cn} 목표 맞음 줄 %'])); assert np.isclose(s, r['③ 더함 (판 4)'], atol=1e-6), (r.case, s, r['③ 더함 (판 4)'])
    rec['matrix_trace_consistent'] = True; rec['seconds'] = T.s(); dump(TD/'checks.json', rec); progress(f'덧붙임 1 채점(1·2·3·5절): {rec}'); print(json.dumps(jsafe(rec), ensure_ascii=False))
if __name__ == '__main__': main()
