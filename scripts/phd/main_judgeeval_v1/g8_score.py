"""6·7절 채점(참값은 여기서만 읽음). 판단(judge_lib)은 참값 없이 재료(step1·2·3)로만 정한다.
정답 차례: 0 두 자료, 1 영상, 2 사전 정보(영상 틀림), 3 사전 정보(영상 없음), 4 둘 다 틀림, 5 정답 없음, -1 사전 정보 높이 없음.
판정 정확도: 정답 0~3 넓이 중 판정이 같은(0↔두 자료, 1↔영상, 2·3↔사전 정보) 넓이 비율. 목표 정확도: 정답 0~4 넓이 중 판정이 고른 자료가 맞은 넓이
(두 자료: 정답 0, 영상: 정답 0·1, 사전 정보: 정답 0·2·3). 모든 표 두 판(전체, 층 둘 뺌), 넓이와 점(기둥 안 참값 점 수). 사용: GT_STAGE=ga3 g8_score.py"""
from common import *
import pandas as pd
import judge_lib as JL
TD = D/'tables/나'; TN = FWD + [FWD_X]
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def jcorrect(t, j): return ((t == 0) & (j == 0)) | ((t == 1) & (j == 1)) | (np.isin(t, [2, 3]) & (j == 2))
def tcorrect(t, j): return ((j == 0) & (t == 0)) | ((j == 1) & np.isin(t, [0, 1])) | ((j == 2) & np.isin(t, [0, 2, 3]))
def acc(t, j, w):
    dj = np.isin(t, [0, 1, 2, 3]); dt = np.isin(t, [0, 1, 2, 3, 4]); okj = jcorrect(t, j) & dj; okt = tcorrect(t, j) & dt
    return 100*w[okj].sum()/max(w[dj].sum(), 1e-12), 100*w[okt].sum()/max(w[dt].sum(), 1e-12)
class Data:
    def __init__(s, prior, c):
        s.prior = prior; Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz'); s.idx = Z['patch_index']; s.t = Z['answer'][:, 0].astype(int); s.tc = Z['answer'].astype(int); s.two = Z['two_layer'].astype(bool)
        s.pts = np.nan_to_num(Z['n_total']); P = loadz(inp('patches', prior=prior), ['kind', 'area', 'place', 'building', 'centre', 'region'])
        s.kind = P['kind'][s.idx]; s.area = P['area'][s.idx]; s.place = P['place'][s.idx]; s.building = P['building'][s.idx]; s.centre = P['centre'][s.idx]; s.region = P['region'][s.idx]
        s.S1 = loadz(O/'work'/STAGE/f'step1_{prior}.npz'); s.C2 = loadz(O/'work'/STAGE/f'step2_{prior}.npz')['counts']; s.S3 = loadz(O/'work'/STAGE/f'step3_{prior}.npz')
        assert np.array_equal(s.S1['patch_index'], s.idx) and np.array_equal(s.S3['patch_index'], s.idx)
        tab = pd.read_csv(inp('patch_table', prior=prior), usecols=['combo_D_judgment']).combo_D_judgment.values[s.idx]
        mp = {'일치': 0, '영상 깊이 사용': 1, '사전정보 사용': 2, '결측': 2}; s.ref = {'JUDGECHECK-v2 본 방법': np.array([{0: 0, 1: 2, 2: 1, 4: 2}.get(int(x), 3) for x in s.S1['jc2']]),
            '11/22 구조': np.array([mp.get(x, 3) for x in tab]), '늘 사전 정보': np.full(len(s.t), 2), '늘 영상': np.full(len(s.t), 1)}   # 3 = 그 밖(제거·미판정)
        s.thr = {k: v for k, v in c['judgment']['step1_m3c2']['size_boundary_m'].items() if k != 'kind'}
    def r1(s, **kw): return JL.step1(s.S1, s.prior, s.kind, size_thr=s.thr, **kw)
    def r2(s, rule='pixel', delta=1): return JL.step2(s.C2, rule, delta)
    def r3(s, rule='main'):
        S = s.S3; a = JL.step3(S['from1_cons'], S['from1_total'], rule, S['from1_a2']); b = JL.step3(S['from2_cons'], S['from2_total'], rule, S['from2_a2']); return a, b
    def plan(s, k, r1=None, r2=None, r3=None):
        r1 = s.r1() if r1 is None else r1; r2 = s.r2() if r2 is None else r2; a, b = s.r3() if r3 is None else r3
        return JL.assemble(r1, r2, a, b, use2=k in (2, 4), use3=k in (3, 4))
