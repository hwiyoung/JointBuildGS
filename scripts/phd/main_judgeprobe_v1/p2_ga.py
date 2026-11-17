"""확인 가 (발주 3절): 한계 밖 패치에서 경우마다 후보 관측의 분포, AUC, 5 % 검정 기각 비율, 둘씩 묶음. 기준은 참값 없이 한계 안 패치에서."""
from common import *
from obs import *
from tables import write
import pandas as pd
QS = [.1, .25, .5, .75, .9]
def run(extra=None, only_region=None):
    cfg(); T = Timer(); D_rows, A_rows, R_rows, P_rows, S_rows, TH_rows = [], [], [], [], [], []
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/f'patch_{prior}.npz', ['kind', 'area', 'region', 'geometry', 'case', 'mixed', 'no_uM', 'place', 'textureless', 'n', 'n10', 'mvs_sd_m', 'u_M', 'fit_nmad', 'fit_count', 'plane_angle', 's_P', 's_M',
                                            'views_P', 'views_M', 'texture_P', 'texture_M', 'mask_P', 'mask_M', 'd_for_check', 'L_m', 'mvs_mean_m', 'mvs_median_m', 'mvs_face_m'])
        o = observations(d)
        if extra is not None and prior in extra: o.update(extra[prior])   # 확인 다 줄 (B0)
        inside = d['geometry'] == 0; outside = d['geometry'] == 1; A = d['area']
        units = [u for u in UNITS if UNITS[u][0] == prior] + (['LoD2_all'] if prior == 'LoD2' else [])
        LO, HI = {}, {}
        for u in [x for x in units if x != 'LoD2_all']:
            um = unit_mask(d, u); lo, hi, th = thresholds(d, o, um, inside)
            for k in o:
                LO.setdefault(k, np.full(len(A), np.nan)); HI.setdefault(k, np.full(len(A), np.nan)); LO[k][um] = lo[k][um]; HI[k][um] = hi[k][um]
            TH_rows += [dict(unit=u, **r) for r in th]
        rej_lo = {k: o[k] < LO[k] for k in o}; rej_hi = {k: o[k] > HI[k] for k in o}
        for u in units:
            um = (d['kind'] > 0) if u == 'LoD2_all' else unit_mask(d, u)
            for ver, vm in [('섞인 패치 뺌', ~d['mixed']), ('섞인 패치 넣음', np.ones(len(A), bool))]:
                if only_region is not None: vm = vm & (d['region'] == only_region)   # 확인 다 5.2: B0 패치만
                grp = {c: um & outside & vm & (d['case'] == c) for c in [0, 1, 2]}
                grp_nou = {c: um & d['no_uM'] & vm & (d['case'] == c) for c in [0, 1, 2]}
                ref = um & inside & (d['case'] == 0) & (np.ones(len(A), bool) if only_region is None else d['region'] == only_region)
                for k, x in o.items():
                    fin = np.isfinite(x)
                    for gname, gm in [('한계 안 두 자료 모두 유효(기준 줄)', ref)] + [(CASE[c], grp[c]) for c in [0, 1, 2]]:
                        m = gm & fin
                        D_rows.append(dict(prior=prior, unit=u, version=ver, obs_no=OBS_NO[k], obs=k, obs_ko=OBS_KO[k], group=gname, n=int(gm.sum()), n_finite=int(m.sum()), area_m2=float(A[gm].sum()), **{f'q{int(q*100)}': wq(x[m], A[m], q) for q in QS}))
                    e = grp[2] & fin; p = grp[1] & fin; v = grp[0] & fin
                    a1 = wauc(x[e], A[e], x[p], A[p]); a2 = wauc(x[e], A[e], x[v], A[v])
                    A_rows.append(dict(prior=prior, unit=u, version=ver, obs_no=OBS_NO[k], obs=k, obs_ko=OBS_KO[k], auc_imgerr_vs_priorerr=a1, auc_imgerr_vs_bothvalid=a2, key=np.nanmean([abs(a1 - .5), abs(a2 - .5)]),
                                       n_imgerr=int(e.sum()), n_priorerr=int(p.sum()), n_bothvalid=int(v.sum())))
                    if u == 'LoD2_all': continue
                    for tgt, G in [('한계 밖', grp), ('u_M 없음', grp_nou)]:
                        for c in [0, 1, 2]:
                            gm = G[c]; a = A[gm].sum()
                            R_rows.append(dict(prior=prior, unit=u, version=ver, target=tgt, obs_no=OBS_NO[k], obs=k, obs_ko=OBS_KO[k], case=CASE[c], n=int(gm.sum()), area_m2=float(a), finite_pct=100*A[gm & fin].sum()/a if a else np.nan,
                                               low_reject_pct=100*A[gm & rej_lo[k]].sum()/a if a else np.nan, high_reject_pct=100*A[gm & rej_hi[k]].sum()/a if a else np.nan,
                                               reject_pct=100*A[gm & (rej_lo[k] | rej_hi[k])].sum()/a if a else np.nan))
                if u == 'LoD2_all' or ver != '섞인 패치 뺌': continue
                # 둘씩 묶음
                aa = pd.DataFrame([r for r in A_rows if r['unit'] == u and r['version'] == ver and r['prior'] == prior and r['obs'] != 'd_over_L']).sort_values('key', ascending=False)   # 검출 통계 뺌
                top = list(aa['obs'][:5])
                for i in range(5):
                    for j in range(i + 1, 5):
                        k1, k2 = top[i], top[j]; rj = rej_lo[k1] | rej_hi[k1] | rej_lo[k2] | rej_hi[k2]
                        for c in [0, 1, 2]:
                            gm = grp[c]; a = A[gm].sum(); P_rows.append(dict(prior=prior, unit=u, pair=f'{OBS_NO[k1]}+{OBS_NO[k2]}', obs_a=k1, obs_b=k2, case=CASE[c], n=int(gm.sum()), reject_pct=100*A[gm & rj].sum()/a if a else np.nan))
                # 자리·무늬 없음 나눔
                for sname, smask in [(f'자리 {v}', d['place'] == kk) for kk, v in PLACE.items()] + [('무늬 없음', d['textureless'] == 1), ('무늬 있음', d['textureless'] == 0)]:
                    for k, x in o.items():
                        fin = np.isfinite(x); e = grp[2] & smask & fin; p = grp[1] & smask & fin; v = grp[0] & smask & fin
                        row = dict(prior=prior, unit=u, split=sname, obs_no=OBS_NO[k], obs=k, auc_imgerr_vs_priorerr=wauc(x[e], A[e], x[p], A[p]), auc_imgerr_vs_bothvalid=wauc(x[e], A[e], x[v], A[v]))
                        for c in [0, 1, 2]:
                            gm = grp[c] & smask; a = A[gm].sum(); row[f'n_{c}'] = int(gm.sum()); row[f'reject_pct_{CASE[c]}'] = 100*A[gm & (rej_lo[k] | rej_hi[k])].sum()/a if a else np.nan
                        S_rows.append(row)
        print('GA', prior, round(T.s()), flush=True)
    sfx = '' if extra is None else f'_{only_region}_mvs_views'
    note = '확인 가. 대상 = 한계 밖 패치(기하 코드 1), 패치의 경우 = 참값 점 다수 경우, 섞인 패치 = 다수 비율 < 80 %. 넓이 가중. 기준 = 한계 안 패치(참값 없음) 탐색 지역 x 단위의 넓이 가중 5 %·95 %.'
    dfA = pd.DataFrame(A_rows)
    # 11-17 사용자 결정(뒤에 바꿈): 13 |d|/L 은 검출 통계라 순위에서 뺌(표에는 남김). 광도 점수(7, 8, 9)를 뺀 순위도 함께.
    dfA['detection_statistic'] = dfA['obs'] == 'd_over_L'; dfA['photometric'] = dfA['obs'].isin(['s_P', 's_M', 'sM_minus_sP'])
    dfA['rank'] = dfA['key'].where(~dfA['detection_statistic']).groupby([dfA['prior'], dfA['unit'], dfA['version']]).rank(ascending=False, method='first')
    dfA['rank_no_photo'] = dfA['key'].where(~dfA['detection_statistic'] & ~dfA['photometric']).groupby([dfA['prior'], dfA['unit'], dfA['version']]).rank(ascending=False, method='first')
    write('ga_auc' + sfx, dfA.sort_values(['prior', 'unit', 'version', 'rank']), note=note, md_filter=lambda x: x[x['version'] == '섞인 패치 뺌'][['unit', 'rank', 'rank_no_photo', 'obs_no', 'obs_ko', 'auc_imgerr_vs_priorerr', 'auc_imgerr_vs_bothvalid', 'n_imgerr', 'n_priorerr', 'n_bothvalid']])
    write('ga_distribution' + sfx, pd.DataFrame(D_rows), note=note, md_filter=lambda x: x[(x['version'] == '섞인 패치 뺌') & (x['unit'] != 'LoD2_all')][['unit', 'obs_no', 'obs_ko', 'group', 'n', 'q10', 'q25', 'q50', 'q75', 'q90']])
    write('ga_reject' + sfx, pd.DataFrame(R_rows), note=note + ' 기각 = 기준 밖(아래 5 % 또는 위 5 %). u_M 없음 줄은 기하 검사를 건너뛴 패치.', md_filter=lambda x: x[(x['version'] == '섞인 패치 뺌')][['unit', 'target', 'obs_no', 'obs_ko', 'case', 'n', 'low_reject_pct', 'high_reject_pct', 'reject_pct']])
    write('ga_pairs' + sfx, pd.DataFrame(P_rows), note=note + ' 단위마다 구별 정도 큰 다섯(13 |d|÷L 뺌)의 둘씩 묶음, 하나라도 기각이면 기각. 섞인 패치 뺌.')
    write('ga_splits' + sfx, pd.DataFrame(S_rows), note=note + ' 자리·무늬 없음 나눔, 섞인 패치 뺌.')
    write('ga_thresholds' + sfx, pd.DataFrame(TH_rows), note='후보 관측의 기준 (한계 안 패치, 참값 없음).')
    progress(f'확인 가{sfx} 표 끝 ({round(T.s())} 초)')
if __name__ == '__main__': run()
