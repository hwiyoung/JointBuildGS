"""단계 3(정량): 집계, 지금 방법 두 가지와 맞대기, 옛 정답과 새 정답, 점검. 판단 값은 읽기만.
나오는 것: /docs/tables/<묶음>/*.md|csv (반올림 전 값), /out/forward_<prior>[_<stage>].csv.gz, reverse_<prior>[...].csv.gz. 사용: GT_STAGE=ga|full g3_tables.py"""
from common import *
import pandas as pd
SUB = {'ga': '가', 'ga2': '가2'}.get(STAGE, '151동')
TD = D/'tables'/SUB
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)]
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    for r in df.itertuples(index=False): L.append('| ' + ' | '.join(fm(x) for x in r) + ' |')
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def site_of(B):
    return {b: (SITES[r['experiment_sites'][0]] if r['experiment_sites'] else '그 밖') for b, r in B.items()}
def load(prior, B):
    F = loadz(O/'work'/STAGE/f'forward_{prior}.npz'); i = F['patch_index']
    if 'raw_n' not in F: F['raw_n'] = loadz(O/'work/ga'/f'forward_{prior}.npz', ['raw_n'])['raw_n']   # 가2: 판단 원통 점 수는 묶음 가 값(점검용 옆 열)
    P = loadz(inp('patches', prior=prior), ['kind', 'area', 'place', 'region', 'building', 'j_region', 'centre', 'normal', 'prior_height_m', 'tile', 'tiles'])
    t = pd.read_csv(inp('patch_table', prior=prior), usecols=['patch_index', 'patch_id', 'initial_state', 'none_cyl_points', 'none_n', 'combo_D_judgment'])
    assert (t.patch_index.values == np.arange(len(t))).all()
    df = pd.DataFrame(dict(patch_index=i, patch_id=t.patch_id.values[i], building=P['building'][i], site=[site_of(B)[b] for b in P['building'][i]], region=P['region'][i],
                           kind=P['kind'][i], surface=[KN[k] for k in P['kind'][i]], place=[PLACE[p] for p in P['place'][i]], area_m2=P['area'][i],
                           answer=[FWD[a] if a >= 0 else FWD_X for a in F['answer']], h_M_m=F['h_M'], tau_m=F['tau'], gt_column=F['n_total'], gt_band_prior=F['n_b0'], gt_band_image=F['n_bM'],
                           gt_dens_1m=F['n_dens'], image_cylinder=F['raw_n'], gt_clusters=F['n_cl'],
                           initial_state=t.initial_state.values[i], none_cyl_points=t.none_cyl_points.values[i], none_n=t.none_n.values[i],
                           judgment_jc2=[JUD[int(x)] for x in P['j_region'][i, 4]], judgment_1122=t.combo_D_judgment.values[i]))
    if STAGE == 'ga2':   # 덧붙임 4: h_I(패치 기둥 2τ 창), 묶음 가 값은 옆 열
        df['h_M_m'] = F['ga_h_M']; df.insert(df.columns.get_loc('h_M_m') + 1, 'h_I_m', F['h_I'])
        for k in ['img_col', 'img_win', 'img_tie', 'img_second_n', 'img_second_m']: df[k] = F[k]
        df['ga_answer'] = [FWD[a] if a >= 0 else FWD_X for a in F['ga_answer']]
    for k in range(6): df[f'cl{k+1}_n'] = F['cl'][:, 2*k]; df[f'cl{k+1}_median_m'] = F['cl'][:, 2*k+1]
    geo = dict(centre=P['centre'][i], normal=P['normal'][i], prior_height=P['prior_height_m'][i], tile=P['tile'][i], tiles=P['tiles'])
    return df, geo
def share_table(df, by, col, names, area='area_m2'):
    rows = []
    for key, g in df.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,); tot = g[area].sum(); r = dict(zip(by, key)); r.update(patches=len(g), area_m2=tot)
        for n in names: a = g.loc[g[col] == n, area].sum(); r[f'{n} m²'] = a; r[f'{n} %'] = 100*a/tot if tot else np.nan
        rows.append(r)
    return pd.DataFrame(rows)
def with_all(df, by_site=True):
    parts = [df.assign(site='세 지역' if STAGE in ('ga', 'ga2') else '151동')]
    if by_site and STAGE in ('ga', 'ga2'): parts.append(df)
    a = pd.concat(parts); b = pd.concat([a, a.assign(surface='모두')]) if (a.surface == '벽').any() else a
    return b
