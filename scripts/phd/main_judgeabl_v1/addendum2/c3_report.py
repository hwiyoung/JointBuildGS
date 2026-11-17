"""덧붙임 2 보고서를 표 값으로 만든다. 사용: c3_report.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd
TAB = D/'tables/addendum2'; CN = [CASE[c] for c in CASES]
def f(x, k=1):
    try: x = float(x)
    except (TypeError, ValueError): return str(x)
    return '-' if not np.isfinite(x) else f'{x:.{k}f}'
REP = ['사전 정보 단독', '영상 단독', '본 방법', '패치 다수결 상한', '기존 1 T=0.5 m', '기존 1 T=1 m', '기존 2 대표(저장된 L)', '기존 3 아래 5 %', '기존 5 T=0.5 m', '기존 5 T=L']
def main():
    U = pd.read_csv(TAB/'p_patch_unit.csv'); PC = pd.read_csv(TAB/'p_patch_counts.csv'); G = pd.read_csv(TAB/'p_gap_split.csv'); CK = pd.read_csv(TAB/'p_checks.csv'); M = pd.read_csv(D/'tables/s_main_summary.csv'); FU = pd.read_csv(TAB/'p_fusion3_patch.csv')
    sel = lambda p: U[(U.prior == p) & (U.surface == ('모두' if p == 'LoD2' else '지붕'))].set_index('variant')
    L, A = sel('LoD2'), sel('ALS')
    # 1. 범위
    rng = []
    for _, r in PC.iterrows():
        rng.append(f"{'LoD2' if r.prior == 'LoD2' else '항공 LiDAR'} {r.surface} 참값 있는 패치 {r.patches_with_gt:,}개(네 경우 " + ' / '.join(f"{int(r[f'n_{c}']):,}" for c in CN) + f", 네 경우 밖 {int(r['n_네 경우 밖']):,}, 동률 {int(r['n_동률']):,}, 점 3개 미만 뺌 {int(r['n_점 3개 미만 뺌']):,})")
    # 3. 차례 바뀐 칸 (본 방법과 기존 대표 사이, 경우마다)
    flips = []
    for p, q in [('LoD2', L), ('ALS', A)]:
        for o in [v for v in REP if v.startswith('기존')] + ['사전 정보 단독', '영상 단독']:
            for c in CN:
                dp = q.loc['본 방법', f'point_ok_{c}'] - q.loc[o, f'point_ok_{c}']; dq = q.loc['본 방법', f'patch_ok_{c}'] - q.loc[o, f'patch_ok_{c}']
                if np.sign(dp) != np.sign(dq) and abs(dp) > 1e-9: flips.append(f"{'LoD2' if p == 'LoD2' else '항공 LiDAR'} {c} 본 방법 대 {o}: 점 {f(dp)} %p → 패치 {f(dq)} %p")
    # 4. 원인 나눔 큰 칸
    g0 = G[(G.place == '모든 자리') & (((G.prior == 'LoD2') & (G.surface == '모두')) | (G.prior == 'ALS'))]
    big = []
    for _, r in g0.iterrows():
        k = max(['가', '나', '다'], key=lambda x: r[f'{x}_pct_of_wrong'] if np.isfinite(r[f'{x}_pct_of_wrong']) else -1)
        big.append((r[f'{k}_points'], f"{'LoD2' if r.prior == 'LoD2' else '항공 LiDAR'} {r.variant} {r.case}: 틀린 점 {int(r.wrong_points):,} 가운데 {k} {f(r[f'{k}_pct_of_wrong'])} %"))
    big = [b for _, b in sorted(big, reverse=True)[:6]]
    head = [f"1. **범위**: " + '; '.join(rng) + '. 패치 단위 비율은 넓이 가중(패치 넓이가 같지 않음).',
            f"2. **패치 단위 목표 맞음**(네 경우): LoD2 본 방법 " + ' / '.join(f(L.loc['본 방법', f'patch_ok_{c}']) for c in CN) + ' (점 단위 ' + ' / '.join(f(L.loc['본 방법', f'point_ok_{c}']) for c in CN) + '), 상한 ' + ' / '.join(f(L.loc['패치 다수결 상한', f'patch_ok_{c}']) for c in CN) +
            ' (점 ' + ' / '.join(f(L.loc['패치 다수결 상한', f'point_ok_{c}']) for c in CN) + '). 항공 LiDAR 본 방법 ' + ' / '.join(f(A.loc['본 방법', f'patch_ok_{c}']) for c in CN) + ' (점 ' + ' / '.join(f(A.loc['본 방법', f'point_ok_{c}']) for c in CN) + '), 상한 ' + ' / '.join(f(A.loc['패치 다수결 상한', f'patch_ok_{c}']) for c in CN) + ' (점 ' + ' / '.join(f(A.loc['패치 다수결 상한', f'point_ok_{c}']) for c in CN) + ').',
            f"3. **본 방법과 기존 방법·단독의 앞뒤가 점 단위와 패치 단위에서 뒤바뀐 칸** {len(flips)}개: " + ('; '.join(flips) if flips else '없음') + '.',
            f"4. **원인 나눔의 큰 칸**(점 수 차례): " + '; '.join(big) + '. 가 = 패치 안 섞임, 나 = 자료의 한계, 다 = 판정.',
            "5. **확인 불가와 시간**: 확인 불가 없음. 기존 4는 JUDGEAPPLY 패치에서 따로 셈(`p_fusion3_patch`, 패치 짜임이 다름). 셈 약 4분(표), 그림 약 3분."]
    rows = ['| 판 | LoD2 패치 단위 | LoD2 점 단위 | LoD2 패치 이름 맞음 | 항공 LiDAR 패치 단위 | 항공 LiDAR 점 단위 | 항공 LiDAR 패치 이름 맞음 |', '|---|---|---|---|---|---|---|']
    order = [v for v in M[M.prior == 'LoD2'].variant if v in L.index] + sorted([v for v in L.index if v.startswith('고정 ')], key=lambda v: int(v.split(' ')[1]))
    for v in order:
        c4 = lambda q, k: ' / '.join(f(q.loc[v, f'{k}_{c}']) for c in CN) if v in q.index else '-'
        rows.append(f"| {v} | {c4(L, 'patch_ok')} | {c4(L, 'point_ok')} | {c4(L, 'patch_name')} | {c4(A, 'patch_ok')} | {c4(A, 'point_ok')} | {c4(A, 'patch_name')} |")
    gr = ['| 사전 정보 | 판 | 경우 | 자리 | 틀린 점 | 가 % | 나 % | 다 % | 나의 거리 중앙값·90 % (m) |', '|---|---|---|---|---|---|---|---|---|']
    gg = G[(((G.prior == 'LoD2') & (G.surface == '모두')) | (G.prior == 'ALS'))]
    for _, r in gg.iterrows():
        if r.place != '모든 자리' and not ((r.prior == 'ALS' and r.case == '사전정보 오류') or (r.prior == 'LoD2' and r.case == '영상 깊이 오류')): continue
        gr.append(f"| {'LoD2' if r.prior == 'LoD2' else '항공 LiDAR'} | {r.variant} | {r.case} | {r.place} | {int(r.wrong_points):,} | {f(r['가_pct_of_wrong'])} | {f(r['나_pct_of_wrong'])} | {f(r['다_pct_of_wrong'])} | {f(r['나_dist_q50_m'], 2)}·{f(r['나_dist_q90_m'], 2)} |")
    ck = CK[CK['check'].isna()] if 'check' in CK else CK; eq = int(ck['equal'].astype(str).eq('True').sum()); tot = len(ck)
    up = CK[CK['check'] == '상한 판 패치 판정 이름 맞음'] if 'check' in CK else CK.iloc[:0]
    fu = '; '.join(f"{'LoD2' if p == 'LoD2' else '항공 LiDAR'} " + ' / '.join(f"{int(FU[(FU.prior == p) & (FU.case == c)].patches.sum()):,}" for c in CN) for p in ['LoD2', 'ALS'])
    txt = f"""# 판단 비교·절제 덧붙임 2 보고 v1 — 패치 단위 채점

