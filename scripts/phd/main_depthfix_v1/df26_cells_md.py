"""Request 2 pre-training summary (host python, stdlib): 추가요청2_학습전셈.md"""
import csv, json
from pathlib import Path
R = Path(__file__).resolve().parents[3]; D = R/'docs/experiments/phd/main_depthfix_v1'; T = D/'tables'
O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'
S = ['R1rep_b10__LoD2', 'R1rep_b10__ALS', 'B173nb_b10__ALS', 'B173nb_b10__LoD2']
KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 주변 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 주변 × LoD2'}
def rows(n): p = T/f'{n}.csv'; return list(csv.DictReader(open(p))) if p.exists() else []
def f(x, d=1):
    try: return f'{float(x):.{d}f}'
    except (TypeError, ValueError): return '—'
def i(x):
    try: return f'{int(float(x)):,}'
    except (TypeError, ValueError): return '—'
L = ['# 추가 요청 2 학습 전 셈: 칸 지도(판 9·10·11) (PHD-MAIN-DEPTHFIX-v1)\n',
     '- 학습 단위: 건물 단위 장면. 학습 없음. 값만 싣는다. `scientific_verdict`: null. 판 10은 참값을 쓰는 **진단** 판이다.',
     '- 칸 = 패치가 사전 정보 면 위에서 차지하는 격자 칸(`prior_propagation_v6` 저장소: 중심 + 간격 × (a·t1 + b·t2), |a|·|b| ≤ ½; LoD2는 면 위 정사각형, 항공 LiDAR는 XY 격자 칸을 면에 올린 평행사변형). 판 0 목표 높이만큼 법선 방향으로 옮겨 그렸다(`target_cells.cpp`). 칸이 없는 위치(면 무게중심 하나뿐인 위치)는 한 변 sqrt(넓이) 정사각형으로 했다(issues 27). 참값은 판 10 지도와 아래 확인 셈에만 썼다.',
     '- 판 9 = 판 1 규칙(뒷면 빼기, 10 m 규칙, 무게·목표·처음 가우시안 같음)을 칸 지도에. 판 10 = 판 9 + 참값 깊이 버퍼가 목표보다 τ 넘게 가까운 화소 무게 0 + 목표 화소 무게 모두 1. 판 11 = 판 9 + 나 + 다(판 4와 같은 방식, 판 9 지도에서 구함).\n',
     '## 1. 지도 자체\n', '| 장면 | 칸 지도 목표 화소 | 원반 지도(판 1) 목표 화소 | 판 1 원반 목표가 판 9에서 영상 깊이로 % | 뒤의 목표로 % | 지시 없음으로 % | 합 % | 판 10에서 참값 가림으로 무게 0 화소 | 판 11 종류별 평균 무게(나 뒤: 가중 평균 / 영상 깊이 / 되돌림 / 결측) |', '|---|---|---|---|---|---|---|---|---|']
for s in S:
    p = O/'maps/base'/f'cell_receipt_{s}.json'
    if not p.exists(): continue
    r = json.loads(p.read_text()); st = r['stats']; dp = st['disc_pixels_ga']; tw = r['type_mean_weight_p11']
    L.append(f"| {KO[s]} | {st['cell_pixels']:,} | {dp:,} | {100*st['gap_image']/dp:.2f} | {100*st['gap_behind']/dp:.2f} | {100*st['gap_none']/dp:.2f} | {r['gap_share_of_disc_pixels_pct']:.2f} | {st['diag_zeroed']:,} | {tw['가중 평균']:.2f} / {tw['영상 깊이']:.2f} / {tw['되돌림']:.2f} / {tw['결측']:.2f} |")
L += ['\n- \'칸 사이 틈\' = 판 1 원반 지도가 원반 목표를 주던 화소 가운데 판 9 칸 지도에서 영상 깊이 지시·뒤의 목표(τ 넘게 뒤)·지시 없음이 된 화소(지도 전체, 모든 학습 영상).\n',
      '## 2. 대상 점이 가려지지 않은 영상에서 받는 지시 (추가 요청 1 표, 판 0·1·9·10·11)\n',
      '대상 점 = 영상 깊이가 틀리고 판 0 목표가 맞는 점, 잃음·지킴은 판 0 결과. 점마다 다섯 종류 영상 비율의 중앙값 %.\n',
      '| 장면 | 무리 | 판 | 맞는 목표 | 앞의 다른 목표 | 영상 깊이 지시 | 뒤의 목표 | 지시 없음 | 맞는 목표 절반 넘는 점 %: 가려지지 않은 영상 | 모든 바깥 영상 |', '|---|---|---|---|---|---|---|---|---|---|']
for s in S:
    for r in rows(f'kinds_visible_{s}_cells'): L.append(f"| {r['stem']} | {r['group']} | {r['map']} | {f(r['맞는 목표_비율_중앙값_pct'])} | {f(r['앞의 다른 목표_비율_중앙값_pct'])} | {f(r['영상 깊이 지시_비율_중앙값_pct'])} | {f(r['뒤의 목표_비율_중앙값_pct'])} | {f(r['지시 없음_비율_중앙값_pct'])} | {f(r['맞는 목표_절반_넘는_점_pct'])} | {f(r.get('맞는 목표_절반_넘는_점_pct(모든 바깥 영상)'))} |")
