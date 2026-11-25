"""2절·8절 정답 표. 패치마다 csv(forward_<prior>_ga3.csv.gz 또는 forward151_<prior>.csv.gz)와 표:
  t1 정답 넓이 비율(사전 정보 x 지붕·벽, 지역별) · t2 문턱 곡선마다 정답 넓이 비율 · t3 가2 -> 가3 바뀜(넓이)과 바뀐 칸의 자리 비율 · t4 층 둘 넓이 · 점검(넓이 합).
151동(full): t1 을 10동과 나머지로 나눔. 사용: GT_STAGE=ga3|full g2_truth_tables.py"""
from common import *
import pandas as pd
FWDX = FWD + [FWD_X]; SUB = {'ga3': '가', 'full': '151동'}[STAGE]; TD = D/'tables'/SUB
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def shares(df, by, col):
    rows = []
    for k, g in df.groupby(by, sort=False):
        k = k if isinstance(k, tuple) else (k,); A = g.area_m2.sum(); r = dict(zip(by, k)); r.update(patches=len(g), area_m2=A)
        for a in FWDX: x = g.area_m2[g[col] == a].sum(); r[f'{a} m²'] = x; r[f'{a} %'] = 100*x/A
        rows.append(r)
    return pd.DataFrame(rows)
def main():
    c = cfg(); Ball = buildings('full'); site = {b: (SITES[r['experiment_sites'][0]] if r['experiment_sites'] else '그 밖') for b, r in Ball.items()}; curve = c['truth']['threshold_curve_m']; all_ = []; rec = dict(at=now(), stage=STAGE, scientific_verdict=None)
    for prior in PRIORS:
        Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz'); i = Z['patch_index']
        P = loadz(inp('patches', prior=prior), ['kind', 'area', 'place', 'region', 'building']); t = pd.read_csv(inp('patch_table', prior=prior), usecols=['patch_id'])
        nm = lambda a: [FWD[x] if x >= 0 else FWD_X for x in a]
        df = pd.DataFrame(dict(prior=PN[prior], patch_index=i, patch_id=t.patch_id.values[i], building=P['building'][i], site=[site[b] for b in P['building'][i]], region=P['region'][i],
                               surface=[KN[k] for k in P['kind'][i]], place=[PLACE[p] for p in P['place'][i]], area_m2=P['area'][i], answer=nm(Z['answer'][:, 0]), h_I_m=Z['h_I'][:, 0], window_points=Z['win'][:, 0],
                               column_image_points=Z['img_col'], second_m=Z['second_m'], second_n=Z['second_n'], two_layer=Z['two_layer'].astype(int), gt_band_prior=Z['n_b0'][:, 0], gt_band_image=Z['n_bI'][:, 0],
                               gt_column=Z['n_total'], tau_P=Z['tau_P'][:, 0], tau_I=Z['tau_I'][:, 0]))
        for k, x in enumerate(curve): df[f'answer_tau_{x:.2f}'] = nm(Z['answer'][:, 1+k])
        if STAGE == 'ga3':
            g2 = pd.read_csv(inp('ga2', prior=prior), usecols=['patch_index', 'answer']); assert (g2.patch_index.values == i).all(); df['ga2_answer'] = g2.answer.values
            df.to_csv(O/f'forward_{prior}_ga3.csv.gz', index=False)
        else: df.to_csv(O/f'forward151_{prior}.csv.gz', index=False)
        sc = np.isin(P['building'], list(buildings())); rec[f'{prior}_area'] = dict(truth=float(df.area_m2.sum()), patches=float(P['area'][sc].sum()) if STAGE == 'ga3' else float(P['area'][np.isin(P['building'], list(Ball))].sum()))
        all_.append(df)
    F = pd.concat(all_, ignore_index=True); F2 = pd.concat([F, F.assign(surface='모두')])
    if STAGE == 'ga3':
        write('t1_truth', pd.concat([shares(F2.assign(site='10동'), ['site', 'prior', 'surface'], 'answer'), shares(F2, ['site', 'prior', 'surface'], 'answer')]), '가3 정답 넓이 비율(τ_P: LoD2 0.30, 항공 LiDAR 0.15; τ_I 0.15)')
    else:
        F2 = F2.assign(group=np.where(F2.site == '그 밖', '나머지', '세 지역 10동'))
        write('t1_truth151', pd.concat([shares(F2.assign(group='151동'), ['group', 'prior', 'surface'], 'answer'), shares(F2, ['group', 'prior', 'surface'], 'answer')]), '151동 정답 넓이 비율(가3 규칙), 10동과 나머지')
    rows = []
    for x in curve:
        s = shares(F2, ['prior', 'surface'], f'answer_tau_{x:.2f}'); s.insert(0, 'tau_m', x); rows.append(s)
    write('t2_threshold_curve', pd.concat(rows), '문턱 곡선: 세 자료에 같은 τ(h_I 창 폭 2τ)마다 정답 넓이 비율')
    write('t4_two_layer', pd.DataFrame([dict(prior=p, surface=s, area_m2=g.area_m2.sum(), two_layer_m2=g.area_m2[g.two_layer == 1].sum(), two_layer_pct=100*g.area_m2[g.two_layer == 1].sum()/g.area_m2.sum(),
                                            **{f'{pl} %': 100*g.area_m2[(g.two_layer == 1) & (g.place == pl)].sum()/max(g.area_m2[g.two_layer == 1].sum(), 1e-12) for pl in ['면 안쪽', '면 경계', '건물 가장자리']})
                                       for (p, s), g in F2.groupby(['prior', 'surface'], sort=False)]), '층이 둘인 패치(둘째 창 점 수 >= 첫 창의 절반, 첫 창 4개 이상)')
    if STAGE == 'ga3':
        rows = []
        for (p, s, a), g in F2.groupby(['prior', 'surface', 'ga2_answer'], sort=False):
            r = dict(prior=p, surface=s, ga2=a, area_m2=g.area_m2.sum()); r.update({f'{b} m²': g.area_m2[g.answer == b].sum() for b in FWDX}); rows.append(r)
        write('t3_ga2_to_ga3', pd.DataFrame(rows), '가2 정답(줄) × 가3 정답(칸) 넓이')
        ch = F[F.ga2_answer != F.answer]; rows = []
        for (p, s, a, b), g in ch.groupby(['prior', 'surface', 'ga2_answer', 'answer']):
            r = dict(prior=p, surface=s, ga2=a, ga3=b, patches=len(g), area_m2=g.area_m2.sum()); r.update({f'{pl} %': 100*g.area_m2[g.place == pl].sum()/r['area_m2'] for pl in ['면 안쪽', '면 경계', '건물 가장자리', '자리 없음']}); rows.append(r)
        write('t3b_changed_place', pd.DataFrame(rows).sort_values(['prior', 'area_m2'], ascending=[True, False]), '가2 -> 가3 바뀐 칸의 자리 비율')
    dump(TD/f'checks_{STAGE}.json', rec); progress(f'정답 표 {SUB}: {rec}'); print(rec)
if __name__ == '__main__': main()
