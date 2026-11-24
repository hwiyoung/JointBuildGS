"""Result summary markdown from tables/res_*.csv (host python, stdlib). usage: python3 df16_md.py <name> <arm,arm,...> [title]
writes docs/experiments/phd/main_depthfix_v1/<name>.md: 5.1 named values side by side per scene (base extraction, + occl10/occlga), cells, by type,
5.2 scene values, 5.3 mechanism values for the listed arms. Values only, no verdict."""
import csv, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3]; D = R/'docs/experiments/phd/main_depthfix_v1'; T = D/'tables'
name, arms = sys.argv[1], sys.argv[2].split(','); title = sys.argv[3] if len(sys.argv) > 3 else name
AK = {a: f'판 {a[1]}' for a in arms}; SC = ['R1 × LoD2', 'R1 × 항공 LiDAR', 'B173 주변 × 항공 LiDAR', 'B173 주변 × LoD2']
def rows(n):
    p = T/f'{n}.csv'; return list(csv.DictReader(open(p))) if p.exists() else []
def f(x, d=1):
    try: return f'{float(x):.{d}f}'
    except (TypeError, ValueError): return '—'
def i(x):
    try: return f'{int(float(x)):,}'
    except (TypeError, ValueError): return '—'
r51 = [r for r in rows('res_51') if r['arm_id'] in arms and r['seed'] == '0']
L = [f'# {title} (PHD-MAIN-DEPTHFIX-v1)\n', '- 학습 단위: 건물 단위 장면(본 방법 판과 같음). 값만 싣는다. 판정은 사람이 한다. `scientific_verdict`: null.',
     '- 판 0 씨앗 1(흔들림)은 끝난 장면만 `tables/res_criteria.csv`의 \'두 씨앗 차이\' 칸에 들어간다(R1 두 장면 먼저, B173 둘은 맨 끝).',
     '- 점 무리는 판 0의 목표로 한 번 정했다(목표 맞음 = 참값 점에서 판 0 목표 평면까지 법선 거리 ≤ τ, issues 11). 참값 점 1,000개 미만 칸은 비율 대신 —.',
     '- 주 지표 = 영상 깊이가 틀리고 목표가 맞는 점의 잃은 비율, 지킬 값 1 = 사전 정보가 틀리고 목표가 틀린 점의 고친 비율, 지킬 값 2 = 두 자료 모두 맞고 목표가 맞는 점의 잃은 비율, 함께 볼 값 = 영상 깊이가 틀리고 목표도 틀린 점의 고친 비율, 참고 = 영상 깊이 결측·목표 맞음의 잃은 비율.\n']
for ext in ['기준 추출', '가림 제외(10 m)', '가림 제외(가 지도)']:
    sub = [r for r in r51 if r['extraction'] == ext and r['points'] == '모든 점']
    if not sub: continue
    L += [f'## 5.1 {ext}\n', '| 장면 | 판 | 주 지표 % (점) | 지킬 값 1 % (점) | 지킬 값 2 % (점) | 함께 볼 값 % (점) | 참고 % (점) |', '|---|---|---|---|---|---|---|']
    for s in SC:
        for a in arms:
            r = next((x for x in sub if x['scene'] == s and x['arm_id'] == a), None)
            if r: L.append(f"| {s} | {AK[a]} | {f(r['main_lost_pct'])} ({i(r['main_lost_n'])}) | {f(r['keep1_fixed_pct'])} ({i(r['keep1_fixed_n'])}) | {f(r['keep2_lost_pct'])} ({i(r['keep2_lost_n'])}) | {f(r['also_fixed_pct'])} ({i(r['also_fixed_n'])}) | {f(r['ref_lost_pct'])} ({i(r['ref_lost_n'])}) |")
            else: L.append(f'| {s} | {AK[a]} | 아직 | | | | |')
    L.append('')
for lab in ['종류 바뀐 패치 뺌', '판 0에서 가린 화소 지시를 절반 넘게 받던 점', '라 대상 패치의 점', '라 대상 패치 가운데 판 0 되돌림', '라 대상 패치 가운데 판 0 영상 깊이']:
    sub = [r for r in r51 if r['extraction'] == '기준 추출' and r['points'] == lab]
    if not sub: continue
    L += [f'### 5.1 기준 추출 — {lab}\n', '| 장면 | 판 | 주 지표 % (점) | 지킬 값 1 % (점) | 함께 볼 값 % (점) |', '|---|---|---|---|---|']
    for r in sub: L.append(f"| {r['scene']} | {r['arm']} | {f(r['main_lost_pct'])} ({i(r['main_lost_n'])}) | {f(r['keep1_fixed_pct'])} ({i(r['keep1_fixed_n'])}) | {f(r['also_fixed_pct'])} ({i(r['also_fixed_n'])}) |")
    L.append('')
ty = [r for r in rows('res_51_type') if r['arm_id'] in arms and r['seed'] == '0' and r['extraction'] == '기준 추출' and r['type'] != '목표 없음']
if ty:
    L += ['### 5.1 기준 추출 — 주 지표를 판 0 목표 종류로 나눔\n', '| 장면 | 판 | 가중 평균 | 영상 깊이 | 되돌림 | 결측 |', '|---|---|---|---|---|---|']
    for s in SC:
        for a in arms:
            g = {r['type']: r for r in ty if r['scene'] == s and r['arm_id'] == a}
            if g: L.append(f'| {s} | {AK[a]} | ' + ' | '.join(f"{f(g[t]['main_lost_pct'])} ({i(g[t]['main_lost_n'])})" if t in g else '—' for t in ['가중 평균', '영상 깊이', '되돌림', '결측']) + ' |')
    L.append('')
