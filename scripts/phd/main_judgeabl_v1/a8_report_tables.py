"""보고서에 넣을 요약 표(md 조각)를 표 파일에서 만든다. 손으로 옮기지 않기 위함. 사용: a8_report_tables.py"""
from common import *
import pandas as pd
TAB = D/'tables'; CN = [CASE[c] for c in CASES]
def f(x): return '' if not np.isfinite(x) else f'{x:.1f}'
def main():
    S = pd.read_csv(TAB/'s_main_summary.csv'); out = []
    L = S[S['prior'] == 'LoD2'].set_index('variant'); A_ = S[S['prior'] == 'ALS'].set_index('variant')
    out += ['참값 점 수(네 경우) LoD2 ' + ' / '.join(f"{int(L.iloc[0][f'n_{c}']):,}" for c in CN) + ', 항공 LiDAR ' + ' / '.join(f"{int(A_.iloc[0][f'n_{c}']):,}" for c in CN) + '.', '',
            '| 판 | LoD2 네 경우 | 평균 | 최솟값 | 격차 | 건물 | 항공 LiDAR 네 경우 | 평균 | 최솟값 | 격차 | 건물 |', '|---|---|---|---|---|---|---|---|---|---|---|']
    def cell(q, v):
        if v not in q.index: return ' | | | | '
        r = q.loc[v]; return ' / '.join(f(r[f'ok_{c}']) for c in CN) + f" | {f(r['요약 가 평균'])} | {f(r['요약 나 최솟값'])} | {f(r['요약 다 최대 격차'])} | {f(r['building_diff_median_pp'])}"
    for v in L.index: out.append(f'| {v} | ' + cell(L, v) + ' | ' + cell(A_, v) + ' |')
    W = pd.read_csv(TAB/'s_sweep.csv'); W = W[(((W['prior'] == 'LoD2') & (W['surface'] == '모두')) | (W['prior'] == 'ALS')) & W['gt_selected'].astype(bool)]
    out += ['\n<!-- sweep -->', '| 사전 정보 | 판 | 두 자료 모두 유효 | 사전정보 오류 | 영상 깊이 오류 | 영상 깊이 결측 | 평균 | 최솟값(경우) | 최대 격차 |', '|---|---|---|---|---|---|---|---|---|']
    for _, r in W.iterrows():
        out.append(f"| {r['prior']} | {r['variant']} | " + ' | '.join(f(r[f'ok_{c}']) for c in CN) + f" | {f(r['요약 가 평균'])} | {f(r['요약 나 최솟값'])} ({r['요약 나 경우']}) | {f(r['요약 다 최대 격차'])} |")
    F = pd.read_csv(TAB/'s_fusion3_scope.csv'); F = F[((F['prior'] == 'LoD2') & (F['surface'] == '모두')) | (F['prior'] == 'ALS')]
    F = F[F['variant'].isin(['사전 정보 단독', '영상 단독', '기존 4 결합(세 실험 지역)', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '본 방법', '패치 다수결 상한'])]
    out += ['\n<!-- fusion3 -->', '| 사전 정보 | 판 | 두 자료 모두 유효 | 사전정보 오류 | 영상 깊이 오류 | 영상 깊이 결측 | 전체 |', '|---|---|---|---|---|---|---|']
    for _, r in F.iterrows(): out.append(f"| {r['prior']} | {r['variant']} | " + ' | '.join(f(r[f'ok_{c}']) for c in CN + ['전체']) + ' |')
    if (TAB/'s_fusion_all_scope.csv').exists():   # 5절: 기존 4 결합(전 건물)이 덮은 범위
        F = pd.read_csv(TAB/'s_fusion_all_scope.csv'); F = F[((F['prior'] == 'LoD2') & (F['surface'] == '모두')) | (F['prior'] == 'ALS')]
        F = F[F['variant'].isin(['사전 정보 단독', '영상 단독', '기존 4 결합(전 건물)', '기존 1 T=0.5 m', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '기존 5 T=0.5 m', '본 방법', '패치 다수결 상한'])]
        out += ['\n<!-- fusion_all -->', '| 사전 정보 | 판 | 두 자료 모두 유효 | 사전정보 오류 | 영상 깊이 오류 | 영상 깊이 결측 | 전체 | 참값 점 (네 경우) |', '|---|---|---|---|---|---|---|---|']
        for _, r in F.iterrows(): out.append(f"| {r['prior']} | {r['variant']} | " + ' | '.join(f(r[f'ok_{c}']) for c in CN + ['전체']) + ' | ' + ' / '.join(f"{int(r[f'n_{c}']):,}" for c in CN) + ' |')
    (TAB/'report_fragments.md').write_text('\n'.join(out) + '\n')
if __name__ == '__main__': main()
