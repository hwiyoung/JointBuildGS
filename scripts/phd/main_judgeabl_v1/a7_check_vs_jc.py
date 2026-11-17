"""8절 검산: 본 방법·사전 정보 단독·영상 단독·상한의 경우별 목표 맞음과 참값 점 수가 JC c1_case_summary(전체, 모든 자리)와 같은가. 표만 읽음."""
from common import *
import pandas as pd
M = {'본 방법': '본 방법', '사전 정보 단독': '사전 정보 단독', '영상 단독': '영상 단독', '패치 다수결 상한': '정답 판정'}
def main():
    S = pd.read_csv(D/'tables/s_all_variants.csv'); S = S[S['scope'] == '전체'].set_index(['prior', 'surface', 'variant']); rows = []
    for p in ['LoD2', 'ALS']:
        c = pd.read_csv(R/f'docs/experiments/phd/main_judgecheck_v2/tables/c1_case_summary_{p}.csv'); c = c[(c['group'] == '전체') & (c['place'] == '모든 자리') & c['variant'].isin(M.values())]
        for r in c.itertuples():
            v = [k for k, x in M.items() if x == r.variant][0]; m = S.loc[(p, r.surface, v)]
            rows.append(dict(prior=p, surface=r.surface, variant=v, case=r.case, mine=m[f'ok_{r.case}'], JC=r.target_ok_pct, n=r.n, equal=bool(abs(m[f'ok_{r.case}'] - r.target_ok_pct) < 1e-9 and int(m[f'n_{r.case}']) == r.n)))
    df = pd.DataFrame(rows); df.to_csv(D/'tables/s_check_baselines_vs_JC.csv', index=False); print('CHECK_JC', len(df), int(df['equal'].sum())); progress(f'8절 검산: JC 와 같은 칸 {int(df["equal"].sum())}/{len(df)}')
if __name__ == '__main__': main()
