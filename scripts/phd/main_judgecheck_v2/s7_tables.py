"""확인 1 (5.1)과 확인 5 (5.2 가·나)의 표. 참값은 경우·목표 맞음·정답 판정에만 쓴다(판정은 이미 저장됨).
표는 docs tables/ 에 csv·json(반올림 전)·md(요약). 넓이 = 0.25 m 칸 수 x 0.0625 m2."""
from common import *
import pandas as pd
import jc2_judge as J
CASE = {0: '두 자료 모두 유효', 1: '사전정보 오류', 2: '영상 깊이 오류', 4: '영상 깊이 결측'}
JUD = {0: '일치', 2: '영상 깊이 사용', 1: '사전정보 사용', 4: '결측', 3: '제거', 9: '미판정'}
MATCH = {0: 0, 1: 2, 2: 1, 4: 4}
NINE = ['두 자료 모두 유효', '영상 깊이 오류', '영상 깊이 결측', '사전정보 오류', '밖1 둘 다 틀림', '밖2 사전 정보 틀림·영상 없음', '밖3 사전 정보 없음·영상 맞음', '밖4 사전 정보 없음·영상 틀림', '밖5 둘 다 없음']
NINE2CASE = {0: 0, 3: 1, 1: 2, 2: 4}
VNAME = {'prior_only': '사전 정보 단독', 'image_only': '영상 단독', 'geometry_only': '기하 일관성 검사 단독', 'photo_only': '광도 일관성 검사 단독', 'method': '본 방법', 'alt_na': '판 나', 'alt_da': '판 다', 'oracle': '정답 판정', 'current': '세 지역 지금 판'}
PLACE = {0: '면 안쪽', 1: '면 경계', 2: '건물 가장자리'}
TAB = D/'tables'
def area(cells): return float(len(np.unique(cells))*0.0625)
def write(name, df, md_cols=None, md_rows=None, note=''):
    TAB.mkdir(parents=True, exist_ok=True); df.to_csv(TAB/f'{name}.csv', index=False)
    (TAB/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df if md_rows is None else md_rows(df)
    if md_cols: m = m[md_cols]
    lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False): lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.2f}' if isinstance(x, float) else str(x).replace('|', '/')) for x in r) + ' |')
    (TAB/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
def dims(d, prior):
    G = {'전체': np.ones(len(d['src']), bool), '세 실험 지역': d['group'] == 'experiment', '나머지': d['group'] == 'rest'}
    P = {'모든 자리': np.ones(len(d['src']), bool), **{v: d['place'] == k for k, v in PLACE.items()}}
    S = {'지붕': d['patch_kind'] == 1, '벽': d['patch_kind'] == 2, '모두': np.ones(len(d['src']), bool)} if prior == 'LoD2' else {'지붕': d['patch_kind'] == 1}
    return G, P, S
def load(prior):
    d = loadz(O/'analysis'/f'gt_{prior}.npz'); d['region_v'] = d['region_v']; return d
def small(n, lim=1000): return '적음' if n < lim else ''
def confusion(prior, d, rest_unpaired):
    rows = []; G, P, S = dims(d, prior); paired = d['paired']; mi = J.VARIANTS.index('method')
    for defn in ['지금 정의', '아홉 조합 정의']:
        cs = d['case'] if defn == '지금 정의' else np.array([NINE2CASE.get(int(x), 3) for x in d['nine']], np.int8)
        for gn, gm in G.items():
            for pn, pm in P.items():
                for sn, sm in S.items():
                    base = paired & gm & pm & sm
                    for c in [0, 1, 2, 4, 3]:
                        rm = base & (cs == c); rn = int(rm.sum())
                        if c == 3:
                            rows.append(dict(prior=prior, definition=defn, group=gn, place=pn, surface=sn, case='네 경우 밖', judgment='', n=rn, row_n=int(base.sum()), ratio_pct=100*rn/max(int(base.sum()), 1), target_ok_pct=np.nan, area_m2=area(d['cell'][rm]), small=small(rn)))
                            continue
                        for j in [0, 2, 1, 4, 3, 9]:
                            m = rm & (d['region_v'][mi] == j); n = int(m.sum())
                            rows.append(dict(prior=prior, definition=defn, group=gn, place=pn, surface=sn, case=CASE[c], judgment=JUD[j], n=n, row_n=rn, ratio_pct=100*n/rn if rn else np.nan,
                                             target_ok_pct=100*float(d['target_ok_v'][mi][m].mean()) if n else np.nan, area_m2=area(d['cell'][m]) if n else 0., match=(MATCH[c] == j), small=small(rn)))
                    if gn == '전체' and pn == '모든 자리' and sn == ('모두' if prior == 'LoD2' else '지붕'):
                        rows.append(dict(prior=prior, definition=defn, group=gn, place=pn, surface=sn, case='판정 없음', judgment='', n=int((~paired).sum()) + rest_unpaired, row_n=np.nan, ratio_pct=np.nan, target_ok_pct=np.nan, area_m2=np.nan, small='',
                                         note=f'실험 지역 저장 행 {int((~paired).sum())} + 나머지 {rest_unpaired} (0.1 m 칸으로 솎은 수)'))
    return pd.DataFrame(rows)
def summary(prior, d):
    rows = []; G, P, S = dims(d, prior); paired = d['paired']
    for gn, gm in G.items():
        for pn, pm in P.items():
            for sn, sm in S.items():
                base = paired & gm & pm & sm
                for v in J.VARIANTS + ['current']:
                    for c in [0, 1, 2, 4]:
                        m = base & (d['case'] == c)
                        if v == 'current':
                            m = m & (d['src'] == 1) & (d['current_region'] >= 0); ok = d['current_target_ok'][m]; nm = d['current_region'][m] == MATCH[c]
                        else:
                            j = J.VARIANTS.index(v); ok = d['target_ok_v'][j][m]; nm = d['region_v'][j][m] == MATCH[c]
                        n = int(m.sum())
                        rows.append(dict(prior=prior, group=gn, place=pn, surface=sn, variant=VNAME[v], case=CASE[c], n=n, target_ok_pct=100*float(ok.mean()) if n else np.nan, name_ok_pct=100*float(nm.mean()) if n else np.nan, small=small(n)))
    return pd.DataFrame(rows)
def made_saved(prior, d):
    rows = []; G, P, S = dims(d, prior); paired = d['paired']; V = J.VARIANTS
    mo, po, io = d['target_ok_v'][V.index('method')], d['target_ok_v'][V.index('prior_only')], d['target_ok_v'][V.index('image_only')]
    for gn, gm in G.items():
        for pn, pm in P.items():
            for sn, sm in S.items():
                for c in [0, 1, 2, 4]:
                    m = paired & gm & pm & sm & (d['case'] == c); n = int(m.sum())
                    made = m & ~mo & (po | io); saved = m & mo & ~po & ~io
                    rows.append(dict(prior=prior, group=gn, place=pn, surface=sn, case=CASE[c], n=n, made_error_n=int(made.sum()), made_error_pct=100*made.sum()/n if n else np.nan, saved_n=int(saved.sum()), saved_pct=100*saved.sum()/n if n else np.nan, small=small(n)))
    return pd.DataFrame(rows)
def per_building(prior, d):
    rows = []; V = J.VARIANTS; paired = d['paired']
    for b in sorted(set(d['building'][paired])):
        bm = paired & (d['building'] == b); grp = d['group'][bm][0]
        for c in [0, 1, 2, 4]:
            m = bm & (d['case'] == c); n = int(m.sum()); r = dict(prior=prior, building=b, group=grp, case=CASE[c], n=n, small=small(n, 200))
            for v in ['method', 'prior_only', 'image_only']:
                j = V.index(v); r[f'{v}_target_ok_pct'] = 100*float(d['target_ok_v'][j][m].mean()) if n else np.nan; r[f'{v}_name_ok_pct'] = 100*float((d['region_v'][j][m] == MATCH[c]).mean()) if n else np.nan
            rows.append(r)
    return pd.DataFrame(rows)
def nine_tables(prior, d):
    paired = d['paired']; G, _, _ = dims(d, prior); K = {'지붕': d['gt_kind'] == 1, '벽': d['gt_kind'] == 2, '땅': d['gt_kind'] == 3, '모두': np.ones(len(d['src']), bool)}
    rows = []; mi = J.VARIANTS.index('method')
    for gn, gm in G.items():
        for kn, km in K.items():
            base = paired & gm & km; tot = int(base.sum())
            for k in range(9):
                m = base & (d['nine'] == k); n = int(m.sum()); r = dict(prior=prior, group=gn, gt_kind=kn, nine=k, nine_name=NINE[k], n=n, area_m2=area(d['cell'][m]), ratio_pct=100*n/tot if tot else np.nan,
                                                                      method_target_ok_pct=100*float(d['target_ok_v'][mi][m].mean()) if n else np.nan, small=small(n))
                for j, jn in JUD.items(): r[f'method_{jn}_pct'] = 100*float((d['region_v'][mi][m] == j).mean()) if n else np.nan
                e = m & (d['src'] == 1)
                r['exp_n'] = int(e.sum()); r['exp_finaltrain_ok_pct'] = 100*float(d['finaltrain_ok'][e].mean()) if e.any() else np.nan; r['exp_judgment_mesh_ok_pct'] = 100*float(d['judgment_mesh_ok'][e].mean()) if e.any() else np.nan
                rows.append(r)
    mp = pd.crosstab(pd.Series([NINE[k] for k in d['nine'][paired]], name='nine'), pd.Series([CASE.get(int(c), '둘 다 틀림 등(밖)') for c in d['case'][paired]], name='current_case')).reset_index()
    out4 = paired & (d['nine'] >= 4); brow = []
    for b in sorted(set(d['building'][paired])):
        bm = paired & (d['building'] == b); n = int(bm.sum()); o = bm & out4
        brow.append(dict(prior=prior, building=b, group=d['group'][bm][0], n=n, outside_n=int(o.sum()), outside_pct=100*o.sum()/n, outside_area_m2=area(d['cell'][o]), prior_wrong_or_none_pct=100*float(np.isin(d['state_P'][bm], [1, 2]).mean())))
    bdf = pd.DataFrame(brow).sort_values('outside_area_m2', ascending=False)
    return pd.DataFrame(rows), mp, bdf
def truth_hits(prior, patch_ids):
    """패치마다 캠퍼스 참값 점이 기둥 안에 있는지 (s4_unpaired patchhits, 평가 상자 안 점 포함). 짝 행이 없어도 참값이 있는 패치를 가린다."""
    tot = {}
    for p in (O/'truth/unpaired').glob(f'*__{prior}_patchhits.npz'):
        z = loadz(p)
        for s, h in zip(z['patch_id'], z['hits']):
            if h: tot[s] = tot.get(s, 0) + int(h)
    return np.array([tot.get(s, 0) > 0 for s in patch_ids], bool)
def nogt(prior):
    rows = []; mi = J.VARIANTS.index('method'); a = loadz(O/'analysis'/f'gt_{prior}.npz', ['gid', 'paired']); acc = []
    for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
        g = loadz(p, ['kind', 'area', 'patch_id']); j = loadz(O/'judge/base'/p.name, ['region']); acc.append(dict(kind=g['kind'], area=g['area'], reg=j['region'][mi], pid=g['patch_id']))
    Ntot = sum(len(x['kind']) for x in acc); has = np.zeros(Ntot, bool); has[a['gid'][a['paired']]] = True
    off = 0
    for x in acc: n = len(x['kind']); x['has'] = has[off:off + n]; off += n
    A = {k: np.concatenate([x[k] for x in acc]) for k in acc[0]}; A['has'] = A['has'] | truth_hits(prior, A['pid'])
    for kn, km in ([('지붕', A['kind'] == 1), ('벽', A['kind'] == 2)] if prior == 'LoD2' else [('지붕', A['kind'] == 1)]):
        m = km & ~A['has']; r = dict(prior=prior, surface=kn, patches=int(m.sum()), area_m2=float(A['area'][m].sum()), all_patches=int(km.sum()), share_pct=100*m.sum()/km.sum())
        for j, jn in JUD.items(): r[f'method_{jn}_pct'] = 100*float(A['area'][m & (A['reg'] == j)].sum()/max(A['area'][m].sum(), 1e-9))
        rows.append(r)
    return pd.DataFrame(rows)
def exp_training(prior, d):
    """5.3: 세 지역의 지금 판, 장면 x 경우마다 판정 맞음·틀림(목표 기준)에 FINALTRAIN 30,000회 완전성, 판단만으로 만든 면의 완전성, 참값 점 수 (RECOUNT 4.2 짜임)."""
    rows = []; e = (d['src'] == 1) & (d['current_region'] >= 0)
    for site in SITES:
        for c in [0, 1, 2, 4]:
            for res, rm in [('맞음', d['current_target_ok']), ('틀림', ~d['current_target_ok'])]:
                m = e & (d['site'] == site) & (d['case'] == c) & rm; n = int(m.sum())
                rows.append(dict(site=site, prior=prior, case=CASE[c], judgment_result=res, n_gt=n, finaltrain_completeness_pct=100*float(d['finaltrain_ok'][m].mean()) if n else np.nan, judgment_mesh_completeness_pct=100*float(d['judgment_mesh_ok'][m].mean()) if n else np.nan, small=small(n)))
    return pd.DataFrame(rows)
def main():
    cfg(); T = Timer()
    for prior in (sys.argv[1:] or ['LoD2', 'ALS']):
        d = load(prior); ru = 0   # 나머지 건물: 건물에 딸린(윤곽 안 지붕·땅, 윤곽 1 m 안 벽) 짝 없는 참값 점, 0.1 m 솎은 수 (s4_unpaired)
        for p in (O/'truth/unpaired').glob('*.json'):
            ru += int(json.loads(p.read_text()).get('priors', {}).get(prior, {}).get('unpaired_building_related_thinned', 0))
        cf = confusion(prior, d, ru); write(f'c1_confusion_{prior}', cf, note=f'확인 1 혼동 행렬 ({prior}). 칸: 그 줄 안 비율, 참값 점 수, 그 칸의 목표 맞음 %. 판정 없음 = 짝 패치가 없는 참값 점 수(세 지역 저장 행 + 나머지 건물의 윤곽 안 지붕·땅·윤곽 1 m 안 벽 점, 0.1 m 칸으로 솎은 수).',
                                                  md_rows=lambda x: x[(x.group == '전체') & (x.place == '모든 자리') & (x.surface == ('모두' if prior == 'LoD2' else '지붕')) & (x.definition == '지금 정의')], md_cols=['case', 'judgment', 'n', 'ratio_pct', 'target_ok_pct', 'area_m2', 'small'])
        sm = summary(prior, d); write(f'c1_case_summary_{prior}', sm, note=f'확인 1 경우별 요약 ({prior}): 판마다 목표 맞음 %와 판정 이름 맞음 %(정답 판정 줄 = 패치 다수결 상한).',
                                       md_rows=lambda x: x[(x.group == '전체') & (x.place == '모든 자리') & (x.surface == ('모두' if prior == 'LoD2' else '지붕'))], md_cols=['variant', 'case', 'n', 'target_ok_pct', 'name_ok_pct', 'small'])
        ms = made_saved(prior, d); write(f'c1_made_saved_{prior}', ms, note='판정이 만든 오차(본 방법 목표 τ 밖, 두 기준 가운데 하나는 τ 안)와 살린 점(본 방법 τ 안, 두 기준 모두 τ 밖).',
                                         md_rows=lambda x: x[(x.group == '전체') & (x.place == '모든 자리') & (x.surface == ('모두' if prior == 'LoD2' else '지붕'))], md_cols=['case', 'n', 'made_error_n', 'made_error_pct', 'saved_n', 'saved_pct'])
        pb = per_building(prior, d); write(f'c1_buildings_{prior}', pb, note='건물 x 경우: 본 방법·두 기준의 목표 맞음 %, 판정 이름 맞음 %. 적음 = 200개 미만.', md_rows=lambda x: x.head(0))
        nt, mp, bd = nine_tables(prior, d)
        write(f'c5_nine_{prior}', nt, note=f'확인 5 (가) 아홉 조합 ({prior}).', md_rows=lambda x: x[(x.group == '전체') & (x.gt_kind == '모두')], md_cols=['nine_name', 'n', 'area_m2', 'ratio_pct', 'method_target_ok_pct', 'exp_finaltrain_ok_pct', 'exp_judgment_mesh_ok_pct'])
        write(f'c5_nine_to_current_{prior}', mp, note='아홉 조합 → 지금 정의의 경우 (참값 점 수).')
        write(f'c5_buildings_outside_{prior}', bd, note='건물마다 네 경우 밖(아홉 조합 4~8)의 비율과 넓이, 큰 차례.', md_rows=lambda x: x.head(15))
        ng = nogt(prior); write(f'c5_no_truth_patches_{prior}', ng, note='(나) 기둥 안에 참값 점이 없는 사전 정보 패치: 수, 넓이, 본 방법 판정 비율(넓이).')
        ex = exp_training(prior, d); write(f'c6_exp_training_{prior}', ex, note='5.3 세 지역의 판정 x 학습 뒤 (지금 판 = FINALTRAIN judge_region, 목표 기준 맞음·틀림).', md_cols=['site', 'case', 'judgment_result', 'n_gt', 'finaltrain_completeness_pct', 'judgment_mesh_completeness_pct', 'small'])
        e = d['src'] == 1; write(f'c6_exp_case_check_{prior}', pd.DataFrame([dict(prior=prior, rows=int(e.sum()), case_equal_stored=int((d['case'][e] == d['case_stored'][e]).sum()))]), note='세 지역 저장 행: 다시 셈한 경우 vs GTJUDGE stage1_cells case_id.')
        print('TABLES', prior, len(cf), len(sm), round(T.mark(prior)), flush=True)
    dump(O/'analysis/tables_c1_c5.json', dict(at=now(), seconds=T.mark('end'), scientific_verdict=None))
if __name__ == '__main__': main()
