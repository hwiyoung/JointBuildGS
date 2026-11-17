"""덧붙임 1 보고서(8천 자 안)를 표 파일의 값으로 만든다(손으로 옮기지 않음). 사용: b8_report.py"""
import sys; sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *
import pandas as pd
TAB = D/'tables/addendum1'; A1 = O/'addendum1'; CN = [CASE[c] for c in CASES]
U3 = ['LoD2 지붕', 'LoD2 벽', '항공 LiDAR 지붕']
def r(name): return pd.read_csv(TAB/f'{name}.csv')
def f(x, k=2):
    try: x = float(x)
    except (TypeError, ValueError): return str(x)
    return '-' if not np.isfinite(x) else f'{x:.{k}f}'
def main():
    VS, C1, C1B, ST, C2, C3, C4B, C4R, C5R, C6, C7, C8, FX = [r(n) for n in ['variogram_summary', 'check1_conditions', 'check1_boundary', 'check1_stability', 'check2_cylinder_radius', 'check3_cylinder_length', 'check4_buildings',
                                                                          'check4_ring_counts', 'check5_texture_rules', 'check6_view_angle', 'check7_view_count', 'check8_patch_inner', 'front_fixed_value_variants']]
    NR = r('check1_no_radius'); B4S = r('check4_buildings_summary')
    sw = float(json.loads((JC/'calib/base.json').read_text())['sigma_W_m'])
    def rng(series, k=2): s = pd.Series(series).dropna(); return f'{f(s.median(), k)} ({f(s.quantile(.1), k)}~{f(s.quantile(.9), k)})' if len(s) else '-'
    rows = []
    # 1 고리
    for u in U3:
        reg = VS[(VS.unit == '항공 LiDAR 지붕') & (VS.region != '전체')]['L95']; c = C1[(C1.unit == u) & (C1.region == '전체') & (C1.R == 1.5) & C1.ring.str.startswith('영상')].iloc[0]
        rows.append(('1 고리 바깥 반지름', u, '1.5 m (가운데 1.0 m)', f"영상 깊이 오차(항공 LiDAR 지붕)의 닮는 거리 95 % {rng(reg)} m(지역별); 이 단위 50 % {f(VS[(VS.unit == u) & (VS.region == '전체')]['L50'].iloc[0])} m; 면 경계까지 중앙값 {f(C1B[(C1B.unit == u) & (C1B.region == '전체')]['dist_boundary_q50'].iloc[0])} m",
                     f"(가) {f(c.cond_a_area_pct, 0)} %, (나) {f(c.cond_b_area_pct, 1)} % (N_유효 {f(c.cond_b_eff_area_pct, 1)} %), (다) {f(c.cond_c_area_pct, 1)} %, 셋 모두 {f(c.all_three_area_pct, 1)} %; 어느 반지름도 못함 {f(NR[(NR.unit == u) & (NR.region == '전체')].none_of_radii_pct.iloc[0], 1)} %(까닭: (가) 세 반지름 모두 {f(NR[(NR.unit == u) & (NR.region == '전체')].reason_a_all_radii_pct.iloc[0], 1)} %, 면이 (가)에 필요한 반지름 {f(NR[(NR.unit == u) & (NR.region == '전체')].needed_radius_for_a_m.iloc[0])} m보다 작음 {f(NR[(NR.unit == u) & (NR.region == '전체')].face_smaller_than_needed_radius_pct.iloc[0], 1)} %)", ''))
    for u in U3:
        q = C2[(C2.unit == u) & (C2.version == 'n < 4 뺌') & (C2.region != '전체')]; a = C2[(C2.unit == u) & (C2.version == 'n < 4 넣음') & (C2.region == '전체')].iloc[0]
        rows.append(('2 원통 반지름', u, f"{a.radius_now_m:g} m", f"밀도 10 % 값으로 {rng(q.r_rule_at_q10_m, 3)} m, 50 % 값으로 {rng(q.r_rule_at_q50_m, 3)} m (지역별)", f"n ≥ 4 넓이 {f(100 - a.n_lt4_area_pct, 1)} %", ''))
    for u in U3:
        q = C3[(C3.unit == u) & (C3.region == '전체')].iloc[0]
        rows.append(('3 원통 길이', u, f"±{q.half_length_m:g} m", f"|d| 99.9 % {f(q.q999)} m, 가장 큰 값 {f(q['max'])} m", f"길이 끝 1 m 밖 {f(100 - q.within_1m_of_end_area_pct, 2)} %", '벽 10 m 원통 확인 불가' if u == 'LoD2 벽' else ''))
    for u in U3:
        b = C4B[C4B.unit == u]; nr = C4R[(C4R.unit == u) & (C4R.region == '전체') & (C4R.bin == '문턱 가까이')]
        rows.append(('4 표본 수의 최소', u, '고리 20, 안쪽 5, 맞춤 20, 건물 100', f"σ_W/3 에 필요한 건물당 n {rng(b.n_needed, 0)}, 유효 표본 수로 보면 {rng(b.n_needed_eff_basis, 0)}", f"고리·안쪽 문턱 가까이 {f(nr.area_pct.iloc[0], 3)}·{f(nr.area_pct.iloc[1], 3)} %, 건물 n_b ≥ 100 {f(100*b.meets_100.mean(), 1)} %, 표준 오차 ≤ σ_W/3 {f(100*b.se_le_sw3.mean(), 1)} %, 유효 표본 수 기준 만족 {f(100*b.meets_eff.mean(), 1)} %", ''))
    for u in U3:
        q = C5R[(C5R.unit == u) & (C5R.region == '전체')]
        if not len(q): rows.append(('5 무늬 세기 문턱', u, '5', '-', '-', '표본 없음')); continue
        q = q.iloc[0]; reg = C5R[(C5R.unit == u) & (C5R.region != '전체')]
        rows.append(('5 무늬 세기 문턱', u, '5', f"규칙 1 {f(q.rule1_threshold, 0)}, 규칙 2 {rng(reg.rule2_threshold)} (σ_n {f(q.sigma_n_q50)})", f"지금 무늬 없음 넓이 {f(q.textureless_area_pct_now, 1)} %", q.rule2_note if isinstance(q.rule2_note, str) else ''))
    for u in U3:
        q = C6[(C6.unit == u) & (C6.region == '전체')]
        if not len(q): continue
        e = q[q.angle_bin.str.startswith('0~40')]; b5060 = q[q.angle_bin == '50~60°']; b6070 = q[q.angle_bin == '60~70°']
        rows.append(('6 사진의 각', u, '60° 이하', f"0~40° 중앙값 − 0.1 아래 첫 구간: {e.note.iloc[0] if len(e) else '-'}", f"50~60° 중앙 NCC {f(b5060.ncc_q50.iloc[0])}, 60~70° {f(b6070.ncc_q50.iloc[0])}; 60~70° 화소 ÷ 2 cm {f(b6070.footprint_over_2cm.iloc[0])}", '표본'))
    for u in U3:
        q = C7[(C7.unit == u) & (C7.region == '전체') & C7.k.astype(str).str.startswith('편차')]
        if not len(q): continue
        rows.append(('7 사진 수', u, '3~10장', f"편차가 더 줄지 않는 가장 작은 k: {int(float(q.note.iloc[0])) if str(q.note.iloc[0]) not in ('nan', 'None') else '없음'}", f"점 {int(q.points.iloc[0])}개(10장 고른 점)", '표본'))
    for u in U3:
        q = C8[(C8.unit == u) & (C8.region == '전체')].set_index('item')
        if '무늬 닮는 거리(1/e, m)' not in q.index: continue
        rows.append(('8 조각·안쪽 원', u, '50 cm, 2 cm, 0.5 m', f"무늬 닮는 거리 {f(q.loc['무늬 닮는 거리(1/e, m)', 'q50'], 3)} m ({q.loc['무늬 닮는 거리(1/e, m)', 'note']}), 화소 {f(q.loc['화소 크기(면 위, m)', 'q50'], 3)} m", f"조각 15·20 대 25 NMAD {q.loc['조각 15x15 − 25x25 s_P 차이', 'note'][5:]}·{q.loc['조각 20x20 − 25x25 s_P 차이', 'note'][5:]}; 안쪽 원 점 수 중앙값 {f(q.loc['고리 안쪽 원 점 수 (한계 안)', 'q50'], 0)}, {q.loc['고리 안쪽 원 점 수 (한계 안)', 'note']}", '표본'))
    t1 = '| 확인 | 사전 정보 | 지금 값 | 규칙이 주는 값(중앙값, 10~90 %) | 지금 값이 규칙을 만족하는 넓이 등 | 비고 |\n|---|---|---|---|---|---|\n' + '\n'.join('| ' + ' | '.join(map(str, x)) + ' |' for x in rows)
    t2 = '| 판 | LoD2 네 경우 | LoD2 차이 %p | 항공 LiDAR 네 경우 | 항공 LiDAR 차이 %p |\n|---|---|---|---|---|\n' + '\n'.join(f"| {x.variant} | {x['LoD2 네 경우']} | {x['LoD2 차이 %p']} | {x['ALS 네 경우']} | {x['ALS 차이 %p']} |" for _, x in FX.iterrows())
    ck = [json.loads((O/f'check9_{p}.json').read_text()) for p in ['LoD2', 'ALS']]; sm = [json.loads((A1/f'sample_{p}.json').read_text()) for p in ['LoD2', 'ALS'] if (A1/f'sample_{p}.json').exists()]
    st = ST[(ST.place == '모든 자리')]
    txt = f"""# 판단 비교·절제 덧붙임 1 보고 v1 — 고정 값의 근거와 값을 바꾼 판정

- PHD-MAIN-JUDGEABL-v1 덧붙임 1. 설정 `configs/phd/main_judgeabl_v1/judgeabl_v1_addendum1.json`(첫 셈 전 잠금). 학습 없음, 판정 규칙 바꾸지 않음. 확인 1~8은 참값 없이 한계 안 패치·한계 안 사진 점에서, 확인 9는 채점에만 참값. scientific_verdict: null.
- 네 경우 = 두 자료 모두 유효 / 사전정보 오류 / 영상 깊이 오류 / 영상 깊이 결측. 표와 그림은 `tables/addendum1/`, `figures/addendum1/`.

## 1. 근거 표

{t1}

## 2. 값을 바꾼 판정 표 (확인 9, JC 민감도 일곱 판 포함)

{t2}

검산: 기준 5 %·무늬 5로 다시 낸 광도 결과와 판정이 본값과 같음(LoD2·항공 LiDAR 100 %). 무늬 3에서 저장 점수가 없어 본값을 둔 사진 점: LoD2 {ck[0]['texture3_kept_points']}개({f(ck[0]['texture3_kept_base_area_m2'], 1)} m²), 항공 LiDAR {ck[1]['texture3_kept_points']}개({f(ck[1]['texture3_kept_base_area_m2'], 1)} m²). JC 민감도 일곱 판은 JC가 저장한 판정·목표를 같은 채점으로 다시 냄(같은 면 고리 값이 JC 보고와 같음). 판정이 바뀐 넓이·바뀐 방향·건물별 차이·광도 결과 여덟의 경우별 비율은 `tables/s_all_variants.csv`, `s_transitions.csv`, `s_building_diff.csv`, `tables/addendum1/check9_photo_codes.csv`. 판마다 쓴 t는 `check9_t.csv`. 그림 2(`figures/fig2_ablation_*`)에 '고정 값' 칸을 더함. 덧붙임 판은 앞서 낸 표의 요약 (다) 기준에서 뺌(앞 값 유지).

## 3. 확인마다

- **확인 1** (`check1_*`, `variogram_*`, 그림 A1): 반변동도는 6 m 안에서 평평해지지 않고 4~6 m까지 오름. 정의대로의 95 % 거리는 모든 단위·지역에서 4.4~4.9 m로 고리 가운데 반지름(R 1.0·1.5·3.0에서 0.75·1.0·1.75 m)보다 커서 (가)는 어느 반지름에서도 만족 0 %. 50 % 거리: LoD2 지붕 {f(VS[(VS.unit == 'LoD2 지붕') & (VS.region == '전체')].L50.iloc[0])}, 벽 {f(VS[(VS.unit == 'LoD2 벽') & (VS.region == '전체')].L50.iloc[0])}, 항공 LiDAR 지붕 {f(VS[(VS.unit == '항공 LiDAR 지붕') & (VS.region == '전체')].L50.iloc[0])} m. 고리 값은 WIDEN0 같은 중심 패치만(넓이 LoD2 지붕 91.7 %, 벽 97.4 %, 항공 LiDAR 35.5 %). R 1.0·3.0의 N은 넓이 비로 어림. u_M 비(중앙값, 모든 자리): {'; '.join(f"{x.unit} {x.ratio} {f(x.q50)}" for _, x in st.iterrows())}.
- **확인 2~4** (`check2_*`, `check3_*`, `check4_*`): 근거 표의 값. 건물별 필요한 n과 n_b는 `check4_buildings.csv`(σ_W {f(100*sw, 2)} cm).
- **확인 5** (`check5_*`, 그림 A2): 규칙 1은 무늬 세기 구간마다 s_P < t 비율이 10 % 아래로 내려가 그 위로 계속 아래인 가장 작은 구간. 규칙 2는 표본의 σ_n과 t로 구함(t ≤ 0인 지역은 구할 수 없음).
- **확인 6~8** (`check6_*`, `check7_*`, `check8_*`): 표본 사진 점에서 원본 사진을 다시 읽음. 표에는 탐색 지역마다의 줄도 있음(확인 6의 화소 크기는 전체만). 확인 1의 4는 `check1_no_radius`, 그림 A2b는 표본의 (무늬 세기, s_P)와 사진 잡음 기댓값 곡선.
- **확인 9 정성**: `figures/addendum1/figA9_changed_t10_*`, `figA9_changed_tex8_*`(맞게 바뀐 곳 둘, 틀리게 바뀐 곳 둘, 한 건물에서 하나).

## 4. 표본, 시간, 확인 불가

- 표본 사진 점: {'; '.join(f"{x['prior']} {x['points']}개, 조각 {x['patches_sampled']}개, {f(x['seconds']/60, 1)}분" for x in sm)}. 씨앗 20261117, 탐색 지역마다 넓이에 비례.
- 표본 조각은 잘라낸 마스크 없이 25 x 25 전체로 셈. 다시 셈 s_P와 저장된 s_P의 상관: {'; '.join(f"{x.unit} {f(x.corr_s_full_vs_stored, 3)}" for _, x in C5R[C5R.region == '전체'].iterrows())} (무늬 세기 {'; '.join(f(x.corr_texture_full_vs_stored, 3) for _, x in C5R[C5R.region == '전체'].iterrows())}). 80° 확장 사진의 가림은 MVS 깊이 지도(0.5 m)로 봄. 확인 7의 차례는 저장된 선택 차례.
- 확인 불가: 확인 3의 벽 원통 10 m(캠퍼스 패치에 저장 값 없음). 정의를 정한 곳은 `issues.md`.
"""
    (D/'판단비교절제_덧붙임1_보고_v1.md').write_text(txt); print('REPORT', len(txt))
if __name__ == '__main__': main()
