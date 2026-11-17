"""다시 셀 것 1~4 (발주 7절). 참값은 경우·목표 맞음에만."""
from common import *
from tables import write
import pandas as pd
THREE = ['4959460', '4906982', '4907509']
def main():
    cfg(); T = Timer(); R1, R2, R3, R4 = [], [], [], []
    cl = pd.read_csv(JC/'analysis/clusters.csv', usecols=['cluster_id', 'prior', 'building', 'geometry_type', 'member_rows', 'area_m2'], dtype=str, low_memory=False)
    for prior in ['LoD2', 'ALS']:
        g = loadz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 's_P', 's_M', 'tau', 'target_ok_v', 'target_distance_v', 'region_v', 'patch_kind', 'building', 'surf', 'face', 'photo_code', 'cell'])
        d = loadz(O/f'patch_{prior}.npz', ['nsel_P', 'nsel_M']); pa = g['paired']; gid = np.maximum(g['gid'], 0); mi = J.VARIANTS.index('method')
        fk = g['surf'] if prior == 'LoD2' else g['face']
        # 1. 지붕 면마다 두 자료 모두 유효 점의 s_P, s_M 중앙값
        same = cl[(cl['prior'] == prior) & (cl['geometry_type'] == '두 자료가 같은 쪽으로 어긋남') & cl['member_rows'].notna()]
        flag = {}
        for r in same.itertuples():
            rows = np.array([int(x) for x in str(r.member_rows).split(',') if x.strip() != ''])
            rows = rows[(rows >= 0) & (rows < len(pa))]
            for b, f in set(zip(g['building'][rows], fk[rows])): flag.setdefault((b, int(f)), []).append(int(r.cluster_id))
        m = pa & (g['case'] == 0) & (g['patch_kind'] == 1)
        df = pd.DataFrame(dict(building=g['building'][m], face=fk[m], s_P=g['s_P'][m], s_M=g['s_M'][m]))
        agg = df.groupby(['building', 'face']).agg(n=('s_P', 'size'), s_P_median=('s_P', 'median'), s_M_median=('s_M', 'median')).reset_index()
        agg['prior'] = prior; agg['three_buildings'] = agg['building'].apply(lambda b: any(b.endswith(x) for x in THREE))
        agg['same_side_clusters'] = [','.join(map(str, flag.get((b, int(f)), []))) for b, f in zip(agg['building'], agg['face'])]
        R1.append(agg)
        # 2. τ 의 0.8~1.2 배 띠 빼기
        band = pa & (((np.abs(g['s_P']) >= .8*g['tau']) & (np.abs(g['s_P']) <= 1.2*g['tau'])) | ((np.abs(g['s_M']) >= .8*g['tau']) & (np.abs(g['s_M']) <= 1.2*g['tau'])))
        for sn, sm in ({'지붕': g['patch_kind'] == 1, '벽': g['patch_kind'] == 2, '모두': np.ones(len(pa), bool)} if prior == 'LoD2' else {'지붕': g['patch_kind'] == 1}).items():
            for vn, j in [('본 방법', 4), ('사전 정보 단독', 0), ('영상 단독', 1), ('패치 다수결 상한', 7)]:
                for c in [0, 1, 2, 4]:
                    a = pa & sm & (g['case'] == c); b = a & ~band
                    R2.append(dict(prior=prior, surface=sn, variant=vn, case=CASE[c], n_all=int(a.sum()), target_ok_all_pct=100*g['target_ok_v'][j][a].mean() if a.any() else np.nan,
                                   n_band_dropped=int(b.sum()), target_ok_band_dropped_pct=100*g['target_ok_v'][j][b].mean() if b.any() else np.nan, band_share_pct=100*(a & band).sum()/max(a.sum(), 1)))
        # 3. LoD2 두 자료 모두 유효, 영상 깊이 사용, 목표 τ 밖: 원통 높이 면까지 거리 - s_M
        if prior == 'LoD2':
            m = pa & (g['case'] == 0) & (g['region_v'][mi] == 2) & ~g['target_ok_v'][mi]
            diff = g['target_distance_v'][mi][m] - g['s_M'][m]; tv = g['tau'][m]; f = np.isfinite(diff)
            for sn, sk in [('지붕', 1), ('벽', 2), ('모두', None)]:
                ss = f & ((g['patch_kind'][m] == sk) if sk else True)
                R3.append(dict(prior=prior, surface=sn, n=int(((g['patch_kind'][m] == sk) if sk else np.ones(m.sum(), bool)).sum()), n_finite=int(ss.sum()), **{f'diff_q{q}': float(np.quantile(diff[ss], q/100)) if ss.any() else np.nan for q in [10, 25, 50, 75, 90]},
                               abs_diff_gt_tau_pct=100*(np.abs(diff[ss]) > tv[ss]).mean() if ss.any() else np.nan))
        # 4. 사진 부족: 어느 쪽 사진이 모자랐나
        short = pa & (g['photo_code'] == 7); sp = d['nsel_P'][gid] < 3; sM = d['nsel_M'][gid] < 3
        for sn, sk in ([('지붕', 1), ('벽', 2)] if prior == 'LoD2' else [('지붕', 1)]):
            for c in [0, 1, 2, 4]:
                base = pa & (g['case'] == c) & (g['patch_kind'] == sk); tot = short & base
                for side, sm_ in [('사전 정보 면만', sp & ~sM), ('영상 깊이 면만', ~sp & sM), ('둘 다', sp & sM)]:
                    m = tot & sm_
                    R4.append(dict(prior=prior, surface=sn, case=CASE[c], short_side=side, n=int(m.sum()), area_m2=float(len(np.unique(g['cell'][m]))*0.0625), pct_of_case=100*m.sum()/max(base.sum(), 1), pct_of_shortage=100*m.sum()/max(tot.sum(), 1)))
        print('RC', prior, round(T.s()), flush=True)
    r1 = pd.concat(R1).sort_values(['three_buildings', 'prior', 'building', 'n'], ascending=[False, True, True, False])
    write('rc1_roof_faces', r1, note='다시 셀 것 1: 지붕 면(LoD2 surf, 항공 LiDAR = JC 자리 면)마다 두 자료 모두 유효 참값 점의 s_P, s_M 중앙값(m). same_side_clusters = 그 면에 참값 점이 놓인 "두 자료가 같은 쪽으로 어긋남" 모임 번호(JC clusters.csv).',
          md_filter=lambda x: x[x['three_buildings']][['prior', 'building', 'face', 'n', 's_P_median', 's_M_median', 'same_side_clusters']])
    write('rc2_band_drop', pd.DataFrame(R2), note='다시 셀 것 2: |s_P| 또는 |s_M| 이 τ 의 0.8~1.2 배인 참값 점을 뺀 목표 맞음 %.')
    write('rc3_cylinder_vs_surface', pd.DataFrame(R3), note='다시 셀 것 3: LoD2 두 자료 모두 유효·영상 깊이 사용·목표 τ 밖 점에서 (원통 높이 목표 면까지 거리 − 영상 깊이 면까지 거리 s_M), m.')
    write('rc4_photo_shortage', pd.DataFrame(R4), note='다시 셀 것 4: 광도 결과 사진 부족(고른 사진 < 3) 참값 점을 모자란 쪽으로 나눔. 넓이 = 0.25 m 칸 x 0.0625 m2.')
    progress(f'다시 셀 것 1~4 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
