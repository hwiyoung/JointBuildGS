"""학습전셈_요약.md from the pre-training tables (host python, stdlib only). usage: python3 df_pre_md.py"""
import csv, json
from pathlib import Path
R = Path(__file__).resolve().parents[3]; D = R/'docs/experiments/phd/main_depthfix_v1'; T = D/'tables/pre'
O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'
ST = ['R1rep_b10__LoD2', 'R1rep_b10__ALS', 'B173nb_b10__ALS', 'B173nb_b10__LoD2']
KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 주변 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 주변 × LoD2'}
def rows(n, s): return list(csv.DictReader(open(T/f'{n}_{s}.csv')))
def f(x, d=1):
    try: return f'{float(x):,.{d}f}'
    except (TypeError, ValueError): return '—'
def i(x):
    try: return f'{int(float(x)):,}'
    except (TypeError, ValueError): return '—'
L = []; a = L.append
a('# 학습 전 셈 요약 (PHD-MAIN-DEPTHFIX-v1)\n')
a('- 학습 단위: 본 방법 판(FINALTRAIN-v1)과 같은 **건물 단위 장면** 넷(R1 × LoD2, R1 × 항공 LiDAR, B173 주변 × 항공 LiDAR, B173 주변 × LoD2). σ_ref는 장면마다 하나.')
a('- 학습하지 않은 셈이다. 참값은 4절의 확인 셈(스위치가 뜻대로 작동하는지)에만 썼고 스위치 규칙에는 쓰지 않았다. `scientific_verdict`: null.')
a('- 규칙: `발주문_v1.md`, `회신1_v1.md`, `회신2_v1.md`(스위치 라·마는 회신 2의 지도 P·M 규칙). 정한 것은 `issues.md`.\n')
a('## 1. 새 판단 구조의 목표 (1절 검산)\n')
a('| 장면 | 이은 패치 | 나5 열과 같은 판정 (넓이 %) | 다름: 장면 영상 높이 없음 → 결측 | 다름: 장면 u 없음 → 결측 | 다름: 그 밖 | 이어지지 않음 (평가 범위 안) |')
a('|---|---|---|---|---|---|---|')
for s in ST:
    r = rows('check1', s)[0]
    a(f"| {KO[s]} | {i(r['joined_patches'])} | {i(r['equal_patches'])} ({f(r['equal_area_pct'])} %) | {i(r['differ_no_scene_image_height'])} ({f(r['differ_no_scene_image_height_area_m2'])} m²) | {i(r['differ_no_scene_u'])} | {i(r['differ_other'])} | {i(r['unjoined_patches'])} ({i(r['unjoined_in_eval'])}) |")
a('\n- 이은 패치 가운데 판정이 다른 것은 모두 \'가중 평균·영상 깊이인데 장면 패치에 영상 높이(또는 u)가 없어 결측으로 둔\' 패치다(회신 1 §2 높이는 장면, 발주문 1절 첫 줄). 그 밖의 다름은 0이다.')
a('- 이어지지 않은 패치는 본 방법 판의 목표를 그대로 쓴다(목표 파일에서 확인).\n')
tr = {s: json.loads((O/'families/targets_receipt'/f'{s}.json').read_text()) for s in ST}
a('| 장면 | 가중 평균 | 영상 깊이 | 되돌림 | 결측 | 목표 없음 | 라 대상 패치 (넓이 m²) |')
a('|---|---|---|---|---|---|---|')
for s in ST:
    t = tr[s]['types']; a(f"| {KO[s]} | {i(t['가중 평균']['patches'])} | {i(t['영상 깊이']['patches'])} | {i(t['되돌림']['patches'])} | {i(t['결측']['patches'])} | {i(t['목표 없음']['patches'])} | {i(tr[s]['split_patches'])} ({f(tr[s]['split_area_m2'])}) |")
a('\n### 1.1 캠퍼스 영상 높이와 장면 영상 높이 (회신 1 §2)\n')
a('| 장면 | 종류 | 패치 | 차이 중앙값 (m) | 차이 90 % (m) | τ 넘는 넓이 % |')
a('|---|---|---|---|---|---|')
for s in ST:
    for r in rows('height_campus_vs_scene', s): a(f"| {KO[s]} | {r['type']} | {i(r['patches_both_heights'])} | {f(r['abs_diff_median_m'], 3)} | {f(r['abs_diff_p90_m'], 2)} | {f(r['over_tau_area_pct'])} |")
a('\n장면 높이로 \'유의한가\'·\'큰가\'만 다시 따졌을 때(영상 점검은 다시 하지 않음) 목표 종류가 바뀌는 패치:\n')
a('| 장면 | 바뀐 패치 | 넓이 m² | 다시 따진 넓이 가운데 % | 캠퍼스 규칙 재현(유의 / 큼) |')
a('|---|---|---|---|---|')
for s in ST:
    r = [x for x in rows('rejudge_scene', s) if x['type_campus'] == '바뀜 합'][0]
    a(f"| {KO[s]} | {i(r['patches'])} | {f(r['area_m2'])} | {f(r['share_of_rejudged_area_pct'], 2)} | {f(r['check_campus_sig_rule_agree_pct'])} % / {f(r['check_campus_big_rule_agree_pct'])} % |")
