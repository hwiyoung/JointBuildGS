"""Step 7 (jointbuildgs:dev): report.md from out/results.json (facts only, no verdicts)."""
import json

import common as cm

rc = cm.Receipt("report")
R = json.loads((cm.OUT / "results.json").read_text())
tol, checks, facts = R["tolerance"], R["checks"], R["facts"]
PC = [(p, c) for p in cm.PRIORS for c in cm.CONDS]
KO = {"nominal": "정상", "biased": "편향+1.0", "L": "L(ALS)", "M": "M(LoD2)"}


def f(x, d=3, unit=""):
    if x is None:
        return "NA"
    if isinstance(x, bool):
        return "예" if x else "아니오"
    if isinstance(x, str):
        return x
    return f"{x:.{d}f}{unit}"


def pct(x):
    return "NA" if x is None else f"{100 * x:.1f}%"


def stat(p, c, reg, kind="ray_depth_camZ"):
    for row in R["stats_rows"]:
        if row[:5] == [p, c, "ALL", reg, kind]:
            return dict(zip(["n", "m", "s", "m2", "s2", "out_frac"], row[5:]))
    return {}


def cov(p, c, reg):
    for row in R["coverage_rows"]:
        if row[:4] == [p, c, "ALL", reg]:
            return row[6]


def cfl(p, c, reg):
    for row in R["conflict_rows"]:
        if row[:4] == [p, c, "ALL", reg]:
            return row[6]


L = []
A = L.append
A(f"# 첫 단계 보고서 — {R['task_id']}")
A("")
A(f"생성: {R['generated_at']} (UTC). `scientific_verdict: null`. 판정 문장은 쓰지 않고 사실만 적는다.")
A("")
A("## 1. 입력과 절차 요약")
A("")
g = R["provenance"]["geometry"]
mv = R["provenance"]["mvs_resampling"]
A(f"- 장면: GeoGS 저자 예제 15시점(5644×4082, PINHOLE), 대상 건물 `{R['config']['scene']['target_building']}`. 포즈는 진단 실험 `sparse_txt`(images.bin에서 생성, sparse_lod와 동일)를 그대로 썼다.")
A(f"- MVS 깊이: P0 공통 기반 COLMAP `patch_match_stereo` geometric-consistency 깊이/법선(1024×741, 카메라 Z m). 시점 영상 크기로 재표본: 깊이 = 유효 이웃 가중 이중선형, 마스크 = 최근접. 픽셀 중심 +0.5 규약 양쪽 동일. 일관 시점 수: consistency graph 파일 {mv['consistent_view_count']['n_consistency_graph_files']}개 → **nviews 배열 없음**, 신뢰도 = geometric 필터 통과 여부(prior 미사용).")
A(f"- prior M(LoD2): 정상 = 저자 제공 LoD2Depth 배열(`lod2_prior/raw_depth`), 편향 = 진단 실험 `B+1.0/scene/lod2_biased.obj`(복구 CityGML 전 정점 +1.000 m, 면 동일 확인)를 같은 `LoD2Depth/main.py`로 렌더. 법선은 복구 메시 렌더의 `raw_normal`(정상은 제공 배열에 법선이 없음).")
als = g["als"]
A(f"- prior L(ALS): 바이에른 ALS 원시 타일 `{als['tiles'][0]['path']}`(LAS {als['tiles'][0]['las_version']}, GPS 시각 기준 취득 {als['acquisition_utc_from_gps_time'][0][:10]}), 대상 건물 XY 외접 사각형 ±{als['margin_m']:.0f} m 크롭, 클래스 2(지면)·6(건물)만 {als['n_points_used']:,}점(밀도 {als['density_pts_per_m2_used']:.1f}점/m²), 2.5D Delaunay TIN {als['n_triangles']:,}삼각형 → 같은 `LoD2Depth/main.py` 광선 추적. 편향 = 전 점 z+1.0 m 후 같은 절차. **대체(GT 간추림) 사용 안 함.** 높이 기준: LoD2와 동일하게 −604+45.66 m 상수 이동.")
A(f"- 지붕/벽면/지면 구분: 정상 복구 LoD2 메시(건물 {g['lod2']['n_buildings']}동, 다각형 {g['lod2']['n_polygons']}개)를 시점별 다각형 id로 렌더. 대상 건물 다각형 {g['lod2']['target_polygons']} (규칙: GroundSurface=지면, |n_z|>0.2=지붕, 이하=벽면). L의 '지면' = 건물이 아닌 픽셀 중 ALS TIN 깊이가 있는 픽셀; M은 지형이 없어 지면 NA. 다른 건물 픽셀은 집계 제외.")
A(f"- 상수: 일관 시점 문턱 3(미사용), k=2.5, 이상치 3s, τ_spec L={R['config']['priors']['L']['tau_spec_m']} m / M={R['config']['priors']['M']['tau_spec_m']} m, τ_n 기본 10°. 잔차 r = MVS 깊이 − prior 깊이(카메라 Z, 표에서 `ray_depth_camZ`), 지붕 연직 잔차 = r × |n·d|/|n_z| (n = 그 픽셀 LoD2 면의 단위 법선, d = 비정규화 세계 광선 R^T(x,y,1); 수평면이면 r×|d_z|와 같음. 표에서 `vertical`; +는 prior가 MVS보다 높음). 발주서의 '광선 방향의 연직 성분' 환산을 경사면까지 일반화한 것으로, 수평면 식 r×|d_z|만 쓰면 카메라를 향한 경사 지붕을 스치듯 보는 시점에서 연직 값이 절반 이하로 줄어든다(수평면 식의 값은 `checks`의 vertical_conversion에 기록).")
A("- τ와 충돌 문턱의 기준 영역: 지붕(두 바퀴 m2, s2). 충돌 = 신뢰도 1 ∧ prior 마스크 1 ∧ |r − m2_정상,영역| > 3·s2_정상,영역 (영역별 정상 조건 값). τ_n = m2_n + 2.5·s2_n(부호 없는 각도라 중앙값 보정; 문자 그대로의 2.5·s2_n도 기록).")
A("")
A("## 2. 개요표 (전체 시점 합산, 지붕 기준)")
A("")
A("| 항목 | " + " | ".join(f"{KO[p]} {KO[c]}" for p, c in PC) + " |")
A("|---|" + "---:|" * 4)
for key, name in [("tau_data", "τ_data (m)"), ("tau_spec", "τ_spec (m)"), ("tau", "τ (m)"), ("tau_source", "τ 출처"), ("tau_n", "τ_n (°)"), ("m", "m 지붕 1차 (m)"), ("s", "s 지붕 1차 (m)"), ("m2", "m2 지붕 2차 (m)"), ("s2", "s2 지붕 2차 (m)"), ("out_frac", "이상치 비율"), ("m2_v", "연직 m2 지붕 (m)"), ("n", "지붕 픽셀 수")]:
    A(f"| {name} | " + " | ".join((f"{tol[p][c][key]:,}" if key == "n" else f(tol[p][c][key], 4 if key == "out_frac" else 3)) for p, c in PC) + " |")
