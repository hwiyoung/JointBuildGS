"""덧붙임 2 1·2절: 목표 높이의 영상 쪽 값 h_M 을 학습이 받는 저장값 mvs_mean_m(heights 의 'cur', 두 자료는 'curmix')으로 바꿔 다시 채점(판단 다시 돌리지 않음, 참값은 목표 맞음에서만).
판 1~4, 판 3, 상한 셋, 판 4(가장 나은 후보), 늘 영상의 h_T 만 바뀜. 'cur'·'curmix' 가 NaN 이면 묶음 다 값(덧붙임 2 설정 S). JUDGECHECK-v2·11/22·늘 사전 정보는 그대로.
나오는 것: tables/마/*_v2, t_v1_v2_diff, t2_missing_v2, checks_v2.json, work/ga3/judge4_v2_<prior>.npz, judge4_plan4_v2_<prior>_ga3.csv.gz. 사용: GT_STAGE=ga3 g20_score_add2.py"""
from common import *
import pandas as pd
import judge_lib as JL
import g8_score as G8
from target_check import J4, T4
from g15_score_add1 import judge4, merge3, Plan, build_plans, CAND1, name1, OUTR
A2 = json.loads((C/'judgeeval_v1_add2.json').read_text()); assert sha(C/'judgeeval_v1_add2.json') == json.loads((C/'judgeeval_v1_add2.lock.json').read_text())['config_sha256'], 'add2 config changed after lock'
TD = D/'tables/마'; TN4 = J4
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
REMAP = lambda n: n.startswith('판') or n.startswith('상한') or n == '늘 영상'
def remap(p, col, HH):
    """v2 h 열: 판정 영상 -> 'cur', 두 자료 -> 'curmix' (NaN 이면 v1 그대로). 돌려줌: 새 열, 영상 값 없음, 두 자료 값 없음."""
    h = p.hcol.copy(); N = len(h); mi = np.zeros(N, bool); mt = np.zeros(N, bool)
    if not REMAP(p.name): return h, mi, mt
    cf = np.isfinite(HH[:, col['cur']]); mf = np.isfinite(HH[:, col['curmix']]); img = p.j4 == 1; two = p.j4 == 0
    h[img & cf] = col['cur']; h[two & mf] = col['curmix']; return h, img & ~cf, two & ~mf