a('\n바뀌는 쪽은 `tables/pre/rejudge_scene_*.csv`. 5.1의 표는 이 패치에 놓인 참값 점을 뺀 값도 함께 낸다.\n')
a('## 2. 검산 (2절)\n')
fc = json.loads((O/'checks/ftcheck_R1rep_b10__ALS.json').read_text()); oc = json.loads((D/'tables/offcheck.json').read_text())
a(f"- 본 방법 판 목표 파일을 이번 코드에 넣어 만든 처음 가우시안과 지도: 배열이 모두 같다(처음 가우시안 같음 {fc['seeds_arrays_equal']}, 지도 {fc['map_arrays_equal']}/{fc['views']} 영상, 파일 sha도 같음 {fc['map_sha_equal']}).")
a(f"- 스위치를 모두 끈 학습(R1 × 항공 LiDAR, 1,000회, 씨앗 0·1): 카메라 차례 = 기록 {oc['camera_sequence_equal']}; 값 {oc['values']}개 가운데 기록과 정확히 같은 것 {oc['exact']}개; 기준(|씨앗 0 − 기록| ≤ |씨앗 1 − 기록|) 만족 {oc['within']}개. 넘은 셋은 600회 가우시안 수(차이 22개), 900회 손실, 1,000회 가우시안 수(53,303 대 53,703, 0.75 %). GPU 학습은 비트 단위로 재현되지 않는다(issues 12). 표 `tables/offcheck.csv`.")
rr = {s: json.loads((O/'maps/base'/f'ra_receipt_{s}.json').read_text()) for s in ST if (O/'maps/base'/f'ra_receipt_{s}.json').exists()}
ok = all(v['check']['c1_equals_P'] and v['check']['c0_equals_M'] for v in rr.values()) if rr else None
a(f"- 스위치 라 검산(회신 2): c를 모두 1로 두면 지도 P만, 0으로 두면 지도 M만 쓴 지도와 배열이 같다 — {'네 장면 모두 같음' if ok else '확인 안 됨'} (25번째 영상마다, 영상 {', '.join(str(v['check']['views_checked']) for v in rr.values())}개).")
a('- 두 목표 판 시험 학습(B173 주변 × LoD2, 판 5 지도의 첫 판, 300회): 손실 유한, 정상 끝(결과로 쓰지 않음).\n')
a('## 3. 스위치 가: 빠지는 지시 (4절)\n')
a('| 장면 | 판 0 목표 화소 | 뒷면으로 빠짐 % | 그 가운데 목표가 맞던 % | 10 m로 빠짐 % | 그 가운데 목표가 맞던 % | 10 m에서 영상 깊이가 틀린 % |')
a('|---|---|---|---|---|---|---|')
for s in ST:
    r = [x for x in rows('ga_removed', s) if x['type'] == '모두'][0]
    a(f"| {KO[s]} | {i(r['target_pixels_p0'])} | {f(r['뒷면_빠진_비율_pct'])} | {f(r['뒷면_빠진_가운데_목표_맞음_pct'])} | {f(r['10 m_빠진_비율_pct'])} | {f(r['10 m_빠진_가운데_목표_맞음_pct'])} | {f(r['10 m_빠진_가운데_영상깊이_틀림_pct'])} |")
a('\n목표 종류마다는 `tables/pre/ga_removed_*.csv`. \'목표가 맞던\' = 그 화소의 참값 깊이 버퍼와 목표 깊이가 τ 안(참값 버퍼가 있는 화소 가운데).\n')
a('참값으로 본 가려진 화소(참값 점이 목표보다 0.5 m 넘게 앞) 가운데 지시를 받는 비율:\n')
a('| 장면 | 가려진 화소 | 판 0 | 판 1 | 판 1: 여전히 가려진 원반 | 판 1: 무게 0 | 판 1: 영상 깊이로 바뀜 | 판 1: 지시 없음 |')
a('|---|---|---|---|---|---|---|---|')
for s in ST:
    r = rows('ga_gt_occluded', s)[0]
    a(f"| {KO[s]} | {i(r['gt_occluded_target_pixels_p0'])} | {f(r['p0_instructed_pct'])} % | {f(r['p1_instructed_pct'])} % | {f(r['p1_still_occluded_disc_pct'])} % | {f(r['p1_weight0_disc_pct'])} % | {f(r['p1_image_depth_pct'])} % | {f(r['p1_nothing_pct'])} % |")
a('\n뒷면 원반이 빠진 뒤 그 화소:\n')
a('| 장면 | 빠진 화소 | 다른 원반이 차지 % | 그 새 목표가 맞음 % | 영상 깊이로 % | 지시 없음 % |')
a('|---|---|---|---|---|---|')
for s in ST:
    r = rows('ga_back_new_owner', s)[0]
    a(f"| {KO[s]} | {i(r['back_removed'])} | {f(r['new_owner_pct'])} | {f(r['new_owner_right_pct'])} | {f(r['to_image_depth_pct'])} | {f(r['to_nothing_pct'])} |")