for reg in ["roof", "wall", "ground", "all"]:
    A(f"| 커버리지 {R['config']['regions_ko'][reg]} | " + " | ".join(pct(cov(p, c, reg)) for p, c in PC) + " |")
for reg in ["roof", "wall", "ground", "all"]:
    A(f"| 충돌 비율 {R['config']['regions_ko'][reg]} | " + " | ".join(pct(cfl(p, c, reg)) for p, c in PC) + " |")
for reg in ["wall", "ground"]:
    A(f"| m2/s2 {R['config']['regions_ko'][reg]} (m) | " + " | ".join(f"{f(stat(p,c,reg).get('m2'))}/{f(stat(p,c,reg).get('s2'))}" for p, c in PC) + " |")
A("")
A(f"진단 실험 N 조건(GeoGS 출력 vs GT, 부호 최근접 거리): 지붕 중앙값 {f(R['diagN']['roof_median_m'])} m, NMAD {f(R['diagN']['roof_nmad_m'])} m; 벽면 {f(R['diagN']['wall_median_m'])} / {f(R['diagN']['wall_nmad_m'])} m. 이 값은 MVS−prior 잔차와 다른 양이므로 `compare_L_vs_M.csv`에 별도 열로 나란히 두었다.")
A("")
A("## 3. 정합 점검과 편향 검증")
A("")
for p in cm.PRIORS:
    pp = checks["per_prior"][p]
    A(f"- {KO[p]} 정상: |m2|={f(abs(pp['R1_values']['m2_roof']))} m, s2={f(pp['R1_values']['s2_roof'])} m → R1 registration_ok = {f(pp['R1_registration_ok'])}." + (f" **경고: {pp['registration_warning_text']}**" if pp["registration_warning"] else ""))
    v = pp["R2_values"]
    A(f"- {KO[p]} 편향: 연직 m2 = {f(v['m2_v_biased'])} m (정상 {f(v['m2_v_nominal'])} m, 차 {f(v['delta_m2_v'])} m, 1.0 m에서 {f(v['deviation_from_1m'])} m) → R2 bias_verified(0.8~1.2 m) = {f(pp['R2_bias_verified'])}.")