def surfaces(d):
    out = [('지붕', d.kind == 1)]
    if (d.kind == 2).any(): out += [('벽', d.kind == 2), ('모두', np.ones(len(d.kind), bool))]
    return out
def versions(d): return [('전체', np.ones(len(d.t), bool)), ('층 둘 뺌', ~d.two)]
def confusion(d, j, label, rows, jn=JL.JN + ['그 밖']):
    for sn, sm in surfaces(d):
        for vn, vm in versions(d):
            m = sm & vm
            for unit, w in [('넓이', d.area), ('점', d.pts)]:
                for ti, tn in enumerate(TN[:-1] + [FWD_X]):
                    tv = ti if ti < 6 else -1; mm = m & (d.t == tv); tot = w[mm].sum(); r = dict(plan=label, prior=PN[d.prior], surface=sn, version=vn, unit=unit, truth=tn, total=tot)
                    for k, jname in enumerate(jn):
                        x = w[mm & (j == k)].sum(); r[jname] = x; r[f'{jname} %'] = 100*x/tot if (tot and ti < 4) else np.nan
                    rows.append(r)
def main():
    c = cfg(); T = Timer(); rec = dict(at=now(), stage=STAGE, scientific_verdict=None); DD = {p: Data(p, c) for p in PRIORS}
    cand1 = [dict(h=h, rep=rp, size=sz, Lver=lv, two_pass=tp) for tp, hs in [(False, [0, 1, 2]), (True, [2])] for h in hs for rp in ['mean', 'median'] for sz in [False, True] for lv in ['pm', 'orig']]
    cand2 = [dict(rule=r, delta=dl) for r in ['pixel', 'centre', 'one', 'two'] for dl in [1, 5]]; cand3 = ['main', 'major', 'a2']
    name1 = lambda k: ('두 번 재기' if k['two_pass'] else f"길이 {['짧음', '중간', '긺(본)'][k['h']]}") + f" · {'평균' if k['rep'] == 'mean' else '중앙값'} · 크기 경계 {'넣음' if k['size'] else '뺌'} · 한계 {'PM' if k['Lver'] == 'pm' else '원문'}"
    rows_conf = []; rows_plan = []; rows_s1 = []; rows_s2 = []; rows_s3 = []; rows_eff = []; rows_cur = []; rows_rad = []; rows_s2d = []; best = {}
    for p, d in DD.items():
        # 7.1 ①
        lens = d.S1['Hs']
        for k in cand1:
            r = d.r1(**k); hh = 2 if k['two_pass'] else k['h']; dv = (d.S1['d_mean'] if k['rep'] == 'mean' else d.S1['d_med'])[:, hh]
            for sn, sm in surfaces(d):
                for vn, vm in versions(d):
                    m = sm & vm; w = d.area; row = dict(candidate=name1(k), prior=PN[p], surface=sn, version=vn, area_m2=w[m].sum())
                    for ri, rn in enumerate(['같다', '다르다', '값 없음']):
                        for ti, tn in enumerate(TN[:-1]): row[f'{rn}|{tn}'] = w[m & (r == ri) & (d.t == ti)].sum()
                    same = m & (r == 0); diff = m & (r == 1)
                    row['같다 맞음 %'] = 100*w[same & (d.t == 0)].sum()/max(w[same & np.isin(d.t, [0, 1, 2, 3, 4])].sum(), 1e-12)
                    row['다르다 맞음 %'] = 100*w[diff & np.isin(d.t, [1, 2, 4])].sum()/max(w[diff & np.isin(d.t, [0, 1, 2, 3, 4])].sum(), 1e-12)
                    row['변화 놓침 m²'] = w[same & (d.t == 1)].sum(); row['헛 변화 m²'] = w[diff & (d.t == 0)].sum(); row['값 없음 m²'] = w[m & (r == 2)].sum(); row['값 없음 중 정답 영상 m²'] = w[m & (r == 2) & (d.t == 1)].sum()
                    row['끝에 몰림 %'] = 100*w[m & (r != 2) & (np.abs(dv) > .9*lens[:, hh])].sum()/max(w[m & (r != 2)].sum(), 1e-12)
                    row['원문 한계: 정답 두 자료 중 다르다 %'] = 100*w[m & (d.t == 0) & (r == 1)].sum()/max(w[m & (d.t == 0)].sum(), 1e-12) if k['Lver'] == 'orig' else np.nan
                    rows_s1.append(row)
        for (rg, kd), g in pd.DataFrame(dict(rg=d.region, kd=d.kind, n=d.S1['n'][:, 2])).groupby(['rg', 'kd']):
            rows_rad.append(dict(prior=PN[p], region=rg, surface=KN[kd], patches=len(g), cylinder_points_median=float(g.n.median()), rule_median_ge20=bool(g.n.median() >= 20)))
        # 7.2 ②
        r1m = d.r1(); none = r1m == 2
        for k in cand2:
            r2 = d.r2(**k)
            for sn, sm in surfaces(d):
                for vn, vm in versions(d):
                    m = sm & vm & none; w = d.area; row = dict(rule={'pixel': '화소 표 안정도', 'centre': '중심 한 점 안정도', 'one': '한 장 이상', 'two': '두 장 이상'}[k['rule']], delta=f"{k['delta']} %", prior=PN[p], surface=sn, version=vn, area_m2=w[m].sum())
                    for ri, rn in enumerate(['사전 정보', '③으로']):
                        for ti, tn in enumerate(TN[:-1]): row[f'{rn}|{tn}'] = w[m & (r2 == ri) & (d.t == ti)].sum()
                    row['정답 영상없음 → 사전 정보 %'] = 100*w[m & (d.t == 3) & (r2 == 0)].sum()/max(w[m & (d.t == 3)].sum(), 1e-12); row['정답 영상 → ③으로 %'] = 100*w[m & (d.t == 1) & (r2 == 1)].sum()/max(w[m & (d.t == 1)].sum(), 1e-12)
                    rows_s2.append(row)
        C = d.C2; tot1 = C[:, 0:4].sum(1)
        for ti, tn in enumerate(TN[:-1]):
            for sn, sm in surfaces(d):
                m = none & sm & (d.t == ti); w = d.area
                if not m.any(): continue
                rows_s2d.append(dict(prior=PN[p], surface=sn, truth=tn, area_m2=w[m].sum(), **{f'{nm} 화소 비율 %': 100*np.nansum(C[m, j])/max(np.nansum(tot1[m]), 1) for j, nm in enumerate(['못 봄', '지나감', '막힘', '일치'])},
                                     **{'표 없음(모두 못 봄) 넓이 %': 100*w[m & (np.nan_to_num(C[:, 1:4]).sum(1) == 0)].sum()/w[m].sum()}))
        # 7.3 ③
        r2m = d.r2(); go3_1 = r1m == 1; go3_2 = (r1m == 2) & (r2m == 1)
        for rule in cand3:
            a, b = d.r3(rule)
            for src, gm, res in [('①에서', go3_1, a), ('②에서', go3_2, b), ('모두', go3_1 | go3_2, np.where(go3_1, a, b))]:
                for sn, sm in surfaces(d):
                    for vn, vm in versions(d):
                        m = sm & vm & gm; w = d.area; row = dict(rule={'main': '본 판(COLMAP 화소 5)', 'major': '다수결', 'a2': '지금 판(A2 영상 5장)'}[rule], source=src, prior=PN[p], surface=sn, version=vn, area_m2=w[m].sum())
                        for ri, rn in enumerate(['사전 정보', '영상']):
                            for ti, tn in enumerate(TN[:-1]): row[f'{rn}|{tn}'] = w[m & (res == ri) & (d.t == ti)].sum()
                        row['정답 영상 → 영상 %'] = 100*w[m & (d.t == 1) & (res == 1)].sum()/max(w[m & (d.t == 1)].sum(), 1e-12); row['정답 영상틀림 → 사전 정보 %'] = 100*w[m & (d.t == 2) & (res == 0)].sum()/max(w[m & (d.t == 2)].sum(), 1e-12)
                        row['진짜 변화 되돌림 m²'] = w[m & (d.t == 1) & (res == 0)].sum(); rows_s3.append(row)
        # 7.4 판 1~4, 참고, 바꿔 끼운 상한, 가장 나은 후보
        J = {f'판 {k}': d.plan(k) for k in [1, 2, 3, 4]}
        o1 = r1m.copy(); o1[d.t == 0] = 0; o1[np.isin(d.t, [1, 2, 4])] = 1; o1[d.t == 3] = 2
        o2 = r2m.copy(); o2[none & (d.t == 1)] = 1; o2[none & np.isin(d.t, [0, 2, 3, 4])] = 0
        a, b = d.r3(); oa = a.copy(); ob = b.copy(); img_ok = np.isin(d.t, [0, 1]); bad = np.isin(d.t, [2, 3]); oa[img_ok] = 1; oa[bad] = 0; ob[img_ok] = 1; ob[bad] = 0
        J['상한: ①만 정답'] = d.plan(4, r1=o1); J['상한: ②만 정답'] = d.plan(4, r2=o2); J['상한: ③만 정답'] = d.plan(4, r3=(oa, ob))
        def score4(**kw): jj = d.plan(4, **kw); return acc(d.t, jj, d.area)[0]
        b1 = max(cand1, key=lambda k: score4(r1=d.r1(**k))); b2 = max(cand2, key=lambda k: score4(r2=d.r2(**k))); b3 = max(cand3, key=lambda r: score4(r3=d.r3(r)))
        best[p] = dict(step1=name1(b1), step2=b2, step3=b3); J['판 4(가장 나은 후보)'] = d.plan(4, r1=d.r1(**b1), r2=d.r2(**b2), r3=d.r3(b3))
        J.update(d.ref)
        for nm, j in J.items():
            confusion(d, j, nm, rows_conf)
            for sn, sm in surfaces(d):
                for vn, vm in versions(d):
                    m = sm & vm; ja, ta = acc(d.t[m], j[m], d.area[m]); jp, tp = acc(d.t[m], j[m], d.pts[m])
                    rows_plan.append(dict(plan=nm, prior=PN[p], surface=sn, version=vn, judgment_acc_area=ja, target_acc_area=ta, judgment_acc_points=jp, target_acc_points=tp,
                                          judged_m2=d.area[m & np.isin(j, [0, 1, 2])].sum(), other_m2=d.area[m & (j == 3)].sum(), area_m2=d.area[m].sum()))
        for a_, b_ in [('판 1', '판 2'), ('판 1', '판 3'), ('판 3', '판 4'), ('판 2', '판 4')]:
            ch = J[a_] != J[b_]; ca = jcorrect(d.t, J[a_]); cb = jcorrect(d.t, J[b_])
            for sn, sm in surfaces(d):
                for ti, tn in enumerate(TN[:-1]):
                    m = sm & ch & (d.t == ti); w = d.area
                    rows_eff.append(dict(change=f'{a_} → {b_}', prior=PN[p], surface=sn, truth=tn, changed_m2=w[m].sum(), 맞게_바뀜=w[m & ~ca & cb].sum(), 틀리게_바뀜=w[m & ca & ~cb].sum(), 틀림_틀림=w[m & ~ca & ~cb].sum(), 맞음_맞음=w[m & ca & cb].sum()))
        for k_, x in enumerate(c['truth']['threshold_curve_m']):
            tt = d.tc[:, 1+k_]
            for nm in ['판 1', '판 4', 'JUDGECHECK-v2 본 방법', '11/22 구조']:
                for sn, sm in surfaces(d):
                    ja, ta = acc(tt[sm], J[nm][sm], d.area[sm]); rows_cur.append(dict(tau_m=x, plan=nm, prior=PN[p], surface=sn, judgment_acc=ja, target_acc=ta))
        savez(O/'work'/STAGE/f'judgments_{p}.npz', patch_index=d.idx, r1=r1m, r2=r2m, r3a=a, r3b=b, **{f'J_{k}': v for k, v in J.items() if k.startswith('판')})
        rec[p] = dict(best=best[p], area=float(d.area.sum()), plan4_sum_equal=bool(np.isclose(sum(d.area[J['판 4'] == q].sum() for q in [0, 1, 2]), d.area.sum())),
                      plan4_without_23_equals_plan1=bool(np.array_equal(JL.assemble(r1m, r2m, a, b, False, False), J['판 1'])))
    write('t71_step1', pd.DataFrame(rows_s1), '① M3C2 후보마다 결과(같다/다르다/값 없음) × 정답 넓이, 맞음 비율, 변화 놓침·헛 변화, 값 없음과 그 가운데 정답 영상, 끝에 몰림(|d| > 0.9 반길이)')
    write('t71_radius_rule', pd.DataFrame(rows_rad), '원통 반지름 규칙(Lague 7절) 확인: 본 길이 원통 안 영상 점 수의 중앙값(지역·자료·면)')
    write('t72_step2', pd.DataFrame(rows_s2), '② 결과(사전 정보 / ③으로) × 정답 넓이, ①(본 판)에서 값 없는 패치')
    write('t72_counts', pd.DataFrame(rows_s2d), '② 화소 분류 비율(δ 1 %), ①에서 값 없는 패치, 정답 종류별')
    write('t73_step3', pd.DataFrame(rows_s3), '③ 결과(사전 정보 / 영상) × 정답 넓이, ①·②(본 판)에서 넘어온 패치')
    write('t74_plans', pd.DataFrame(rows_plan), '판 1~4, 바꿔 끼운 상한, 가장 나은 후보 판, 참고 열: 판정 정확도·목표 정확도(넓이, 점)')
    write('t74_confusion', pd.DataFrame(rows_conf), '혼동 행렬: 정답(줄) × 판정(칸: 두 자료, 영상, 사전 정보, 그 밖) 넓이·점, 비율은 정답 0~3 줄만')
    write('t74_effect', pd.DataFrame(rows_eff), '단계의 효과: 판 사이 판정이 바뀐 넓이를 정답 종류별로 맞게 바뀜·틀리게 바뀜·틀림→틀림')
    write('t74_threshold_curve', pd.DataFrame(rows_cur), '문턱 곡선: 세 자료 같은 τ 정답으로 다시 센 판정·목표 정확도')
    rec['best_rule'] = '단계마다 그 단계 후보만 바꾼 판 4의 판정 정확도(넓이, 전체)가 가장 높은 후보'; dump(TD/'checks.json', rec); progress(f'채점 나: {T.s():.0f} s'); print(json.dumps(jsafe(rec), ensure_ascii=False)[:2000])
if __name__ == '__main__': main()
