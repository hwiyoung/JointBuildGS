"""확인 라 (발주 6절) + 다시 셀 것 6: 최소 검출 오류 MDE = 2.80 sqrt(u_M^2 + sigma_P^2 + sigma_W^2) + |r| (유의 5 %, 검정력 80 %).
'한계 안 일치' 진짜 판정 오류 점(JC 6.3): 본 방법 판정 일치(한계 안), 경우 1·2·4, 목표 τ 밖."""
from common import *
from tables import write
import pandas as pd
QS = [.1, .25, .5, .75, .9]
def main():
    cfg(); T = Timer(); tau = json.loads((JC/'stage0/tau.json').read_text())['values']; ROWS, PT, R6, R6X = [], [], [], []
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/f'patch_{prior}.npz', ['kind', 'area', 'region', 'place', 'u_M', 'sigma_P', 'sigma_W', 'r_m', 'L_m', 'geometry', 'mixed', 'case'])
        mde = 2.80*np.sqrt(d['u_M']**2 + d['sigma_P']**2 + d['sigma_W']**2) + np.abs(d['r_m'])
        key = np.where(d['kind'] == 2, f'{prior}_wall', f'{prior}_roof'); tv = np.array([tau.get(r if r in tau else 'none', tau['none'])[k] for r, k in zip(d['region'], key)])
        savez(O/f'ra_{prior}.npz', mde=mde, tau=tv)
        for u in [x for x in UNITS if UNITS[x][0] == prior]:
            um = d['kind'] == UNITS[u][1]
            for pn, pm in [('모든 자리', np.ones(len(um), bool))] + [(v, d['place'] == k) for k, v in PLACE.items()]:
                for gn, gm in [('모든 패치', np.ones(len(um), bool)), ('한계 안', d['geometry'] == 0), ('한계 밖', d['geometry'] == 1)]:
                    m = um & pm & gm & np.isfinite(mde); a = d['area'][m]
                    ROWS.append(dict(prior=prior, unit=u, place=pn, patches=gn, n=int(m.sum()), n_no_mde=int((um & pm & gm & ~np.isfinite(mde)).sum()), **{f'mde_q{int(q*100)}': wq(mde[m], a, q) for q in QS},
                                     tau_q50=wq(tv[m], a, .5), area_mde_gt_tau_pct=100*a[mde[m] > tv[m]].sum()/a.sum() if a.sum() else np.nan))
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 's_P', 's_M', 'tau', 'target_ok_v', 'region_v', 'patch_kind'])
        mi = J.VARIANTS.index('method'); pa = g['paired']; gid = np.maximum(g['gid'], 0)
        err = pa & (g['region_v'][mi] == 0) & np.isin(g['case'], [1, 2, 4]) & ~g['target_ok_v'][mi] & (d['geometry'][gid] == 0)
        diff = np.abs(g['s_P'] - g['s_M'])
        for u in [x for x in UNITS if UNITS[x][0] == prior]:
            for c in [1, 2, 4, 'all']:
                for mn, mm in [('섞인 패치', d['mixed'][gid]), ('섞이지 않은 패치', ~d['mixed'][gid]), ('모두', np.ones(len(pa), bool))]:
                    m = err & (g['patch_kind'] == UNITS[u][1]) & mm & (np.isin(g['case'], [1, 2, 4]) if c == 'all' else (g['case'] == c)); fin = m & np.isfinite(diff) & np.isfinite(mde[gid])
                    PT.append(dict(prior=prior, unit=u, case='세 경우' if c == 'all' else CASE[c], mixed=mn, n=int(m.sum()), n_finite=int(fin.sum()), below_mde_pct=100*(diff[fin] < mde[gid][fin]).mean() if fin.any() else np.nan,
                                   diff_q50=float(np.median(diff[fin])) if fin.any() else np.nan, mde_q50=float(np.median(mde[gid][fin])) if fin.any() else np.nan))
                    # 다시 셀 것 6: L / τ
                    lt = d['L_m'][gid]/g['tau']; f2 = m & np.isfinite(lt)
                    R6.append(dict(prior=prior, unit=u, case='세 경우' if c == 'all' else CASE[c], mixed=mn, n=int(m.sum()), **{f'L_over_tau_q{int(q*100)}': float(np.quantile(lt[f2], q)) if f2.any() else np.nan for q in QS},
                                   L_gt_tau_pct=100*(lt[f2] > 1).mean() if f2.any() else np.nan))
            m = err & (g['patch_kind'] == UNITS[u][1]); lt = d['L_m'][gid]/g['tau']
            for a in [True, False]:
                for b in [True, False]:
                    mm = m & ((lt > 1) == a) & (d['mixed'][gid] == b); R6X.append(dict(prior=prior, unit=u, L_gt_tau=a, mixed_patch=b, n=int(mm.sum()), pct=100*mm.sum()/max(m.sum(), 1)))
        print('RA', prior, round(T.s()), int(err.sum()), flush=True)
    note = '확인 라. MDE = 2.80 x sqrt(u_M^2 + σ_P^2 + σ_W^2) + |r| (패치마다), τ = 그 패치 탐색 지역의 τ. 넓이 가중.'
    write('ra_mde', pd.DataFrame(ROWS), note=note, md_filter=lambda x: x[x['patches'] == '모든 패치'][['unit', 'place', 'n', 'mde_q10', 'mde_q25', 'mde_q50', 'mde_q75', 'mde_q90', 'tau_q50', 'area_mde_gt_tau_pct']])
    write('ra_inside_agree_errors', pd.DataFrame(PT), note=note + " '한계 안 일치' 진짜 판정 오류 점에서 참값 거리 차이 |s_P − s_M| 이 패치 MDE 보다 작은 점의 비율. 섞인 패치 = 발주 0.3 정의(다수 비율 < 80 %). 영상 깊이 결측은 s_M 이 없어 n_finite 0.")
    write('rc6_L_over_tau', pd.DataFrame(R6), note="다시 셀 것 6: '한계 안 일치' 진짜 판정 오류 점의 패치 L ÷ τ.")
    write('rc6_cross', pd.DataFrame(R6X), note='다시 셀 것 6: L > τ 와 섞인 패치의 교차표 (세 경우 합).')
    progress(f'확인 라·다시 셀 것 6 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