b = facts["bias_file_check"]["summary"]
A(f"- 편향 파일 검증(7절 함정 1): 편향 LoD2 렌더 − 복구 정상 렌더의 지붕 연직 차 중앙값 = {f(b['median_over_views_m'])} m (기대 {b['expected_m']:.1f} m, prior가 올라가면 깊이는 준다). 진단 실험의 B+1.0 `lod2_prior`는 실행 시점에 아직 생성되지 않아 같은 OBJ·같은 스크립트로 재생성했다.")
s = facts["supplied_vs_recovered_lod2"]["summary"]
A(f"- 저자 제공 LoD2 배열 − 복구 메시 렌더의 지붕 연직 차 중앙값 = {f(s['median_over_views_m'])} m. 정상 M은 제공 배열, 편향 M은 복구 메시(+1.0)이므로 이 메시 출처 차이가 편향에 동반된다.")
vc = facts["vertical_conversion"]["horizontal_plane_formula_m2_v"]
A(f"- 연직 환산 비교(사실): 수평면 식 r×|d_z|만 쓰면 편향 조건 지붕 연직 m2가 L {f(vc.get('L|biased'))} / M {f(vc.get('M|biased'))} m로 나온다(면 법선 식: {f(tol['L']['biased']['m2_v'])} / {f(tol['M']['biased']['m2_v'])} m).")
sc = [x["scale_check_vs_supplied_lod2"]["median_mvs_minus_lod2_m"] for x in mv["views"] if "scale_check_vs_supplied_lod2" in x]
A(f"- MVS 단위·스케일 검증(7절 함정 3): 시점별 median(MVS − 제공 LoD2) = {min(sc):+.3f} ~ {max(sc):+.3f} m (전 건물 픽셀, 8픽셀 보폭). 수 m 차이 없음.")
fr = R["provenance"]["faceid_render"]["views"]
md = [x.get("max_abs_depth_diff_m") for x in fr if x.get("max_abs_depth_diff_m") is not None]
A(f"- 면 id 렌더와 공식 main.py 깊이의 일치: 최대 |Δ깊이| = {max(md):.2e} m, 히트 마스크 불일치 픽셀 최대 {max(x.get('hit_mask_disagreement_px', 0) for x in fr)}개 (Open3D {R['provenance']['faceid_render']['open3d']}).")
A("")
A("## 4. 정상 조건 지붕 충돌의 위치 사실 (4-8절)")
A("")
for p in cm.PRIORS:
    e = facts["nominal_roof_conflict_facts"].get(p)
    if e:
        A(f"- {KO[p]}: 지붕 신뢰도 픽셀 {e['n_conf_roof']:,} 중 충돌 {e['n_conflict_roof']:,} ({pct(e['n_conflict_roof']/e['n_conf_roof'] if e['n_conf_roof'] else None)}); 면 경계 {e['edge_band_px']}픽셀 이내 {pct(e['edge_band_fraction'])}; MVS가 prior보다 가까움(prior 지붕 위 구조물: 도머·굴뚝·설비 후보) {pct(e['mvs_nearer_fraction'])}, 먼 쪽 {pct((e['n_mvs_farther']/e['n_conflict_roof']) if e['n_conflict_roof'] else None)}.")
