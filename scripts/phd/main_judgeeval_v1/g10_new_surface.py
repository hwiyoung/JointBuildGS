"""7.5 사전 정보에 없는 새 면. PHD-MAIN-JUDGEGT-v1 역방향 파일(reverse_<prior>_ga.csv.gz, 세 지역 10동 범위의 영상 쪽 패치)을 다시 씀.
떨어진 영상 쪽 패치 = 가장 가까운 사전 정보 패치에서 옆 0.125 m 밖이거나 법선 10 m 밖. 그 가운데 영상 쪽 패치 기둥(0.25 x 0.25 m, 지붕 ±10 / 벽 ±5 m) 안
법선 거리 0 ± 0.15 m 에 참값 4점 이상 = 실제로 새로 생긴 면(이 발주에서 다시 셈). 패치 하나 = 0.0625 m². 사용: GT_STAGE=ga3 g10_new_surface.py"""
from common import *
import pandas as pd
from g8_score import write
def main():
    c = cfg(); build(); rows = []
    for prior in PRIORS:
        f = Path(c['inputs']['reverse_judgegt'].format(prior=prior))
        if not f.exists(): rows.append(dict(prior=PN[prior], note=f'확인 불가: {f} 없음')); continue
        r = pd.read_csv(f); far = r[r.far.astype(bool)].reset_index(drop=True); n_new = np.zeros(len(far))
        for t, g in far.groupby('tile'):
            ii = g.index.values; H = np.where(g.surface == '벽', 5., 10.); trip = np.full((len(g), 3*KW), np.nan); trip[:, 0] = .15; trip[:, 2] = .15
            ck = run('colk', inp('truth_points', tile=t), np.c_[g[['x', 'y', 'z', 'nx', 'ny', 'nz']].values, np.zeros((len(g), 3)), np.full(len(g), .125), H, trip], f'new_{prior}_{t}'); n_new[ii] = ck[:, 2]
        P = loadz(inp('patches', prior=prior), ['area', 'building']); pa = P['area'][np.isin(P['building'], list(buildings()))].sum()
        for sn, m in [('지붕', far.surface == '지붕'), ('벽', far.surface == '벽'), ('모두', np.ones(len(far), bool))]:
            a_far = far.area_m2[m].sum(); a_new = far.area_m2[m & (n_new >= 4)].sum()
            rows.append(dict(prior=PN[prior], surface=sn, image_side_patches=int(len(r)), far_patches=int(m.sum()), far_m2=a_far, new_surface_m2=a_new, prior_patch_m2=pa, far_pct_of_prior=100*a_far/pa, new_pct_of_prior=100*a_new/pa))
    df = pd.DataFrame(rows); write('t75_new_surface', df, '7.5 사전 정보에 없는 새 면(JUDGEGT-v1 역방향 파일, 참값 0 ± 0.15 m 4점 이상)'); print(df.to_string())
if __name__ == '__main__': main()