- PHD-MAIN-JUDGEABL-v1 덧붙임 2. 설정 `configs/phd/main_judgeabl_v1/judgeabl_v1_addendum2.json`(첫 셈 전 잠금). 저장된 판정·목표·점 채점만 읽음(새 판정·새 광도 점수·학습 없음). 참값은 채점에만. scientific_verdict: null.
- 네 경우 = 두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측. LoD2 = 지붕과 벽 합침. 정의: 패치의 경우 = JC 다수결 규칙(동률에 두 자료 모두 유효가 있으면 그것, 다른 동률은 뺌), 참값 점 3개 미만 뺌, 패치 목표 맞음 = 다수 경우 점의 절반 이상이 τ 안.

## 맨 앞 다섯 줄

""" + '\n'.join(head) + f"""

## 표 1. 패치 단위 요약 (목표 맞음 %, 네 경우)

""" + '\n'.join(rows) + f"""

## 표 2. 점 단위가 100 %에 못 미치는 까닭 (틀린 점 가운데 비율)

가 = 점의 경우가 패치의 경우와 다름, 나 = 같은 경우이고 맞는 자료(사전정보 오류 → 영상 단독, 영상 깊이 오류·결측 → 사전 정보 단독, 두 자료 모두 유효 → 둘 다)의 목표도 τ 밖, 다 = 같은 경우이고 맞는 자료는 τ 안인데 이 판이 τ 밖. 자리별은 항공 LiDAR 사전정보 오류와 LoD2 영상 깊이 오류만 싣고 나머지는 `p_gap_split.csv`.