def main():
    c = cfg(); B = buildings(); T = Timer(); rec = dict(at=now(), stage=STAGE, scientific_verdict=None); rng = np.random.default_rng(c['seed'])
    allf = []; allr = []
    for prior in PRIORS:
        df, geo = load(prior, B); df.insert(0, 'prior', PN[prior]); allf.append(df)
        sfx = '' if STAGE == 'full' else f'_{STAGE}'; df.to_csv(O/f'forward_{prior}{sfx}.csv.gz', index=False)
        if c.get('include_reverse', True):
          Rv = loadz(O/'work'/STAGE/f'reverse_{prior}.npz'); G = loadz(O/'work'/STAGE/'reverse_geometry.npz')
          rdf = pd.DataFrame(dict(prior=PN[prior], tile=G['tiles'][G['tile']], x=G['centre'][:, 0], y=G['centre'][:, 1], z=G['centre'][:, 2], nx=G['normal'][:, 0], ny=G['normal'][:, 1], nz=G['normal'][:, 2],
                                surface=[KN[k] for k in G['kind']], area_m2=c['reverse']['patch_area_m2'], answer=[REV[a] for a in Rv['answer']], tau_m=Rv['tau'], gt_column=Rv['n_total'], gt_band=Rv['n_b0'],
                                gt_clusters=Rv['n_cl'], near_patch_index=Rv['near_patch'], near_lateral_m=Rv['near_lateral_m'], near_normal_m=Rv['near_normal_m'], cell_points=G['cell_points'], normal_radius_m=G['normal_radius']))
          rdf['far'] = (rdf.near_lateral_m > .125) | (rdf.near_normal_m.abs() > 10); rdf.to_csv(O/f'reverse_{prior}{sfx}.csv.gz', index=False); allr.append(rdf)
        # 점검: 원통 점 수 = none_cyl_points
        v = df[np.isfinite(df.image_cylinder) & (df.image_cylinder >= 0)]; pick = rng.choice(len(v), min(1000, len(v)), replace=False)
        rec[f'{prior}_cyl_check'] = dict(sample=len(pick), equal=int((v.image_cylinder.values[pick] == v.none_cyl_points.values[pick]).sum()), all_patches=len(v), all_equal=int((v.image_cylinder.values == v.none_cyl_points.values).sum()))
        P = loadz(inp('patches', prior=prior), ['area', 'building']); sc = np.isin(P['building'], list(B)); rec[f'{prior}_area'] = dict(forward=float(df.area_m2.sum()), prior_patches=float(P['area'][sc].sum()))
    F = pd.concat(allf, ignore_index=True); Rr = pd.concat(allr, ignore_index=True) if allr else None
    # 표 1 참값 밀도
    rows = []
    for (p, s), g in with_all(F, False).groupby(['prior', 'surface'], sort=False):
        x = g.gt_dens_1m.values; ok = np.isfinite(x); w = g.area_m2.values
        rows.append(dict(prior=p, surface=s, patches=len(g), area_m2=w.sum(), **{f'p{q}': np.quantile(x[ok], q/100) for q in [10, 25, 50, 75, 90]}, mean=x[ok].mean(), area_ge4_pct=100*w[ok & (x >= 4)].sum()/w.sum()))
    write('t1_gt_density', pd.DataFrame(rows), '패치 기둥 안 법선 거리 0 ± 1 m 참값 점 수 (패치 수 기준 분위), 4개 이상 넓이 비율')
    # 표 2 정방향 정답
    t2 = share_table(with_all(F), ['site', 'prior', 'surface'], 'answer', FWD + [FWD_X])
    mc = with_all(F).assign(multi=lambda d: d.gt_clusters >= 2).groupby(['site', 'prior', 'surface'], sort=False).apply(lambda g: pd.Series(dict(multi_m2=g.area_m2[g.multi].sum(), multi_pct=100*g.area_m2[g.multi].sum()/g.area_m2.sum()))).reset_index()
    write('t2_forward', t2.merge(mc, on=['site', 'prior', 'surface']), '정방향 정답 넓이와 비율, 참값 무리가 둘 이상인 넓이(multi)')
    write('t2b_forward_place', share_table(with_all(F, False), ['prior', 'surface', 'place'], 'answer', FWD + [FWD_X]), '정방향 정답, 자리별')
    # 표 3 역방향 (덧붙임 2: include_reverse=false 이면 뺌)
    if Rr is not None:
     RA = pd.concat([Rr.assign(scope='모두'), Rr[Rr.far].assign(scope='떨어진 것(옆 0.125 m 밖 또는 법선 10 m 밖)')])
     RA = pd.concat([RA, RA.assign(surface='모두')])
     write('t3_reverse', share_table(RA, ['prior', 'scope', 'surface'], 'answer', REV), '역방향 정답(영상 쪽 패치 하나 = 0.0625 m²)')
    # 표 4 맞대기
    cor = c['compare']['correct']; JC = ['일치', '영상 깊이 사용', '사전정보 사용', '결측', '제거', '미판정']; rows4 = []; summ = []
    for jcol, jname in [('judgment_jc2', '(가) JUDGECHECK-v2 본 방법'), ('judgment_1122', '(나) 11/22 새 구조')]:
        for (p, s), g in with_all(F, False).groupby(['prior', 'surface'], sort=False):
            for a in FWD + [FWD_X]:
                h = g[g.answer == a]; tot = h.area_m2.sum(); r = dict(compare=jname, prior=p, surface=s, answer=a, patches=len(h), area_m2=tot)
                for j in JC: x = h.area_m2[h[jcol] == j].sum(); r[f'{j} m²'] = x; r[f'{j} %'] = 100*x/tot if (tot and a in cor) else np.nan
                if a in cor: r['맞게 고른 %'] = 100*h.area_m2[h[jcol].isin(cor[a])].sum()/tot if tot else np.nan; summ.append(dict(compare=jname, prior=p, surface=s, answer=a, area_m2=tot, correct_pct=r['맞게 고른 %'], correct_set='·'.join(cor[a])))
                rows4.append(r)
    write('t4_compare', pd.DataFrame(rows4), '정방향 정답(줄) × 판정(칸) 넓이. 비율은 두 자료·영상·사전 정보 줄만(둘 다 틀림·정답 없음은 넓이만)')
    write('t4b_compare_summary', pd.DataFrame(summ), '줄마다 맞게 고른 넓이 비율. 맞는 판정: 두 자료=일치, 영상=영상 깊이 사용, 사전 정보(영상 틀림)=사전정보 사용, 사전 정보(영상 없음)=결측·사전정보 사용')
    # 표 5 옛 정답 × 새 정답
    MAP = {0: '두 자료', 1: '영상', 2: '사전 정보(영상 틀림)', 4: '사전 정보(영상 없음)', 3: '둘 다 틀림', -9: '정답 없음'}
    G5 = with_all(F, False); G5 = G5.assign(old=[STATE[int(x)] for x in G5.initial_state]); rows5 = []
    for (p, s, o), g in G5.groupby(['prior', 'surface', 'old'], sort=False):
        r = dict(prior=p, surface=s, old=o, area_m2=g.area_m2.sum())
        for a in FWD + [FWD_X]: r[f'{a} m²'] = g.area_m2[g.answer == a].sum()
        rows5.append(r)
    write('t5_old_new', pd.DataFrame(rows5), '옛 정답(initial_state) × 새 정방향 정답 넓이. 옛 번호: 0 두 자료 모두 유효, 1 사전정보 오류, 2 영상 깊이 오류, 4 영상 깊이 결측, 3 네 경우 밖, -2 동률, -3 참값 점 3개 미만, -9 참값 없음')
    G5 = G5[G5.surface != '모두'] if (G5.surface == '모두').any() else G5
    G5 = G5.assign(same=[MAP.get(int(i)) == a for i, a in zip(G5.initial_state, G5.answer)]); diff = G5[~G5.same]
    top = diff.groupby(['prior', 'old', 'answer']).area_m2.sum().reset_index().sort_values('area_m2', ascending=False)
    rows6 = []
    for p in top.prior.unique():
        for _, r in top[top.prior == p].head(3).iterrows():
            g = diff[(diff.prior == p) & (diff.old == r.old) & (diff.answer == r.answer)]; d = dict(prior=p, old=r.old, new=r.answer, area_m2=r.area_m2)
            for pl in ['면 안쪽', '면 경계', '건물 가장자리', '자리 없음']: d[f'{pl} %'] = 100*g.area_m2[g.place == pl].sum()/r.area_m2
            for sf in ['지붕', '벽']: d[f'{sf} %'] = 100*g.area_m2[g.surface == sf].sum()/r.area_m2
            rows6.append(d)
    write('t5b_top_changes', pd.DataFrame(rows6), '옛 정답과 새 정답이 다른 칸, 넓이 큰 차례로 셋(사전 정보마다), 자리·면별 비율')
    # 점검: 두 자료 비율과 옛 '두 자료 모두 유효'(패치 넓이, 점)
    ck = []
    for prior in PRIORS:
        g = F[F.prior == PN[prior]]; z = loadz(PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2/analysis'/f'gt_{prior}.npz', ['gid', 'case', 'paired'])
        m = z['paired'] & np.isin(z['gid'], g.patch_index.values); pt0 = 100*(z['case'][m] == 0).mean() if m.any() else np.nan
        ck.append(dict(prior=PN[prior], new_both_pct=100*g.area_m2[g.answer == '두 자료'].sum()/g.area_m2.sum(), new_both_pct_of_with_answer=100*g.area_m2[g.answer == '두 자료'].sum()/g.area_m2[~g.answer.isin(['정답 없음', FWD_X])].sum(),
                       old_both_patch_pct=100*g.area_m2[g.initial_state == 0].sum()/g.area_m2.sum(), old_both_patch_pct_of_with_case=100*g.area_m2[g.initial_state == 0].sum()/g.area_m2[g.initial_state.isin([0, 1, 2, 3, 4, -2])].sum(),
                       old_both_point_pct=pt0, old_points=int(m.sum())))
    write('t6_both_check', pd.DataFrame(ck), "'두 자료' 넓이 비율과 옛 정답 '두 자료 모두 유효'(패치 넓이, 참값 점) — 같은 패치")
    if STAGE == 'ga2':
        G7 = with_all(F, False); rows7 = []
        for (p, s_), g in G7.groupby(['prior', 'surface'], sort=False):
            for a in FWD + [FWD_X]:
                h = g[g.ga_answer == a]
                if not len(h): continue
                r = dict(prior=p, surface=s_, ga=a, area_m2=h.area_m2.sum())
                for b in FWD + [FWD_X]: r[f'{b} m²'] = h.area_m2[h.answer == b].sum()
                rows7.append(r)
        write('t7_ga_to_ga2', pd.DataFrame(rows7), '묶음 가 정답(줄) × 가2 정답(칸) 넓이')
        G7 = G7[G7.surface != '모두'] if (G7.surface == '모두').any() else G7; ch = G7[G7.ga_answer != G7.answer]; rows7b = []
        for (p, s_, a, b), g in ch.groupby(['prior', 'surface', 'ga_answer', 'answer']):
            r = dict(prior=p, surface=s_, ga=a, ga2=b, patches=len(g), area_m2=g.area_m2.sum())
            for pl in ['면 안쪽', '면 경계', '건물 가장자리', '자리 없음']: r[f'{pl} %'] = 100*g.area_m2[g.place == pl].sum()/r['area_m2']
            rows7b.append(r)
        write('t7b_changed_place', pd.DataFrame(rows7b).sort_values(['prior', 'area_m2'], ascending=[True, False]), '가 → 가2 바뀐 칸마다 자리 비율')
        rows8 = []
        for (p, s_), g in with_all(F, False).groupby(['prior', 'surface'], sort=False):
            two = (g.img_win >= 4) & (g.img_second_n >= .5*g.img_win); tie = g.img_tie == 1; A = g.area_m2.sum(); r = dict(prior=p, surface=s_, area_m2=A, two_layer_m2=g.area_m2[two].sum(), two_layer_pct=100*g.area_m2[two].sum()/A,
                     tie_patches=int(tie.sum()), tie_m2=g.area_m2[tie].sum())
            for pl in ['면 안쪽', '면 경계', '건물 가장자리', '자리 없음']: r[f'two_layer {pl} %'] = 100*g.area_m2[two & (g.place == pl)].sum()/max(g.area_m2[two].sum(), 1e-12)
            rows8.append(r)
        write('t8_two_layer', pd.DataFrame(rows8), '층이 둘인 패치(두 번째로 많이 몰린 창의 점 수 ≥ 첫 창의 절반, 첫 창 4개 이상)와 동률(다른 최다 창의 중앙값이 τ 넘게 떨어짐)')
    rec['both_check'] = ck; rec['seconds'] = T.s(); dump(D/'tables'/SUB/'checks.json', rec); progress(f'단계 3 표 {SUB}: {T.s():.0f} s'); print(json.dumps(jsafe(rec), ensure_ascii=False)[:3000])
if __name__ == '__main__': main()