A("- 면별 충돌 비율·잔차 중앙값은 `lod2_faces_{prior}_{cond}.csv`; 도머·굴뚝·처마와의 대조는 뷰어 패널 2·3에서 사람이 기록한다(자동 판정 없음).")
A("")
A("## 5. L과 M 비교 (4-8절)")
A("")
x = checks["cross_prior"]
A(f"- τ: L {f(tol['L']['nominal']['tau'])} m vs M {f(tol['M']['nominal']['tau'])} m (상대차 {pct(x['R5_values']['rel_diff_tau'])}). 지붕 충돌 비율 상대차: 정상 {pct(x['R5_values']['rel_diff_roof_conflict']['nominal'])}, 편향 {pct(x['R5_values']['rel_diff_roof_conflict']['biased'])}. → R5 run_both_priors = {f(x['R5_run_both_priors'])}.")
A(f"- s2_L < s2_M: {f(x['s_L_lt_s_M'])} ({f(x['s_values']['s2_L'])} vs {f(x['s_values']['s2_M'])} m). 지붕 커버리지 L {pct(x['coverage_values']['roof_L'])} vs M {pct(x['coverage_values']['roof_M'])} (5%p 이내: {f(x['coverage_within_5pp'])}); 벽면 L {pct(x['coverage_values']['wall_L'])} vs M {pct(x['coverage_values']['wall_M'])}.")
A(f"- 편향 조건에서 지붕 충돌이 켜진 비율: L {pct(cfl('L','biased','roof'))}, M {pct(cfl('M','biased','roof'))} (정상: L {pct(cfl('L','nominal','roof'))}, M {pct(cfl('M','nominal','roof'))}). 벽면: L {pct(cfl('L','nominal','wall'))}→{pct(cfl('L','biased','wall'))}, M {pct(cfl('M','nominal','wall'))}→{pct(cfl('M','biased','wall'))}. L의 벽면 잔차는 TIN 브리징 삼각형이라 참고값이다.")
A("- 지붕 잔차 분포 분위수는 `compare_L_vs_M.csv`(p05~p95, ray/vertical)와 뷰어 패널 4의 히스토그램에 있다.")
A("")
A("## 6. 그림·파일 경로")
A("")
A("- 시점별: `out/{prior}/{cond}/{view}_res.npy|png`, `_resv.npy`, `_conflict.npy|png`, `_region.npy`(정상 폴더); 신뢰도: `out/conf/{view}_conf.npy|png` (prior와 무관하므로 한 곳에 둠).")
A("- 면 속성: `out/lod2_faces_{prior}_{cond}.csv|ply`, 위에서 본 렌더 `out/figures/faces_{prior}_{cond}_conflict.png`. ALS 점: `out/als_points_{cond}.ply`, `out/figures/als_points_{cond}_conflict.png`.")
A("- 표: `out/stats.csv`, `out/tolerance.json`, `out/coverage.csv`, `out/conflict.csv`, `out/compare_L_vs_M.csv`, `out/checks.json`. 설정: `out/stage2_config_L.json`, `out/stage2_config_M.json`. 뷰어: `out/viewer.html` (+`viewer_png/`, `viewer_data/`), `out/viewer_README.md`.")
A("- 실행 기록: `logs/*.log`, `logs/*.host_receipt.json`, `logs/receipt_*.json`, `logs/issues.jsonl`, `provenance/*.json`.")
A("")
A("## 7. 문제와 예외")
A("")
iss = (cm.TASK / "logs/issues.jsonl")
if iss.exists():
    for line in iss.read_text().splitlines():
        if line.strip():
            j = json.loads(line)
            A(f"- {j['id']} ({j['status']}): {j['issue']}")