""" + '\n'.join(gr) + f"""

## 그림

| 그림 | 제목 |
|---|---|
| `figures/addendum2/figP1_mixed_patch_ALS.png` | 항공 LiDAR 사전정보 오류 패치 가운데 섞인 것(다수 비율 < 80 %) — 건물 가장자리 둘, 면 안쪽 둘 |
| `figures/addendum2/figP1_mixed_patch_LoD2.png` | LoD2 영상 깊이 오류 패치 가운데 섞인 것 — 같은 짜임(발주가 짚은 다른 칸) |
| `figures/addendum2/figP2_patch_vs_point_*.png` | 판마다 점 단위(원)와 패치 단위(네모) 목표 맞음, 경우마다 |

## 검산, 바꾼 것, 확인 불가

- 점 단위 목표 맞음 = 앞 묶음 `s_all_variants`(판 x 경우 x 면 {tot}칸 가운데 {eq}칸 같음). 경우별 패치 수 + 네 경우 밖 + 동률 + 점 3개 미만 = 참값 있는 패치 수(모든 면 같음, `p_patch_counts` check_sum). 가 + 나 + 다 = 틀린 점 수(모든 칸, `p_gap_split` check_sum).
- 상한 판의 패치 판정 이름 맞음은 100 %가 아님: {'; '.join(f"{r.prior} {int(r.not_equal_patches):,}/{int(r.patches):,} 패치 ({r.why})" for _, r in up.iterrows())}. JC 상한 규칙이 일치인데 u_M이 없으면 사전정보 사용으로, 영상 깊이 사용인데 MVS 높이가 없으면 본 방법 판정으로 두기 때문.
- 고침(덧붙임 2 중 발견): 패치별 판정 파일과 본 표의 바뀐 넓이·바뀐 방향에서 '패치 다수결 상한'의 패치 판정이 본 방법 복사본이었음(JC judge/base 의 oracle 칸). JC `patches_<prior>.npz` oracle_region 으로 고쳐 다시 냄. 점 단위 값은 영향 없음(바뀐 칸은 상한 줄의 changed_area_m2 뿐).
- 기존 4(세 실험 지역)는 JUDGEAPPLY 패치에서 패치 단위로 셈(`p_fusion3_patch`, 네 경우의 패치 수 {fu}).
- 섞인 패치 비율은 `p_mixed`(다수 비율 100 / 80~100 / 50~80 / 50 % 아래, 경우·자리마다).
"""
    (D/'판단비교절제_덧붙임2_보고_v1.md').write_text(txt); print('REPORT', len(txt), 'flips', len(flips))
if __name__ == '__main__': main()