def main():
    c = cfg(); T = Timer(); rows_m = []; rows_tr = []; rows_up = []; rows_cur = []; rows5 = []; rows_chk = []; rec = dict(at=now(), scientific_verdict=None, add2_config_sha256=sha(C/'judgeeval_v1_add2.json')); rows_diff = []; rows_miss = []; old = pd.read_csv(D/'tables/나/t74_confusion.csv')
    for prior in PRIORS:
        d = G8.Data(prior, c); Hz = loadz(O/'work'/STAGE/f'heights_{prior}.npz'); assert np.array_equal(Hz['patch_index'], d.idx); Hn = [str(x) for x in Hz['names']]; OK = Hz['ok']; HH = Hz['H']; TT = Hz['TAU']
        Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz', ['n_b0']); tm = np.array([T4.get(int(x), -1) for x in d.t]); N = len(d.t); rr = np.arange(N)
        plans = build_plans(d, Hn); per = {}; per1 = {}; col = {n: i for i, n in enumerate(Hn)}; F1 = loadz(O/'work'/STAGE/f'judge4_{prior}.npz'); assert np.array_equal(F1['patch_index'], d.idx)
        MISS = {}
        for p in plans:
            if f'J4_{p.name}' in F1: assert np.array_equal(F1[f'J4_{p.name}'], p.j4), ('judgment changed', p.name)
            per1[p.name] = (OK[rr, p.hcol], HH[rr, p.hcol], TT[rr, p.hcol]); p.hcol1 = p.hcol; p.hcol, mi, mt = remap(p, col, HH); MISS[p.name] = (mi, mt)
            if f'ok_{p.name}' in F1: assert np.array_equal(F1[f'ok_{p.name}'], per1[p.name][0]), ('v1 ok replay differs', p.name)
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
        # 점검: 사전 정보로 판정한 패치의 목표 맞음은 v1 과 같다
        for p in plans:
            pr = np.isin(p.j4, [2, 3]) if p.split else (merge3(p.j4) == 2)
            assert np.array_equal(per[p.name][0][pr], per1[p.name][0][pr]), ('prior cells changed', p.name)
        rec.setdefault('prior_cells_same', {})[prior] = True
        # 값 없음 표
        for p in plans:
            if not REMAP(p.name): continue
            mi, mt = MISS[p.name]
            for sn, sm in G8.surfaces(d):
                for (vn, vm), (un, w) in G8.UV(d):
                    if un != '넓이': continue
                    m = sm & vm & (tm >= 0); r = dict(plan=p.name, prior=PN[prior], surface=sn, version=vn, scored_area_m2=d.area[m].sum())
                    r['두 자료 판정 넓이'] = d.area[m & (p.j4 == 0)].sum(); r['두 자료: curmix 없음 넓이'] = d.area[m & mt].sum(); r['두 자료: curmix 없음 패치'] = int((m & mt).sum())
                    r['영상 판정 넓이'] = d.area[m & (p.j4 == 1)].sum(); r['영상: cur 없음 넓이'] = d.area[m & mi].sum(); r['영상: cur 없음 패치'] = int((m & mi).sum())
                    if p.st is not None:
                        for k, stn in [(1, '①'), (2, '②'), (3, '③')]: r[f'영상: cur 없음, 단계 {stn}'] = d.area[m & mi & (p.st == k)].sum()
                    r['채점 밖까지: 값 없음 패치'] = int((sm & vm & (mi | mt)).sum()); rows_miss.append(r)
        # v1 -> v2 차이
        for p in plans:
            ok2 = per[p.name][0]; ok1 = per1[p.name][0]; ch = p.hcol != p.hcol1
            for sn, sm in G8.surfaces(d):
                for (vn, vm), (un, w) in G8.UV(d):
                    m = sm & vm
                    for k, cn in list(enumerate(TN4)) + [(None, '전체(채점한 넓이)')]:
                        mm = m & ((tm == k) if k is not None else (tm >= 0)); tot = w[mm].sum()
                        if not tot: continue
                        a1 = 100*w[mm & ok1].sum()/tot; a2 = 100*w[mm & ok2].sum()/tot
                        rows_diff.append(dict(plan=p.name, prior=PN[prior], surface=sn, version=vn, unit=un, case=cn, case_total=tot, target_acc_v1=a1, target_acc_v2=a2, diff_pp=a2 - a1, h_changed_patches=int((mm & ch).sum()), h_changed_w=w[mm & ch].sum(),
                                              ok_false_to_true_w=w[mm & ~ok1 & ok2].sum(), ok_true_to_false_w=w[mm & ok1 & ~ok2].sum(), ok_flip_patches=int((mm & (ok1 != ok2)).sum())))
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
        savez(O/'work'/STAGE/f'judge4_v2_{prior}.npz', **sv)
        fwd = pd.read_csv(O/f'forward_{prior}_ga3.csv.gz', usecols=['patch_index', 'patch_id', 'building', 'surface', 'place', 'area_m2', 'answer']); fwd = fwd.set_index('patch_index').loc[d.idx].reset_index()
        ok, hT, tT, so = per['판 4']; p = J['판 4']; stn = {1: '①', 2: '②', 3: '③'}
        fwd['judge4'] = [J4[x] if x >= 0 else '그 밖' for x in p.j4]; fwd['judge_stage'] = [stn[x] + ('(기본)' if f else '') for x, f in zip(p.st, p.df)]; fwd['h_T'] = hT; fwd['tau_T'] = tT; fwd['target_ok'] = ok; fwd['src_ok'] = so
        fwd.to_csv(O/f'judge4_plan4_v2_{prior}_ga3.csv.gz', index=False)
        rec[prior] = dict(patches=N, plan4_target_acc_area=float(100*d.area[(tm >= 0) & per['판 4'][0]].sum()/d.area[tm >= 0].sum()), plan4_judgment4_area=float(100*d.area[(tm >= 0) & (p.j4 == tm)].sum()/d.area[tm >= 0].sum()))
    chk = pd.DataFrame(rows_chk); write('t1_check_merge3_v2', chk, '판정 넷을 셋으로 합친 행렬 = 묶음 나 t74_confusion 점검(다른 칸 수)'); rec['merge3_cells_different'] = int(chk.cells_different.sum())
    if rec['merge3_cells_different']: issue(f'셋으로 합친 행렬이 t74_confusion 과 다름: {chk[chk.cells_different > 0].head().to_dict("records")}'); dump(TD/'checks_v2.json', rec); raise SystemExit('merge3 differs: stop')
    write('t_v1_v2_diff', pd.DataFrame(rows_diff), '판·면·경우마다 목표 정확도 묶음 다(v1) -> v2, 차이 %p, h 를 바꾼 패치 수·넓이(점), 목표 맞음이 바뀐 넓이(점)')
    write('t2_missing_v2', pd.DataFrame(rows_miss), 'mvs_mean_m(cur) 또는 섞음(curmix)이 없어 묶음 다 h_T 를 그대로 쓴 넓이·패치(채점 안, 넓이). 늘 영상은 영상 판정 = 모든 패치')
    mx = pd.DataFrame(rows_m); write('t1_matrix4_v2', mx, '4 x 4 오류 행렬(긴 꼴): 줄 = 정답 넷 + 채점 밖 셋, 칸 = 판정 넷 + 그 밖. 칸마다 넓이(또는 점), 줄 안 %, 목표 맞음 줄 안 %(줄마다 더하면 그 경우 목표 정확도), 칸 안 목표 맞음 %. 늘 사전 정보는 사전 정보를 나누지 않은 3열')
    tr = pd.DataFrame(rows_tr); write('t3_trace_v2', tr, '경우별 추적 표(긴 꼴). 판단 = 판정 넷 대각선, 판단(셋) = 앞 묶음 판정 정확도 정의, 목표 = 목표 높이가 참값 τ_T 안, 고른 자료 = 앞 묶음 목표 정확도. 학습 뒤는 비움(target_check.py 로 채움)')
    write('t3_upper_v2', pd.DataFrame(rows_up), '바꿔 끼운 상한 보조표(판정 넷 판단·목표 정확도)'); write('t3_threshold_curve_v2', pd.DataFrame(rows_cur), '문턱 곡선: 정답과 τ_T 모두 같은 τ, 판정 넷 판단 정확도와 목표 정확도')
    write('t5_image_error_v2', pd.DataFrame(rows5), '5절: 정답 사전 정보·영상 틀림인데 판 4 가 두 자료. |h_I| = 정답의 영상 자리 크기, d = ① 본 판 평균(지붕 10 / 벽 5 m), L = 저장 한계')
    for (r_, s_) in [(mx, 'm'), (tr, 't')]: assert (pd.to_numeric(r_.filter(like='%').stack(), errors='coerce').dropna() <= 100 + 1e-9).all() if s_ == 'm' else True
    trn = tr[tr.accuracy.isin(['판단', '목표', '판단(셋, 앞 묶음 정의)', '고른 자료'])][['①만 (판 1)', '② 더함 (판 2)', '③ 더함 (판 4)']].to_numpy(float); assert np.nanmax(trn) <= 100 + 1e-9, 'over 100 %'
    # 행렬과 추적 표 맞댐
    for _, r in tr[(tr.accuracy == '목표') & ~tr.case.str.startswith('전체') & ~tr.case.str.startswith('채점')].iterrows():
        g = mx[(mx.plan == '판 4') & (mx.prior == r.prior) & (mx.surface == r.surface) & (mx.version == r.version) & (mx.unit == r.unit) & (mx.truth == r.case)].iloc[0]
        s = sum(g[f'{cn} 목표 맞음 줄 %'] for cn in TN4 + ['그 밖'] if np.isfinite(g[f'{cn} 목표 맞음 줄 %'])); assert np.isclose(s, r['③ 더함 (판 4)'], atol=1e-6), (r.case, s, r['③ 더함 (판 4)'])
    rec['matrix_trace_consistent'] = True; rec['seconds'] = T.s(); dump(TD/'checks_v2.json', rec); progress(f'덧붙임 2 v2 채점: {rec}'); print(json.dumps(jsafe(rec), ensure_ascii=False))
if __name__ == '__main__': main()