A("- 일관 시점 수 배열(nviews)은 원천 데이터가 없어 만들지 않았다(문턱 3은 미사용).")
A("- L prior의 벽면 픽셀 잔차는 2.5D TIN의 브리징 삼각형에서 나온 참고값이다. M prior의 지면은 NA다.")
A("")
A("## 8. 둘째 단계 반영")
A("")
A("| 첫 단계 산출 | 둘째 단계의 자리 | 실제 값 (L / M) |")
A("|---|---|---|")
tL, tM = tol["L"]["nominal"], tol["M"]["nominal"]
cL, cM = checks["per_prior"]["L"], checks["per_prior"]["M"]
A(f"| conf.npy(시점별) | 손실의 픽셀 가중 | `out/conf/{{view}}_conf.npy` 15개, prior 가중 = (1−conf)×prior 마스크, MVS 가중 = conf×MVS 마스크 (공통) |")
A(f"| conf.npy | 원반 신뢰도 E | 8000회에 원반 중심을 각 시점에 투영해 conf 평균, 500회마다 갱신 (공통) |")
A(f"| E | 기울기 배율·불투명도 하한 | E<0.5: lr×0.01, 불투명도 하한 0.5; E≥0.5: 배율 1 (공통) |")
A(f"| E | 밀집화·가지치기 | prior 출신 E<0.5 동결, 가지치기 기록 (공통) |")
A(f"| tolerance.json의 τ | 허용 구간·절단 | τ = {f(tL['tau'])} / {f(tM['tau'])} m; 4τ = {f(4*tL['tau'])} / {f(4*tM['tau'])} m; 상수 3τ = {f(3*tL['tau'])} / {f(3*tM['tau'])} m |")
A(f"| τ | 초기화 관측 점 선택 | prior 표면 거리 > {f(tL['tau'])} / {f(tM['tau'])} m인 MVS 점만 시드 |")
A(f"| τ | 판독 문턱 | 이동량 < τ 보존, ≥ τ 보정 (같은 값) |")
A(f"| τ_n | prior 법선 항 허용 각도 | {f(tL['tau_n'],1)}° / {f(tM['tau_n'],1)}° (출처 {tL['tau_n_source']} / {tM['tau_n_source']}) |")
A(f"| coverage.csv | 판독 기대치 | 지붕 커버리지 {pct(cL['R4_roof_coverage'])} / {pct(cM['R4_roof_coverage'])} → 미판정 상한 ≈ {pct(cL['R4_undetermined_upper'])} / {pct(cM['R4_undetermined_upper'])} |")
A(f"| 면별 충돌 비율(편향) | 판독 검증 기준 | 지붕 충돌 비율 {pct(cfl('L','biased','roof'))} / {pct(cfl('M','biased','roof'))}; 면별 값은 `lod2_faces_*_biased.csv` |")
A(f"| 면별 충돌 비율(정상) | 다듬기 기대 자리 | 지붕 충돌 비율 {pct(cfl('L','nominal','roof'))} / {pct(cfl('M','nominal','roof'))}; 면별 값은 `lod2_faces_*_nominal.csv` |")
A(f"| stats의 연직 m(편향) | 보정 이동량 기대치 | m2_v = {f(tol['L']['biased']['m2_v'])} / {f(tol['M']['biased']['m2_v'])} m |")
A(f"| compare_L_vs_M | arm 구성 | run_both_priors = {f(x['R5_run_both_priors'])} (τ 상대차 {pct(x['R5_values']['rel_diff_tau'])}, 지붕 충돌 상대차 정상 {pct(x['R5_values']['rel_diff_roof_conflict']['nominal'])}·편향 {pct(x['R5_values']['rel_diff_roof_conflict']['biased'])}) |")
A(f"| 정합 경고 | 착수 조건 | 경고 L: {f(cL['registration_warning'])}, M: {f(cM['registration_warning'])} |")
A("")
A("진행 규칙 판정:")
A("")
for p in cm.PRIORS:
    pp = checks["per_prior"][p]
    A(f"- {KO[p]}: R1 registration_ok={f(pp['R1_registration_ok'])}, R2 bias_verified={f(pp['R2_bias_verified'])}, R3 tolerance_source={pp['R3_tolerance_source']} (τ_data>2τ_spec: {f(pp['R3_tau_data_gt_2x_spec'])}), R4 지붕 커버리지={pct(pp['R4_roof_coverage'])} (미판정 상한 {pct(pp['R4_undetermined_upper'])}), R6 conflict_sane={f(pp['R6_conflict_sane'])}, 벽면 충돌 비슷(|Δ|≤0.10)={f(pp['wall_conflict_similar'])}.")
A(f"- 공통: R5 run_both_priors={f(x['R5_run_both_priors'])}, s_L<s_M={f(x['s_L_lt_s_M'])}, 커버리지 차 5%p 이내={f(x['coverage_within_5pp'])}. 모두 초록(R1·R2·R6 양 prior): {f(checks['all_green'])}.")
A("")
A("stage2_config_L.json / stage2_config_M.json 내용은 `out/`에 있으며 뷰어 패널 6에 그대로 표시된다.")
A("")
A(f"<!-- END {R['task_id']} -->")
(cm.OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[-12:]))
rc.write()
