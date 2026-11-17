"""a1 결과로 표를 만든다 (2절의 값). 참값은 채점에만 쓰였다. 사용: a2_tables.py"""
from common import *
import pandas as pd
TAB = D/'tables'
CN = [CASE[c] for c in CASES]
BASELINE = ['사전 정보 단독', '영상 단독', '본 방법', '패치 다수결 상한']
REP = ['기존 1 T=0.5 m', '기존 1 T=1 m', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '기존 4 결합(세 실험 지역)', '기존 4 결합(전 건물)', '기존 5 T=0.5 m', '기존 5 T=L']
NO_BEST = ['패치 다수결 상한', '기존 4 결합(세 실험 지역)']   # + 참값으로 고름, 참고 줄(4.6)
def write(name, df, note='', md=None):
    TAB.mkdir(parents=True, exist_ok=True); df.to_csv(TAB/f'{name}.csv', index=False)
    (TAB/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df if md is None else md(df)
    lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False): lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.2f}' if isinstance(x, float) else str(x).replace('|', '/')) for x in r) + ' |')
    (TAB/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
def surfaces(prior): return [('지붕', ['지붕']), ('벽', ['벽']), ('모두', ['지붕', '벽'])] if prior == 'LoD2' else [('지붕', ['지붕'])]
def agg(x, keys):
    s = x.groupby(keys + ['case'], sort=False)[['n', 'ok', 'name_ok', 'made']].sum().reset_index(); return s
def wide(s, keys):
    rows = []
    for k, q in s.groupby(keys, sort=False):
        k = k if isinstance(k, tuple) else (k,); r = dict(zip(keys, k)); q = q.set_index('case')
        for c in CN:
            n = q['n'].get(c, 0); r[f'n_{c}'] = int(n); r[f'ok_{c}'] = 100*q['ok'].get(c, 0)/n if n else np.nan
            r[f'name_{c}'] = 100*q['name_ok'].get(c, 0)/n if n else np.nan; r[f'made_{c}'] = 100*q['made'].get(c, 0)/n if n else np.nan
        nt = q['n'].sum(); r['n_전체'] = int(nt); r['ok_전체'] = 100*q['ok'].sum()/nt if nt else np.nan
        rows.append(r)
    return pd.DataFrame(rows)
def summary3(df, by):
    """요약 (가) 평균, (나) 최솟값·경우, (다) 최대 격차(참값 쓰지 않는 판 가운데 가장 높은 값 기준)."""
    oks = [f'ok_{c}' for c in CN]; df = df.copy(); df['요약 가 평균'] = df[oks].mean(1); df['요약 나 최솟값'] = df[oks].min(1); df['요약 나 경우'] = [CN[int(np.nanargmin(v))] if np.isfinite(v).any() else '' for v in df[oks].values]
    gap = []
    for _, q in df.groupby(by, sort=False):
        pool = q[~q['variant'].isin(NO_BEST) & ~q['gt_selected'] & ~q['reference']]; best = pool[oks].max(0)
        for i, r in q.iterrows(): gap.append((i, float(np.nanmax((best.values - r[oks].values.astype(float))))))
    g = dict(gap); df['요약 다 최대 격차'] = [g[i] for i in df.index]; return df
def main():
    T = Timer(); OUTS = {}
    for prior in ['LoD2', 'ALS']:
        x = pd.read_csv(O/f'cross_{prior}.csv'); x['ok'] = x['ok'].astype(float)
        a1 = json.loads((O/f'a1_{prior}.json').read_text()); OUTS[prior] = (x, a1)
    S, SPL, BD, SW = [], [], [], []
    for prior, (x, a1) in OUTS.items():
        bl = pd.read_csv(O/f'building_{prior}.csv')
        for sn, kinds in surfaces(prior):
            for scope in ['전체', '세 실험 지역 결합 범위']:
                q = x[x['kind'].isin(kinds)]
                if scope == '전체': q = q[q['family'] != 'old4_3']
                else: q = q[q['fusion3']]
                w = wide(agg(q, ['variant', 'family']), ['variant', 'family']); w.insert(0, 'scope', scope); w.insert(0, 'surface', sn); w.insert(0, 'prior', prior); S.append(w)
            # 나눔 (전체 범위)
            q = x[x['kind'].isin(kinds) & (x['family'] != 'old4_3')]
            for dim in ['group', 'place', 'textureless']:
                w = wide(agg(q, ['variant', dim]), ['variant', dim]).rename(columns={dim: 'split_value'}); w.insert(0, 'split', dim); w.insert(0, 'surface', sn); w.insert(0, 'prior', prior); SPL.append(w)
            # 건물별
            b = bl[bl['kind'].isin(kinds)].groupby(['variant', 'building', 'case'])[['n', 'ok']].sum().reset_index(); b['pct'] = 100*b['ok']/b['n']
            base = b[b['variant'] == '본 방법'].set_index(['building', 'case'])['pct']
            for v, q in b.groupby('variant', sort=False):
                q = q[q['n'] >= 200]; dlt = (q.set_index(['building', 'case'])['pct'] - base.reindex(q.set_index(['building', 'case']).index)).dropna()
                r = dict(prior=prior, surface=sn, variant=v, cells=len(dlt), diff_median_pp=float(dlt.median()) if len(dlt) else np.nan, diff_q25_pp=float(dlt.quantile(.25)) if len(dlt) else np.nan,
                         diff_q75_pp=float(dlt.quantile(.75)) if len(dlt) else np.nan, base_better_cells=int((dlt < 0).sum()), base_worse_cells=int((dlt > 0).sum()))
                for c in CN:
                    dc = dlt[dlt.index.get_level_values('case') == c]; r[f'diff_median_pp_{c}'] = float(dc.median()) if len(dc) else np.nan; r[f'base_better_{c}'] = int((dc < 0).sum()); r[f'base_worse_{c}'] = int((dc > 0).sum())
                BD.append(r)
            if sn == '지붕' or prior == 'LoD2':
                bb = b.copy(); bb.insert(0, 'surface', sn); bb.insert(0, 'prior', prior); SW.append(bb)
    S = pd.concat(S, ignore_index=True); S['gt_selected'] = False; S['reference'] = False
    # 3.1 참값으로 고른 값: 유형마다 요약 (가)가 가장 높은 값
    oks = [f'ok_{c}' for c in CN]; extra = []
    for (prior, sn, scope), q in S[S['scope'] == '전체'].groupby(['prior', 'surface', 'scope'], sort=False):
        for fam, lab in [('old1', '기존 1'), ('old2', '기존 2'), ('old3', '기존 3')]:
            f = q[q['family'] == fam].copy()
            if not len(f): continue
            f['m'] = f[oks].mean(1); r = f.sort_values('m', ascending=False).iloc[0].drop('m').copy(); r['variant'] = f"{lab} 참값으로 고름 ({r['variant']})"; r['gt_selected'] = True; extra.append(r)
    S = pd.concat([S, pd.DataFrame(extra)], ignore_index=True)
    S = summary3(S, ['prior', 'surface', 'scope'])
    base = S[S['variant'] == '본 방법'].set_index(['prior', 'surface', 'scope'])
    for c in CN + ['전체']:
        S[f'diff_pp_{c}'] = [r[f'ok_{c}'] - base.loc[(r['prior'], r['surface'], r['scope']), f'ok_{c}'] for _, r in S.iterrows()]
    # 바뀐 넓이
    ca = {}
    for prior, (x, a1) in OUTS.items():
        for v, nt in a1['notes'].items(): ca[(prior, v)] = (nt.get('changed_area_m2', np.nan), nt.get('changed_patches', np.nan))
    S['changed_area_m2'] = [ca.get((p, v.split(' 참값으로 고름 (')[-1].rstrip(')') if '참값으로 고름' in v else v), (np.nan,))[0] for p, v in zip(S['prior'], S['variant'])]
    BD = pd.DataFrame(BD); bmed = BD.set_index(['prior', 'surface', 'variant'])['diff_median_pp']
    S['building_diff_median_pp'] = [bmed.get((p, s, v.split(' 참값으로 고름 (')[-1].rstrip(')') if '참값으로 고름' in v else v), np.nan) for p, s, v in zip(S['prior'], S['surface'], S['variant'])]
    note = '목표 맞음 % = 참값 점 비율(JC 2.5). 요약 가 = 네 경우 평균, 나 = 최솟값과 그 경우, 다 = 경우마다 (참값을 쓰지 않는 판 가운데 가장 높은 값 − 이 판) 의 최댓값(상한·참값으로 고름·기존 4 세 지역 줄은 기준에서 뺌). 범위 "세 실험 지역 결합 범위" = 기존 4(JUDGEAPPLY 결합)가 있는 세 실험 지역 참값 점만.'
    write('s_all_variants', S, note=note, md=lambda d: d[(d['scope'] == '전체')][['prior', 'surface', 'variant'] + oks + ['ok_전체', '요약 가 평균', '요약 나 최솟값', '요약 나 경우', '요약 다 최대 격차']])
    # 요약 표 (보고서 2): 사전 정보마다, LoD2 = 모두
    order = BASELINE + REP + [v for v in S['variant'].unique() if v.split(' ')[0] in ('검출', '식별', '유보', '처리', '가시성')]
    main_rows = S[(S['scope'] == '전체') & (((S['prior'] == 'LoD2') & (S['surface'] == '모두')) | ((S['prior'] == 'ALS') & (S['surface'] == '지붕'))) & S['variant'].isin(order)].copy()
    main_rows['o'] = main_rows['variant'].map({v: i for i, v in enumerate(order)}); main_rows = main_rows.sort_values(['prior', 'o'], ascending=[False, True])
    cols = ['prior', 'variant'] + oks + ['ok_전체', '요약 가 평균', '요약 나 최솟값', '요약 나 경우', '요약 다 최대 격차'] + [f'diff_pp_{c}' for c in CN] + ['building_diff_median_pp']
    write('s_main_summary', main_rows[cols + [f'n_{c}' for c in CN]], note=note + ' LoD2 = 지붕과 벽 합침, 항공 LiDAR = 지붕.', md=lambda d: d[cols])
    f3 = S[(S['scope'] == '세 실험 지역 결합 범위') & S['variant'].isin(BASELINE + REP)]
    write('s_fusion3_scope', f3, note=note + ' 세 실험 지역 결합 범위만(기존 4를 같은 참값 점에서).', md=lambda d: d[['prior', 'surface', 'variant'] + oks + ['ok_전체'] + [f'n_{c}' for c in CN]])
    # 값 훑기 (3.1)
    sw = S[(S['scope'] == '전체') & (S['family'].isin(['old1', 'old2', 'old3']) | S['gt_selected'])]
    write('s_sweep', sw, note=note + ' 3.1 값 훑기. "참값으로 고름" 줄은 요약 가가 가장 높은 값을 참값으로 고른 참고 줄.', md=lambda d: d[['prior', 'surface', 'variant'] + oks + ['ok_전체', '요약 가 평균', '요약 나 최솟값', '요약 나 경우', '요약 다 최대 격차']])
    # 판정 이름 맞음, 판정이 만든 오차
    write('s_name_made', S[S['scope'] == '전체'][['prior', 'surface', 'variant'] + [f'name_{c}' for c in CN] + [f'made_{c}' for c in CN]], note='판정 이름 맞음 % (경우의 기대 판정과 같음), 판정이 만든 오차 % (이 판 목표 τ 밖, 사전 정보 단독 또는 영상 단독 목표 τ 안).')
    write('s_splits', pd.concat(SPL, ignore_index=True), note='나눔: group(세 실험 지역·나머지), place(면 안쪽·면 경계·건물 가장자리·없음), textureless. 목표 맞음 %.', md=lambda d: d[d['variant'].isin(['본 방법'])][['prior', 'surface', 'split', 'split_value', 'variant'] + oks])
    write('s_building_diff', BD, note='건물 x 경우 칸(참값 점 200개 이상)마다 이 판 − 본값 목표 맞음 %p. base_better = 본값이 나은 칸 수.', md=lambda d: d[['prior', 'surface', 'variant', 'cells', 'diff_median_pp', 'diff_q25_pp', 'diff_q75_pp', 'base_better_cells', 'base_worse_cells']])
    write('s_building_values', pd.concat(SW, ignore_index=True), note='건물 x 경우의 목표 맞음 (n, ok = 맞은 참값 점 수, pct).', md=lambda d: d.head(0))
    tr = pd.concat([pd.read_csv(O/f'trans_{p}.csv') for p in OUTS], ignore_index=True)
    write('s_transitions', tr, note='본값 판정 → 이 판 판정, 넓이 m² (참값 없는 패치 포함).', md=lambda d: d[~d['variant'].isin(BASELINE)].sort_values('area_m2', ascending=False).groupby(['prior', 'variant']).head(3))
    fv = pd.concat([pd.read_csv(O/f'five_{p}.csv') for p in OUTS], ignore_index=True)
    write('s_five_percent', fv, note='5 % 확인 (JC s8 규칙): 칸 0 패치(사전 정보·영상 깊이 높이 모두 τ 안) 넓이 가운데 판의 한계 밖 비율. 명목 5 %.')
    p44 = pd.concat([pd.read_csv(O/f'process44_{p}.csv') for p in OUTS], ignore_index=True)
    write('s_process44', p44[p44['variant'].isin(['본 방법', '처리 1 일치는 사전 정보 높이', '처리 2 일치는 영상 깊이 높이', '사전 정보 단독', '영상 단독'])], note='4.4: 두 자료 모두 유효 참값 점에서 목표 면까지 거리 절댓값의 중앙값과 NMAD (m).')
    pr = pd.concat([pd.read_csv(O/f'photo_refs_{p}.csv') for p in OUTS], ignore_index=True)
    write('s_photo_refs', pr, note='사진 점 기준(참값 없음): t(= t_q5), t_q1~q50 (기존 3), c_lo·c_hi (식별 5). t 와 같은 표본(5000개, 씨앗 20261112).')
    dt3 = pd.concat([pd.read_csv(O/f'det3_{p}.csv') for p in OUTS], ignore_index=True)
    write('s_det3_limits', dt3, note='검출 3 지역 하나의 한계: 넓이 가중 중앙값 m, NMAD, 한계 1.96 NMAD (m).')
    ck = []; nt = []
    for prior, (x, a1) in OUTS.items():
        ck += list(a1['checks'])
        for v, n_ in a1['notes'].items(): nt.append(dict(prior=prior, variant=v, **{k: (json.dumps(w, ensure_ascii=False) if isinstance(w, (list, dict)) else w) for k, w in n_.items()}))
    write('s_checks', pd.DataFrame(ck), note='검산.'); write('s_variant_notes', pd.DataFrame(nt), note='판마다 쓴 값과 넓이(L 없음→사전정보 사용 넓이, u_M 없는 일치 넓이, 바뀐 넓이).')
    progress(f'a2 표 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
