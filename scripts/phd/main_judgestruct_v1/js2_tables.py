"""js1 결과로 표 t11·t12·t13·t14 와 그림 12·14. 사용: js2_tables.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
FONT = '/fonts/NotoSansCJK-Regular.ttc'; font_manager.fontManager.addfont(FONT); plt.rcParams.update({'font.family': font_manager.FontProperties(fname=FONT).get_name(), 'axes.unicode_minus': False, 'font.size': 8})
FIG = D/'figures'; FIG.mkdir(parents=True, exist_ok=True)
NO_BEST = ['패치 다수결 상한', '기존 4 결합(세 실험 지역)']
STORED = ['사전 정보 단독', '영상 단독', '패치 다수결 상한', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '기존 4 결합(전 건물)', '기존 5 T=0.5 m', '기존 5 T=L']
ORDER = ['본 방법', '사전 정보 단독', '영상 단독', '패치 다수결 상한', '구조 하한', '구조 하한 (나)', '구조 상한', '구조 상한 2', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '기존 4 결합(전 건물)', '기존 5 T=0.5 m', '기존 5 T=L']
GT_ROWS = ['패치 다수결 상한', '구조 상한', '구조 상한 2']
f1 = lambda v: '' if not np.isfinite(v) else f'{v:.1f}'
def save(fig, name, meta):
    fig.savefig(FIG/f'{name}.png', dpi=300, facecolor='white', bbox_inches='tight'); plt.close(fig); dump(FIG/f'{name}.json', dict(meta, at=now(), scientific_verdict=None))


def main():
    cf = cfg(); T = Timer(); CHK = []
    SA = pd.read_csv(JABL_DOC/'tables/s_all_variants.csv'); SA = SA[SA.scope == '전체']
    PU = pd.read_csv(JABL_DOC/'tables/addendum2/p_patch_unit.csv'); BD = pd.read_csv(JABL_DOC/'tables/s_building_diff.csv')
    SM = pd.read_csv(JABL_DOC/'tables/s_main_summary.csv')
    J1 = {p: json.loads((O/p/'js1.json').read_text()) for p in ['LoD2', 'ALS']}
    # ======== 셈 1-1
    IS = pd.concat([pd.read_csv(O/p/'t11_initial_state.csv') for p in ['LoD2', 'ALS']], ignore_index=True)
    for _, r in IS.iterrows(): CHK.append(dict(check='처음 상태 패치 수 합 = 패치 수 (네 경우 + 네 경우 밖 + 동률 + 3개 미만 + 참값 없음)', prior=r.prior, surface=r.surface, set=r.set, split=f'{r.split}:{r.split_value}', ok=bool(r.check_sum)))
    SN = [STATE[s] for s in STATE_ORDER]
    def is_md(q):
        out = q[['prior', 'surface', 'set', 'split', 'split_value', 'patches', 'area_m2']].copy()
        out['넓이 % (유효/사전 오류/영상 오류/결측/네 경우 밖)'] = [' / '.join(f1(r[f'area_pct_{s}']) for s in SN) for _, r in q.iterrows()]
        out['참값 점 % (같은 차례)'] = [' / '.join(f1(r[f'pt_pct_{c}']) for c in CN + ['네 경우 밖']) for _, r in q.iterrows()]
        out['동률·3개 미만·참값 없음 패치'] = [f"{int(r['n_동률'])} · {int(r['n_참값 점 3개 미만'])} · {int(r['n_참값 없음'])}" for _, r in q.iterrows()]
        return out
    IS['prior'] = IS['prior'].map(PN)
    write('t11_initial_state', IS, note='셈 1-1. 차이가 유의한 패치(영상 깊이 점 4개 이상, 본값 L 밖)와 한계가 없는 패치(점 4개 이상, L 없음)의 처음 상태. 넓이 % = 처음 상태가 있는 넓이(네 경우 + 네 경우 밖) 가운데; 참값 점 % = 그 패치들의 참값 점(짝 있음)을 점 자신의 경우로 셈. 처음 상태 = 덧붙임 2 패치 다수결.', md=is_md)
    BB = pd.concat([pd.read_csv(O/p/'t11_by_building_rows.csv') for p in ['LoD2', 'ALS']], ignore_index=True); BB['prior'] = BB['prior'].map(PN)
    BB.to_csv(D/'tables/t11_by_building_rows.csv', index=False)
    QB = []
    for (p, s), q in BB.groupby(['prior', 'surface'], sort=False):
        q = q[q.sig_area_m2 >= 5]; r = dict(prior=p, surface=s, buildings=len(q))
        for st in SN:
            v = q[f'area_pct_{st}'].dropna(); r[f'{st} 10·50·90 %'] = ' · '.join(f1(np.quantile(v, x)) for x in [.1, .5, .9]) if len(v) else ''
        QB.append(r)
    write('t11_by_building', pd.DataFrame(QB), note='셈 1-1 건물마다. 차이가 유의한 넓이가 5 m² 이상인 건물만; 건물마다 처음 상태 넓이 비율(분모 = 처음 상태가 있는 넓이)의 건물 사이 10·50·90 % 값(건물마다 같은 무게). 건물마다 값은 t11_by_building_rows.csv.')
    RE = pd.concat([pd.read_csv(O/p/'t11_reach.csv') for p in ['LoD2', 'ALS']], ignore_index=True); RE['prior'] = RE['prior'].map(PN)
    write('t11_reach', RE, note='셈 1-1 닿는 범위. 경우마다 참값 점(짝 있음)이 든 패치의 갈래 비율 %: 차이가 유의한 패치 / 한계 안(일치) / 한계가 없는 패치 / 영상 깊이 점 4개 미만 / 그 밖(사전 정보 높이나 법선이 없음, 또는 점 4개 이상인데 MVS 높이가 없고 한계 안팎이 아님). 새 구조의 4단계(영상 오류 찾기)는 차이가 유의한 패치에만 닿는다.')
    JPK = pd.concat([pd.read_csv(O/p/'t11_jp_check.csv') for p in ['LoD2', 'ALS']], ignore_index=True); JPK['prior'] = JPK['prior'].map(PN)
    write('t11_jp_check', JPK, note='검산 참고: JUDGEPROBE-v1 정의(한계 밖, JP 패치 경우, 섞인 패치 = 다수 비율 < 0.8 뺌)로 센 사전정보 오류 : 영상 깊이 오류 패치 수, 그리고 이 셈의 정의(덧붙임 2 처음 상태, 섞인 패치 넣음)의 패치 수·넓이 비.')
    # ======== 셈 1-2·1-3
    RW = pd.concat([pd.read_csv(O/p/'rows.csv') for p in ['LoD2', 'ALS']], ignore_index=True)
    rows = []
    for _, r in RW.iterrows(): rows.append(r.to_dict())
    for prior in ['LoD2', 'ALS']:
        for sn, _ in SURF[prior]:
            for v in STORED:
                s = SA[(SA.prior == prior) & (SA.surface == sn) & (SA.variant == v)]; pu = PU[(PU.prior == prior) & (PU.surface == sn) & (PU.variant == v)]
                if not len(s): continue
                s = s.iloc[0]; r = dict(prior=prior, surface=sn, variant=v, stored=True)
                for c in CN:
                    r[f'n_{c}'] = s[f'n_{c}']; r[f'ok_{c}'] = s[f'ok_{c}']; r[f'name_{c}'] = s[f'name_{c}']
                    r[f'patch_ok_{c}'] = pu.iloc[0][f'patch_ok_{c}'] if len(pu) else np.nan; r[f'patch_name_{c}'] = pu.iloc[0][f'patch_name_{c}'] if len(pu) else np.nan
                r['ok_전체'] = s['ok_전체']; r['patch_ok_전체'] = pu.iloc[0]['patch_ok_전체'] if len(pu) else np.nan
                b = BD[(BD.prior == prior) & (BD.surface == sn) & (BD.variant == v)]; r['building_diff_median_pp'] = float(b.iloc[0].diff_median_pp) if len(b) else np.nan
                r['changed_area_m2'] = s.get('changed_area_m2', np.nan); rows.append(r)
    B = pd.DataFrame(rows); B['stored'] = B['stored'].fillna(False).astype(bool)
    # 검산 1: 본 방법 = JUDGEABL
    for prior in ['LoD2', 'ALS']:
        for sn, _ in SURF[prior]:
            mine = B[(B.prior == prior) & (B.surface == sn) & (B.variant == '본 방법')].iloc[0]; s = SA[(SA.prior == prior) & (SA.surface == sn) & (SA.variant == '본 방법')].iloc[0]
            pu = PU[(PU.prior == prior) & (PU.surface == sn) & (PU.variant == '본 방법')].iloc[0]
            for c in CN + ['전체']:
                CHK.append(dict(check='본 방법 점 단위 = JUDGEABL s_all_variants', prior=prior, surface=sn, case=c, mine=mine[f'ok_{c}'], theirs=s[f'ok_{c}'], ok=bool(abs(mine[f'ok_{c}'] - s[f'ok_{c}']) < 1e-9)))
                CHK.append(dict(check='본 방법 패치 단위 = JUDGEABL p_patch_unit', prior=prior, surface=sn, case=c, mine=mine[f'patch_ok_{c}'], theirs=pu[f'patch_ok_{c}'], ok=bool(abs(mine[f'patch_ok_{c}'] - pu[f'patch_ok_{c}']) < 1e-9)))
            for c in CN: CHK.append(dict(check='본 방법 판정 이름 맞음 = JUDGEABL', prior=prior, surface=sn, case=c, mine=mine[f'name_{c}'], theirs=s[f'name_{c}'], ok=bool(abs(mine[f'name_{c}'] - s[f'name_{c}']) < 1e-9)))
        sf = '모두' if prior == 'LoD2' else '지붕'; mine = B[(B.prior == prior) & (B.surface == sf) & (B.variant == '본 방법')].iloc[0]; sm = SM[(SM.prior == prior) & (SM.variant == '본 방법')].iloc[0]
        for c in CN + ['전체']: CHK.append(dict(check='본 방법 = JUDGEABL s_main_summary', prior=prior, surface=sf, case=c, mine=mine[f'ok_{c}'], theirs=sm[f'ok_{c}'], ok=bool(abs(round(mine[f'ok_{c}'], 2) - sm[f'ok_{c}']) < .006)))
    # 요약 셋 (점, 패치)
    for pre in ['', 'patch_']:
        oks = [f'{pre}ok_{c}' for c in CN]; B[f'{pre}mean4'] = B[oks].mean(1); B[f'{pre}min4'] = B[oks].min(1); B[f'{pre}min_case'] = [CN[int(np.nanargmin(v))] if np.isfinite(v).any() else '' for v in B[oks].values]
        gaps = []
        for i, r in B.iterrows():
            pool = SA[(SA.prior == r.prior) & (SA.surface == r.surface) & ~SA.variant.isin(NO_BEST) & ~SA.gt_selected.astype(bool) & ~SA.reference.astype(bool) & (SA.family != 'fix') & (SA.family != 'old4')]
            if pre == 'patch_':
                pool = PU[(PU.prior == r.prior) & (PU.surface == r.surface) & PU.variant.isin(pool.variant)]; best = pool[[f'patch_ok_{c}' for c in CN]].max(axis=0).values
            else: best = pool[[f'ok_{c}' for c in CN]].max(axis=0).values
            lo_ = B[(B.prior == r.prior) & (B.surface == r.surface) & B.variant.isin(['구조 하한', '구조 하한 (나)'])][oks].max(axis=0).values
            best = np.fmax(best, lo_); gaps.append(float(np.nanmax(best - r[oks].values.astype(float))))
        B[f'{pre}gap'] = gaps
    base = B[B.variant == '본 방법'].set_index(['prior', 'surface'])
    for pre in ['', 'patch_']:
        for c in CN + ['전체']: B[f'{pre}diff_{c}'] = [r[f'{pre}ok_{c}'] - base.loc[(r.prior, r.surface), f'{pre}ok_{c}'] for _, r in B.iterrows()]
    B['o'] = B.variant.map({v: i for i, v in enumerate(ORDER)}); B = B.sort_values(['prior', 'surface', 'o'], ascending=[False, True, True]).drop(columns='o')
    B['gt_used'] = B.variant.isin(GT_ROWS)
    Bout = B.copy(); Bout['prior'] = Bout['prior'].map(PN)
    def b_md(q):
        o = pd.DataFrame(dict(prior=q.prior, surface=q.surface, variant=[v + (' (참값으로)' if g else '') for v, g in zip(q.variant, q.gt_used)]))
        for c in CN: o[f'{c} 점 · 패치'] = [f"{f1(a)} · {f1(b)}" for a, b in zip(q[f'ok_{c}'], q[f'patch_ok_{c}'])]
        o['전체 점 · 패치'] = [f"{f1(a)} · {f1(b)}" for a, b in zip(q['ok_전체'], q['patch_ok_전체'])]
        o['평균 · 최솟값(경우) · 최대 격차 (점)'] = [f"{f1(a)} · {f1(b)}({c_}) · {f1(g)}" for a, b, c_, g in zip(q.mean4, q.min4, q.min_case, q.gap)]
        o['같은 셋 (패치)'] = [f"{f1(a)} · {f1(b)}({c_}) · {f1(g)}" for a, b, c_, g in zip(q.patch_mean4, q.patch_min4, q.patch_min_case, q.patch_gap)]
        o['판정 이름 맞음 (점, 네 경우)'] = [' / '.join(f1(r[f'name_{c}']) for c in CN) for _, r in q.iterrows()]
        o['본 방법과 차이 %p (점, 네 경우 / 전체)'] = [' / '.join(f1(r[f'diff_{c}']) for c in CN) + f" / {f1(r['diff_전체'])}" for _, r in q.iterrows()]
        o['건물별 차이 중앙값 %p'] = q.building_diff_median_pp.map(f1)
        return o
    write('t12_t13_bounds', Bout, note='셈 1-2·1-3. 목표 맞음 % (점 단위 = JC 2.5 참값 점 비율, 패치 단위 = 덧붙임 2 넓이 가중). 구조 하한 = 차이가 유의한 패치 모두 영상 깊이 사용(한계가 없는 패치는 본값 그대로); (나) = 한계가 없는 패치도 영상 깊이 사용. 구조 상한(참값으로) = 구조 하한에서 영상 오류 패치(처음 상태 영상 깊이 오류)만 사전정보 사용. 구조 상한 2(참값으로) = 차이가 유의한 패치 가운데 영상 깊이 목표 τ 안이 절반 아래이고 사전 정보 목표 τ 안이 절반 이상인 패치를 사전정보 사용. 요약 = 네 경우 평균 · 최솟값(경우) · 최대 격차(참값을 쓰지 않는 판 가운데 가장 높은 값 − 이 판, 기준 모임에 구조 하한 둘 포함). 구조 판이 아닌 줄은 JUDGEABL 저장 값.', md=b_md)
    # 셈 1-2 따로: 식별 1 과 같음
    ID1 = []
    for p in ['LoD2', 'ALS']:
        for e in J1[p]['id1']: ID1.append(dict(e, prior=PN[p]))
    write('t12_lower_vs_id1', pd.DataFrame(ID1), note='셈 1-2: 구조 하한과 JUDGEABL "식별 1 없음·영상 깊이 사용" 의 패치 판정이 같은 비율(패치 수, 넓이). 다른 패치의 까닭은 페이로드 <prior>/id1_diff_*.csv.')
    # ======== 셈 1-4
    GRID = []; BND = []
    Rs, Fs = cf['section_3_4_grid']['R'], cf['section_3_4_grid']['F']
    for p in ['LoD2', 'ALS']:
        for e in json.loads((O/p/'grid_terms.json').read_text())['rows']:
            sn = e['surface']; nT = sum(e[f'n_{c}'] for c in CN); paT = sum(e[f'pa_{c}'] for c in CN)
            bp = {c: 100*e[f'base_{c}']/e[f'n_{c}'] for c in CN}; bp['전체'] = 100*sum(e[f'base_{c}'] for c in CN)/nT; bp['평균'] = np.mean([bp[c] for c in CN])
            bpp = {c: 100*e[f'pbase_{c}']/e[f'pa_{c}'] for c in CN}; bpp['전체'] = 100*sum(e[f'pbase_{c}'] for c in CN)/paT; bpp['평균'] = np.mean([bpp[c] for c in CN])
            def val(R, F, pre=''):
                if pre == '':
                    v = {c: 100*(e[f'lo_{c}'] + R*e[f'dE_{c}'] + F*e[f'dO_{c}'])/e[f'n_{c}'] for c in CN}; v['전체'] = 100*sum(e[f'lo_{c}'] + R*e[f'dE_{c}'] + F*e[f'dO_{c}'] for c in CN)/nT
                else:
                    v = {c: 100*(e[f'plo_{c}'] + R*e[f'pdE_{c}'] + F*e[f'pdO_{c}'])/e[f'pa_{c}'] for c in CN}; v['전체'] = 100*sum(e[f'plo_{c}'] + R*e[f'pdE_{c}'] + F*e[f'pdO_{c}'] for c in CN)/paT
                v['평균'] = np.mean([v[c] for c in CN]); return v
            for F in Fs:
                for R in Rs:
                    v = val(R, F); vp = val(R, F, 'p'); den = R*e['A_E'] + F*e['A_O']; den2 = R*e['A_E'] + F*e['A_O_state']
                    row = dict(prior=PN[p], surface=sn, F=F, R=R, precision_pct=100*R*e['A_E']/den if den else np.nan, precision_state_only_pct=100*R*e['A_E']/den2 if den2 else np.nan)
                    for c in CN + ['전체', '평균']: row[f'ok_{c}'] = v[c]; row[f'diff_{c}'] = v[c] - bp[c]
                    for c in CN + ['전체', '평균']: row[f'patch_ok_{c}'] = vp[c]; row[f'patch_diff_{c}'] = vp[c] - bpp[c]
                    GRID.append(row)
            # 검산 3
            br = B[(B.prior == p) & (B.surface == sn)].set_index('variant')
            for (R, F, vn) in [(0, 0, '구조 하한'), (1, 0, '구조 상한')]:
                v = val(R, F); vp = val(R, F, 'p')
                for c in CN + ['전체']:
                    CHK.append(dict(check=f'격자 R={R}, F={F} = {vn} (점)', prior=p, surface=sn, case=c, mine=v[c], theirs=br.loc[vn, f'ok_{c}'], ok=bool(abs(v[c] - br.loc[vn, f'ok_{c}']) < 1e-9)))
                    CHK.append(dict(check=f'격자 R={R}, F={F} = {vn} (패치)', prior=p, surface=sn, case=c, mine=vp[c], theirs=br.loc[vn, f'patch_ok_{c}'], ok=bool(abs(vp[c] - br.loc[vn, f'patch_ok_{c}']) < 1e-9)))
            # 경계: 값은 R 에 대해 1차 → 정확한 R
            for pre, bb in [('', bp), ('p', bpp)]:
                for F in Fs:
                    v0 = val(0, F, pre); v1 = val(1, F, pre)
                    def solve(c, strict):
                        a, b = v0[c], v1[c] - v0[c]; t = bb[c]
                        if (a > t) if strict else (a >= t): return 0.
                        if b <= 0: return np.nan
                        r_ = (t - a)/b; return r_ if r_ <= 1 + 1e-12 and ((a + b*min(r_, 1) > t - 1e-12) if not strict else True) else np.nan
                    r1 = solve('전체', True); r2 = solve('평균', True); r3a, r3b = solve(CASE[1], False), solve(CASE[2], False); r3 = np.nan if (np.isnan(r3a) or np.isnan(r3b)) else max(r3a, r3b)
                    def gridR(crit):
                        for R in Rs:
                            v = val(R, F, pre)
                            if crit == 1 and v['전체'] > bb['전체']: return R
                            if crit == 2 and v['평균'] > bb['평균']: return R
                            if crit == 3 and v[CASE[1]] >= bb[CASE[1]] and v[CASE[2]] >= bb[CASE[2]]: return R
                        return np.nan
                    prec = lambda R_: 100*R_*e['A_E']/(R_*e['A_E'] + F*e['A_O']) if np.isfinite(R_) and R_*e['A_E'] + F*e['A_O'] > 0 else np.nan
                    BND.append(dict(prior=PN[p], surface=sn, unit='점' if pre == '' else '패치', F=F, prec_at_R_total=prec(r1), prec_at_R_mean4=prec(r2), prec_at_R_both=prec(r3), R_total_exact=r1, R_total_grid=gridR(1), R_mean4_exact=r2, R_mean4_grid=gridR(2), R_both_exact=r3, R_both_grid=gridR(3),
                                    at_R1_total_diff=v1['전체'] - bb['전체'], at_R1_mean4_diff=v1['평균'] - bb['평균'], at_R1_prior_err_diff=v1[CASE[1]] - bb[CASE[1]], at_R1_image_err_diff=v1[CASE[2]] - bb[CASE[2]]))
    G = pd.DataFrame(GRID); BN = pd.DataFrame(BND)
    def g_md(q):
        q = q[q.surface.isin(['모두', '지붕']) & ~((q.prior == 'LoD2') & (q.surface == '지붕'))]
        o = q[['prior', 'surface', 'F', 'R']].copy(); o['정밀도 %'] = q.precision_pct.map(f1)
        o['네 경우 점 (유효/사전 오류/영상 오류/결측)'] = [' / '.join(f1(r[f'ok_{c}']) for c in CN) for _, r in q.iterrows()]
        o['전체 점'] = q['ok_전체'].map(f1); o['평균 점'] = q['ok_평균'].map(f1); o['전체 − 본 방법 %p'] = q['diff_전체'].map(lambda v: f'{v:+.2f}')
        o['평균 − 본 방법 %p'] = q['diff_평균'].map(lambda v: f'{v:+.2f}'); o['전체 패치'] = q['patch_ok_전체'].map(f1); o['평균 패치'] = q['patch_ok_평균'].map(f1)
        return o
    write('t14_grid', G, note='셈 1-4. 가상의 탐지기: 영상 오류 패치의 비율 R, 차이가 유의한 나머지 패치의 비율 F 를 사전정보 사용으로 바꿈, 기댓값(무작위로 뽑지 않음). 정밀도 = 바꾼 넓이 가운데 영상 오류 패치 넓이(나머지 패치에 처음 상태가 없는 패치 포함; 뺀 값은 csv precision_state_only_pct). md 는 LoD2 모두와 항공 LiDAR 지붕만, 지붕·벽은 csv. 실제 탐지기가 놓치는 패치는 무작위가 아니므로 이 값은 탐지기가 갖춰야 할 성능의 어림이다.', md=g_md)
    def bn_md(q):
        o = q[['prior', 'surface', 'unit', 'F']].copy()
        fm = lambda a, b: ('닿지 않음' if not np.isfinite(a) else f'{a:.3f}') + (' (격자 ' + ('—' if not np.isfinite(b) else f'{b:.1f}') + ')')
        pr = lambda v: '' if not np.isfinite(v) else f', 정밀도 {v:.0f} %'
        o['전체 목표 맞음 > 본 방법: R'] = [fm(a, b) + pr(c) for a, b, c in zip(q.R_total_exact, q.R_total_grid, q.prec_at_R_total)]
        o['네 경우 평균 > 본 방법: R'] = [fm(a, b) + pr(c) for a, b, c in zip(q.R_mean4_exact, q.R_mean4_grid, q.prec_at_R_mean4)]
        o['사전 오류·영상 오류 둘 다 ≥ 본 방법: R'] = [fm(a, b) + pr(c) for a, b, c in zip(q.R_both_exact, q.R_both_grid, q.prec_at_R_both)]
        o['R=1 에서 차이 %p (전체 / 평균 / 사전 오류 / 영상 오류)'] = [f'{a:+.2f} / {b:+.2f} / {c:+.2f} / {d_:+.2f}' for a, b, c, d_ in zip(q.at_R1_total_diff, q.at_R1_mean4_diff, q.at_R1_prior_err_diff, q.at_R1_image_err_diff)]
        return o
    write('t14_boundary', BN, note='셈 1-4 경계: F 마다 본 방법보다 높아지는 가장 작은 R (정밀도 = 그 R 에서 바꾼 넓이 가운데 영상 오류 패치 넓이, 분모에 처음 상태 없는 패치 포함). 값이 R 에 대해 1차라 정확한 R 을 풀고, 괄호에 격자(0.1 간격)에서 처음 넘는 R. 기준 셋: 전체 목표 맞음(>), 네 경우 평균(>), 사전정보 오류와 영상 깊이 오류가 둘 다 본 방법 이상(≥). "닿지 않음" = R = 1 에서도 못 넘음.', md=bn_md)
    # ======== 그림 14
    for p, sf in [('LoD2', '모두'), ('ALS', '지붕')]:
        q = G[(G.prior == PN[p]) & (G.surface == sf)]; Z = np.array([[q[(q.F == F) & (q.R == R)]['diff_전체'].iloc[0] for F in Fs] for R in Rs])
        fig, ax = plt.subplots(figsize=(6.4, 4.6)); vm = max(abs(np.nanmin(Z)), abs(np.nanmax(Z)))
        im = ax.imshow(Z, origin='lower', cmap='RdBu', vmin=-vm, vmax=vm, aspect='auto', extent=[-.5, len(Fs) - .5, -.05, 1.05])
        for i in range(len(Rs)):
            for j in range(len(Fs)): ax.text(j, Rs[i], f'{Z[i, j]:+.2f}', ha='center', va='center', fontsize=4.5, color='k')
        bq = BN[(BN.prior == PN[p]) & (BN.surface == sf) & (BN.unit == '점')]
        for col, lab, st in [('R_total_exact', '전체 목표 맞음 > 본 방법', '-'), ('R_mean4_exact', '네 경우 평균 > 본 방법', '--'), ('R_both_exact', '사전 오류·영상 오류 둘 다 ≥ 본 방법', ':')]:
            ax.plot(np.arange(len(Fs)), bq[col].values, st, color='k', lw=1.4, marker='o', ms=2.5, label=lab)
        ax.set_xticks(range(len(Fs))); ax.set_xticklabels([f'{F:g}' for F in Fs]); ax.set_yticks(Rs); ax.set_xlabel('F (차이가 유의한 나머지 패치를 사전정보 사용으로 바꾸는 비율)'); ax.set_ylabel('R (영상 오류 패치를 찾는 비율)')
        plt.colorbar(im, ax=ax, label='전체 목표 맞음 − 본 방법 (%p, 점 단위)'); ax.legend(fontsize=6, loc='upper left', framealpha=.85)
        ax.set_title(f'{PN[p]} {sf}: 영상 오류 탐지기의 재현율 R·거짓 경보 F 와 전체 목표 맞음 (기댓값)', fontsize=8)
        save(fig, f'fig14_boundary_{p}', dict(prior=p, surface=sf, source='tables/t14_grid.csv, t14_boundary.csv', note='선이 없는 F 는 R = 1 에서도 못 넘음'))
    # ======== 그림 12
    for p, sf in [('LoD2', '모두'), ('ALS', '지붕')]:
        q = B[(B.prior == p) & (B.surface == sf)].set_index('variant').loc[[v for v in ORDER if v in set(B[(B.prior == p) & (B.surface == sf)].variant)]]
        fig, axs = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True); cols = plt.get_cmap('tab20')(np.linspace(0, 1, len(q)))
        for ax, pre, lab in [(axs[0], '', '점 단위'), (axs[1], 'patch_', '패치 단위')]:
            w = .8/len(q); xs = np.arange(len(CN) + 1)
            for i, (v, r) in enumerate(q.iterrows()):
                vals = [r[f'{pre}ok_{c}'] for c in CN] + [r[f'{pre}ok_전체']]
                ax.bar(xs - .4 + w*(i + .5), vals, w, color=cols[i], label=v + (' (참값으로)' if v in GT_ROWS else ''), hatch='//' if v in GT_ROWS else None, edgecolor='white', lw=.3)
            bm = [q.loc['본 방법', f'{pre}ok_{c}'] for c in CN] + [q.loc['본 방법', f'{pre}ok_전체']]
            for k, b_ in enumerate(bm): ax.hlines(b_, k - .42, k + .42, color='k', lw=.8, ls='--')
            ax.set_ylabel(f'목표 맞음 % ({lab})'); ax.set_ylim(0, 100); ax.grid(axis='y', lw=.3, alpha=.5)
        axs[1].set_xticks(np.arange(len(CN) + 1)); axs[1].set_xticklabels(CN + ['전체']); axs[0].legend(fontsize=5.5, ncol=4, loc='lower left', framealpha=.9)
        fig.suptitle(f'{PN[p]} {sf}: 경우별 목표 맞음 — 구조 하한·상한과 기존 판 (점선 = 본 방법)', fontsize=9); fig.tight_layout()
        save(fig, f'fig12_bars_{p}', dict(prior=p, surface=sf, rows=list(q.index), source='tables/t12_t13_bounds.csv'))
    CK = pd.DataFrame(CHK); write('checks', CK, note='검산. ok = 같음(점 단위 1e-9, s_main_summary 는 표의 소수 둘째 자리).', md=lambda q: q.groupby('check').agg(cells=('ok', 'size'), equal=('ok', 'sum')).reset_index())
    print('CHECKS', CK.groupby('check').ok.agg(['size', 'sum']).to_string(), flush=True)
    progress(f'js2 표·그림 12·14 끝 ({round(T.s())} 초); 검산 {int(CK.ok.sum())}/{len(CK)} 같음')
if __name__ == '__main__': main()
