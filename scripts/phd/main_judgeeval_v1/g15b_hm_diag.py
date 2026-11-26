"""덧붙임 1 보고 다 1절 '목표 높이 값의 영향'과 2절 'h_T 없음' 넓이(채점용 진단, 판단 안 바꿈).
정답 영상·판 4 판정 영상 패치에서 h_M 후보마다 목표 맞음 넓이 %, 판마다 채점 안 넓이 가운데 h_T 없음 넓이. 사용: GT_STAGE=ga3 g15b_hm_diag.py"""
from common import *
import pandas as pd
def main():
    rows = []
    for p in PRIORS:
        F = loadz(O/'work'/STAGE/f'judge4_{p}.npz'); H = loadz(O/'work'/STAGE/f'heights_{p}.npz'); a = loadz(inp('patches', prior=p), ['area', 'kind']); ar = a['area'][F['patch_index']]; k = a['kind'][F['patch_index']]
        t = F['answer']; inm = np.isin(t, [0, 1, 2, 3]); nm = [str(x) for x in H['names']]
        for pl in ['판 4', '상한: ①만 정답', '판 4(가장 나은 후보)']: rows.append(dict(kind='h_T 없음', prior=PN[p], surface='모두', item=pl, area_m2=float(ar[inm & ~np.isfinite(F[f'hT_{pl}'])].sum()), value=np.nan))
        for kk, sn in [(1, '지붕'), (2, '벽')]:
            m = inm & (t == 1) & (F['J4_판 4'] == 1) & (k == kk)
            if not m.any(): continue
            for h in ['d_mean_2', 'd_med_2', 'd_mean_0', 'd_med_0', 'cur', 'hM3c']: rows.append(dict(kind='정답 영상·판정 영상: 높이 후보의 목표 맞음 %', prior=PN[p], surface=sn, item=h, area_m2=float(ar[m].sum()), value=100*ar[m & H['ok'][:, nm.index(h)]].sum()/ar[m].sum()))
    df = pd.DataFrame(rows); df.to_csv(D/'tables/다/t2_hm_candidates.csv', index=False); print(df.to_string())
if __name__ == '__main__': main()
