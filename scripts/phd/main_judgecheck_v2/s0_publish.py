"""단계 0 값의 표: 범위(2.1), τ, r, σ_W, t, 재현 확인, MVS 같은지. 참값 점 수는 조립(s6) 뒤에 채운다."""
from common import *
import pandas as pd
from s7_tables import write
def main():
    cfg(); B = json.loads((O/'stage0/buildings.json').read_text()); rows = [r for r in B['rows'] if r['in_scope']]
    gt = {}
    for prior in ['LoD2', 'ALS']:
        p = O/'analysis'/f'gt_{prior}.npz'
        if p.exists():
            z = loadz(p, ['paired', 'region', 'group', 'patch_kind']); gt[prior] = z
    sc = []
    for prior in ['LoD2', 'ALS']:
        P = []
        for f in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')): P.append(loadz(f, ['region', 'group', 'kind', 'area', 'building']))
        A = {k: np.concatenate([x[k] for x in P]) for k in P[0]}
        for reg in ['전체'] + REGIONS + ['none']:
            for grp in ['전체', 'experiment', 'rest']:
                for kn, kk in ([('지붕', 1), ('벽', 2)] if prior == 'LoD2' else [('지붕', 1)]):
                    m = (A['kind'] == kk) & ((A['region'] == reg) if reg != '전체' else True) & ((A['group'] == grp) if grp != '전체' else True)
                    g = gt.get(prior); gn = None
                    if g is not None: gm = g['paired'] & (g['patch_kind'] == kk) & ((g['region'] == reg) if reg != '전체' else True) & ((g['group'] == grp) if grp != '전체' else True); gn = int(gm.sum())
                    sc.append(dict(prior=prior, search_region=reg, group=grp, surface=kn, buildings=len(set(A['building'][m])), patches=int(m.sum()), area_m2=float(A['area'][m].sum()), gt_points=gn))
    write('s0_scope', pd.DataFrame(sc), note='범위: 탐색 지역 x 묶음 x 사전 정보 x 지붕/벽마다 건물 수, 핵심점(패치) 수, 넓이, 참값 점 수(짝 패치가 있는 점).', md_rows=lambda x: x[(x.search_region == '전체')])
    reg = [dict(region=r['region'] if r['region'] != 'none' else 'none (밖 61동)', buildings=v) for r, v in [(dict(region=k), c) for k, c in B['summary']['region_counts'].items()]]
    write('s0_buildings_per_region', pd.DataFrame(reg), note=f"건물 범위 {B['summary']['in_scope']}동 (LoD2만 있는 {len(B['summary']['LoD2_only'])}동 제외: {', '.join(B['summary']['LoD2_only'])}). 실험 지역 {len(B['summary']['experiment_buildings'])}동.")
    tau = json.loads((O/'stage0/tau.json').read_text()); write('s0_tau', pd.DataFrame(tau['rows']), note='τ = RESCORE-v1 3.1 (지우기 없음 NMAD x 2.5). B0·R2·R1 은 지금 값과 같음: ' + str(all(c['equal'] for c in tau['current_check'])), md_cols=['region', 'key', 'tau_m', 'n'])
    cal = json.loads((O/'calib/base.json').read_text())
    write('s0_r', pd.DataFrame(cal['r_rows']), note=f"r = 일치하는 곳의 d 중앙값 (본값). σ_W = {cal['sigma_W_m']:.5f} m (ALS 지붕 {cal['sigma_W_buildings']}동; 지금 값 {cal['sigma_W_reference_m']:.5f} m). 지역마다 쓴 건물 수: {cal['building_count_by_region']}")
    if (O/'judge/base.json').exists():
        j = json.loads((O/'judge/base.json').read_text()); write('s0_t', pd.DataFrame(j['t_rows']), note='t = 한계 안 사진 점 s_P 의 넓이 가중 아래 5 % (5000개 넘으면 무작위 5000개, 씨앗 20261112).', md_cols=['region', 'prior', 'kind', 't', 't10', 'pool_count', 'sample_count'])
    rp = json.loads((O/'stage0/reproduction.json').read_text()); write('s0_reproduction', pd.DataFrame(rp['rows']).drop(columns=['differing_by_transition', 't_recomputed', 't_JUDGEAPPLY']), note=f"재현 확인 {rp['status']}: 지금 값으로 다시 낸 판정 vs JUDGEAPPLY 핵심점 + 11/4 규칙(FINALTRAIN judge_region), 넓이 비율.",
          md_cols=['site', 'prior', 'patches', 'same_area_share', 'L_max_abs_diff_m', 'geometry_equal_share', 'photo_code_equal_share'])
    mi = json.loads((O/'stage0/mvs_identity.json').read_text()); r2 = []
    for r in mi['rows']:
        for s in r['samples'][:6]: r2.append(dict(site=r['site'], experiment_views=r['experiment_views'], common_with_widen0=r['common_with_widen0'], common_with_discard=r['common_with_discard'], image=s['image'], other=s['other'], equal_share=s.get('equal_share'), median_abs_diff_m=s.get('median_abs_diff_m')))
    write('s0_mvs_identity', pd.DataFrame(r2).drop_duplicates(), note='세 실험 지역 MVS(STAGE0 s61 export)와 WIDEN0 캠퍼스 MVS·DISCARD 탐색 지역 MVS의 같은 영상 깊이 비교. 다른 실행이다.')
    print('S0_PUBLISH done')
if __name__ == '__main__': main()