a('\n## 4. 스위치 나·다: 목표 종류마다 평균 무게 (4절)\n')
a('| 장면 | 판 | 가중 평균 | 영상 깊이 | 되돌림 | 결측 |')
a('|---|---|---|---|---|---|')
for s in ST:
    W = rows('weights_by_type', s); arms = list(dict.fromkeys(r['arm'] for r in W))
    for arm in arms:
        g = {r['type']: r for r in W if r['arm'] == arm}
        a(f"| {KO[s]} | {arm} | {f(g['가중 평균']['mean'], 2)} | {f(g['영상 깊이']['mean'], 2)} | {f(g['되돌림']['mean'], 2)} | {f(g['결측']['mean'], 2)} |")
a('\n분포(10·25·50·75·90 %)는 `tables/pre/weights_by_type_*.csv`. 판 2 = 무게 차이 줄이기. 대상 점 화소의 무게 중앙값(잃은 점·지킨 점)은 판 0 결과 뒤 덧붙인다.\n')
a('## 5. 스위치 라 (4절, 회신 2)\n')
a('| 장면 | κ | 대상 패치 (넓이 m²) | c 중앙값 | c ≥ 0.5 % | 처음 가우시안 면이 판 0과 다른 패치 (m²) |')
a('|---|---|---|---|---|---|')
for s in ST:
    for r in rows('ra_patches', s): a(f"| {KO[s]} | {r['kappa']} ({r['kappa_value']}) | {i(r['patches'])} ({f(r['area_m2'])}) | {f(r['c_q50'], 2)} | {f(r['c_ge_05_pct'])} | {i(r['seed_face_changed_patches'])} ({f(r['seed_face_changed_area_m2'])}) |")
a('\nc 구간(0~0.2, 0.2~0.5, 0.5~1)별 비율은 `tables/pre/ra_patches_*.csv`. 참값이 있는 대상 패치의 참값 점에서, c가 큰 면이 맞는 비율:\n')
a('| 장면 | κ | 참값 점 | c가 큰 면 맞음 % | 판 0 목표 면 맞음 % | 사전 정보 면 맞음 % | 영상 깊이 면 맞음 % |')
a('|---|---|---|---|---|---|---|')
for s in ST:
    for r in rows('ra_gt_face', s): a(f"| {KO[s]} | {r['kappa']} | {i(r['gt_points'])} | {f(r['larger_c_face_right_pct'])} | {f(r['p0_target_face_right_pct'])} | {f(r['prior_right_pct'])} | {f(r['image_right_pct'])} |")
if rr:
    a('\n지도 P·M (회신 2): 대상 패치가 한 지도에서라도 가진 화소 가운데 두 항을 모두 받는 화소, 두 지도의 소유 패치가 다른 화소, 면마다 지시를 받는 화소(판 1과 나란히):\n')
    a('| 장면 | 판 | 대상 화소 | 두 항 모두 % | 두 지도 소유 다름 % | 지도 M 영상 깊이 면 지시 | 판 1 영상 깊이 면 지시 | 지도 P 사전 정보 면 지시 | 판 1 사전 정보 면 지시 |')
    a('|---|---|---|---|---|---|---|---|---|')
    nm = {'ga_ra_kA': '판 5', 'ga_ra_ma_kA': '판 6', 'ga_ra_k1': '판 7', 'ga_na_da_ra_ma_kA': '판 8'}
    for s, v in rr.items():
        for k, p in v['pixels'].items():
            a(f"| {KO[s]} | {nm[k]} | {i(p['split_pixels'])} | {f(100*p['both_terms']/p['split_pixels'])} | {f(100*p['owners_differ']/p['split_pixels'])} | {i(p['map_M_image_face_instructed'])} | {i(p['p1_image_face_instructed'])} | {i(p['map_P_prior_face_instructed'])} | {i(p['p1_prior_face_instructed'])} |")
a('\n## 6. 점 무리 (5절, 판 0 목표 기준으로 한 번 정함)\n')
a('| 장면 | 두 자료 모두 맞음 (목표 맞음 / 틀림) | 사전 정보가 틀림 | 영상 깊이가 틀림 | 영상 깊이 결측 |')
a('|---|---|---|---|---|')
for s in ST:
    P = {(r['case'], r['target_ok']): r['points'] for r in rows('points', s)}
    a(f"| {KO[s]} | " + ' | '.join(f"{i(P[(c, 'True')])} / {i(P[(c, 'False')])}" for c in ['0', '1', '2', '4']) + ' |')
a('\n\'목표 맞음\' = 참값 점에서 그 패치의 판 0 목표 평면까지 법선 거리 ≤ τ(WRONGTARGET의 둘째 정의; 새 목표의 메시가 없어서, issues 11).\n')
a('## 7. 그림 자리\n')
c = json.loads((R/'configs/phd/main_depthfix_v1/depthfix_v1.json').read_text())['places']
for k, v in c.items(): a(f"- {k}: {v.get('building', '')} {v.get('why', v.get('source', ''))}")
(D/'학습전셈_요약.md').write_text('\n'.join(L)+'\n'); print('WROTE', len('\n'.join(L)))