cl = [r for r in rows('res_51_cells') if r['arm_id'] in arms and r['seed'] == '0' and r['extraction'] == '기준 추출']
if cl:
    L += ['### 5.1 네 경우 × 판 0 목표 맞음·틀림: 결과 면이 허용 거리 안인 비율 % (점)\n', '| 장면 | 판 | ' + ' | '.join(f'{c} / 목표 {"맞음" if t else "틀림"}' for c in ['두 자료 모두 맞음', '사전 정보가 틀림', '영상 깊이가 틀림', '영상 깊이 결측'] for t in (1, 0)) + ' |', '|---|---|' + '---|'*8]
    for s in SC:
        for a in arms:
            g = {(r['case'], r['target_ok']): r for r in cl if r['scene'] == s and r['arm_id'] == a}
            if g: L.append(f'| {s} | {AK[a]} | ' + ' | '.join(f"{f(g[(c, t)]['within_pct'])} ({i(g[(c, t)]['points'])})" for c in ['두 자료 모두 맞음', '사전 정보가 틀림', '영상 깊이가 틀림', '영상 깊이 결측'] for t in ('True', 'False')) + ' |')
    L.append('')
r52 = [r for r in rows('res_52') if r['arm_id'] in arms and r['seed'] == '0']
if r52:
    L += ['## 5.2 장면 값\n', '| 장면 | 판 | 완전성 % | 정확성 % | 부유 표면 % | 가우시안 15,000회 | 가우시안 30,000회 | 두 겹 패치 넓이 % |', '|---|---|---|---|---|---|---|---|']
    for s in SC:
        for r in [x for x in r52 if x['scene'] == s]: L.append(f"| {s} | {r['arm']} | {f(r['completeness_pct'])} | {f(r['accuracy_pct'])} | {f(r['floating_pct'], 2)} | {i(r['gaussians_15000'])} | {i(r['gaussians_30000'])} | {f(r['two_layer_area_pct']) if r['arm_id'] in ('p5', 'p6', 'p7', 'p8') else '(참고) ' + f(r['two_layer_area_pct'])} |")
    L.append('\n- 두 겹 패치는 발주문 5.2대로 판 5~8의 값이다. 판 0~4 줄의 값은 같은 패치 집합(라 대상 패치)에서 같은 규칙으로 센 참고 값이다.\n- 가우시안 수는 15,000회 뒤로 늘지 않는다(학습 기록에서도 같음).\n- 네 경우의 완전성과 가림 제외 추출의 완전성·정확성은 `tables/res_52.csv`.\n')
m53 = [r for r in rows('res_53') if r.get('map') in AK.values() or (r.get('group', '').endswith('(판 0)') and r.get('map') in ('판 2', '판 3', '판 4'))]
pix = [r for r in m53 if r['group'] in ('잃은 점(판 0)', '지킨 점(판 0)')]
if pix:
    L += ['## 5.3 화소가 준 지시 (대상 점 = 영상 깊이가 틀리고 판 0 목표가 맞는 점, 잃음·지킴은 판 0 결과; 판 2~4 지도 줄 = 4절 덧붙임, 학습 전 값)\n', '- 마지막 열의 \'가린 화소\'는 참값 깊이 버퍼(장면 상자 안의 참값 점만)로 판정했다. 상자 밖 물체에 가려진 화소는 잡지 못한다(issues 23).\n',
          '| 장면 | 지도 | 무리 | 점 | 맞는 목표 절반 넘는 점 %: 모든 바깥 영상 | 가려지지 않은 영상 | 화소 무게 중앙값: 0 포함 | 0 뺌 | 판 0에서 가린 화소 지시를 절반 넘게 받던 점 % |', '|---|---|---|---|---|---|---|---|---|']
    for r in pix: L.append(f"| {r['scene']} | {r['map']} | {r['group']} | {i(r['points'])} | {f(r['right_target_half_pct'])} | {f(r.get('right_target_half_visible_pct'))} | {f(r['w_median'], 2)} | {f(r.get('w_median_nonzero'), 2)} | {f(r['occluded_instr_half_p0_pct'])} |")
    L.append('')
sf = [r for r in m53 if r['group'] == '라 대상 패치 결과 면' and r['p0_type'] == '모두']
if sf:
    L += ['## 5.3 라 대상 패치에서 결과 면의 자리 (넓이 %; 발주문 5.3대로 판 5~8의 값, 판 0~4 줄은 같은 패치의 참고 값)\n', '| 장면 | 판 | c 구간 | 패치 | 사전 정보 면 | 영상 깊이 면 | 두 면 사이 | 두 면 바깥 | 면 없음 |', '|---|---|---|---|---|---|---|---|---|']
    for r in sf: L.append(f"| {r['scene']} | {r['map']} | {r['c_bin']} | {i(r['patches'])} | {f(r['사전 정보 면_area_pct'])} | {f(r['영상 깊이 면_area_pct'])} | {f(r['두 면 사이_area_pct'])} | {f(r['두 면 바깥_area_pct'])} | {f(r['면 없음_area_pct'])} |")
    L.append('\n판 0에서 되돌림·영상 깊이였던 패치로 나눈 값은 `tables/res_53.csv`.\n')
(D/f'{name}.md').write_text('\n'.join(L)+'\n'); print('WROTE', D/f'{name}.md')