L += ['\n### 종류마다 화소 무게의 중앙값(0 뺌) — 판 11은 무게가 바뀌는 판\n', '| 장면 | 무리 | 판 | 맞는 목표 | 앞의 다른 목표 | 영상 깊이 지시 | 뒤의 목표 |', '|---|---|---|---|---|---|---|']
for s in S:
    for r in rows(f'kinds_visible_{s}_cells'): L.append(f"| {r['stem']} | {r['group']} | {r['map']} | {f(r.get('맞는 목표_무게_중앙값(0 뺌)'), 2)} | {f(r.get('앞의 다른 목표_무게_중앙값(0 뺌)'), 2)} | {f(r.get('영상 깊이 지시_무게_중앙값(0 뺌)'), 2)} | {f(r.get('뒤의 목표_무게_중앙값(0 뺌)'), 2)} |")
L += ['\n### 대상 점 화소: 판 1 종류 → 판 9 종류 (가려지지 않은 영상, 쌍 %)\n', '| 장면 | 무리 | 판 1 종류 | 쌍 | → 맞는 목표 | 앞의 다른 목표 | 영상 깊이 지시 | 뒤의 목표 | 지시 없음 |', '|---|---|---|---|---|---|---|---|---|']
for s in S:
    for r in rows(f'kinds_transition_p1_p9_{s}'): L.append(f"| {r['stem']} | {r['group']} | {r['kind_p1']} | {i(r['pairs'])} | {f(r['판 9: 맞는 목표 %'])} | {f(r['판 9: 앞의 다른 목표 %'])} | {f(r['판 9: 영상 깊이 지시 %'])} | {f(r['판 9: 뒤의 목표 %'])} | {f(r['판 9: 지시 없음 %'])} |")
L += ['\n- 대상 점에서 \'칸 사이 틈으로 뒤의 목표나 영상 깊이 지시를 받게 된\' 몫 = 위 표에서 판 1 \'맞는 목표\' 줄의 → 영상 깊이 지시 + 뒤의 목표.\n',
      '## 3. \'앞의 다른 목표\'를 판 9 지도로 다시 셈\n', '| 장면 | 무리 | 쌍 | 가중 평균 % | 영상 깊이 % | 되돌림 % | 결측 % | 참값 깊이에 맞음 % | 같은 패치 % | 맞닿은 패치 % | 떨어진 패치 % |', '|---|---|---|---|---|---|---|---|---|---|---|']
for s in S:
    for r in rows(f'front_owner_{s}_p9'): L.append(f"| {r['stem']} | {r['group']} | {i(r['front_pairs'])} | {f(r['목표 종류 가중 평균 %'])} | {f(r['목표 종류 영상 깊이 %'])} | {f(r['목표 종류 되돌림 %'])} | {f(r['목표 종류 결측 %'])} | {f(r['참값 깊이에 맞음 % (버퍼 있는 쌍 가운데)'])} | {f(r['같은 패치 %'])} | {f(r['맞닿은 패치 %'])} | {f(r['떨어진 패치 %'])} |")
L += ['\n참값에 맞지 않는 앞 목표만:\n', '| 장면 | 무리 | 쌍 | 맞는 목표가 제 패치 밖까지 덮음 % | 틀린 목표 % | 그 패치에 참값 점 없음 % | 앞 1 m 안 % | 1~3 m % | 3~10 m % | 10 m 넘음 % |', '|---|---|---|---|---|---|---|---|---|---|']
for s in S:
    for r in rows(f'front_wrong_{s}_p9'): L.append(f"| {r['stem']} | {r['group']} | {i(r['front_not_gt_pairs'])} | {f(r['맞는 목표가 제 패치 밖까지 덮음 %'])} | {f(r['틀린 목표 %'])} | {f(r['그 패치에 참값 점 없음 %'])} | {f(r['앞 1 m 안 %'])} | {f(r['앞 1~3 m %'])} | {f(r['앞 3~10 m %'])} | {f(r['앞 10 m 넘음 %'])} |")
L += ['\n판 0 지도 값은 `셈_앞의다른목표.md`.\n', '## 4. 그림\n', '- 다섯 자리의 목표 깊이 지도, 판 1(원반)과 판 9(칸) 나란히, 자리 그림과 같은 영상: `figures/cellmap_<자리>.png`(분홍 테두리 = 판 1 원반 목표가 판 9에서 빠지거나 뒤로 간 화소).\n',
      '## 5. 학습\n', '- 이 묶음을 낸 뒤 판 10 R1 두 장면 → 판 11 R1 두 장면 → 판 10·11 B173 × 항공 LiDAR(씨앗 0)를 바로 시작한다(답을 기다리지 않음). 도는 학습(판 3 R1 × LoD2, 판 4 R1 두 장면)은 그대로.']
(D/'추가요청2_학습전셈.md').write_text('\n'.join(L)+'\n'); print('WROTE')
