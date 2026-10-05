# 첫 단계 보고서 — PHD-STAGE1-CONF-TOL-CONFLICT-v1

생성: 2026-09-21T14:31:47.145790+00:00 (UTC). `scientific_verdict: null`. 판정 문장은 쓰지 않고 사실만 적는다.

## 1. 입력과 절차 요약

- 장면: GeoGS 저자 예제 15시점(5644×4082, PINHOLE), 대상 건물 `DEBY_LOD2_4959323`. 포즈는 진단 실험 `sparse_txt`(images.bin에서 생성, sparse_lod와 동일)를 그대로 썼다.
- MVS 깊이: P0 공통 기반 COLMAP `patch_match_stereo` geometric-consistency 깊이/법선(1024×741, 카메라 Z m). 시점 영상 크기로 재표본: 깊이 = 유효 이웃 가중 이중선형, 마스크 = 최근접. 픽셀 중심 +0.5 규약 양쪽 동일. 일관 시점 수: consistency graph 파일 0개 → **nviews 배열 없음**, 신뢰도 = geometric 필터 통과 여부(prior 미사용).
- prior M(LoD2): 정상 = 저자 제공 LoD2Depth 배열(`lod2_prior/raw_depth`), 편향 = 진단 실험 `B+1.0/scene/lod2_biased.obj`(복구 CityGML 전 정점 +1.000 m, 면 동일 확인)를 같은 `LoD2Depth/main.py`로 렌더. 법선은 복구 메시 렌더의 `raw_normal`(정상은 제공 배열에 법선이 없음).
- prior L(ALS): 바이에른 ALS 원시 타일 `phase-payloads/p0-audit/data/raw/als/691_5336.laz`(LAS 1.2, GPS 시각 기준 취득 2022-02-27), 대상 건물 XY 외접 사각형 ±15 m 크롭, 클래스 2(지면)·6(건물)만 120,333점(밀도 16.0점/m²), 2.5D Delaunay TIN 240,629삼각형 → 같은 `LoD2Depth/main.py` 광선 추적. 편향 = 전 점 z+1.0 m 후 같은 절차. **대체(GT 간추림) 사용 안 함.** 높이 기준: LoD2와 동일하게 −604+45.66 m 상수 이동.
- 지붕/벽면/지면 구분: 정상 복구 LoD2 메시(건물 210동, 다각형 3918개)를 시점별 다각형 id로 렌더. 대상 건물 다각형 {'roof': 6, 'wall': 12, 'ground': 1} (규칙: GroundSurface=지면, |n_z|>0.2=지붕, 이하=벽면). L의 '지면' = 건물이 아닌 픽셀 중 ALS TIN 깊이가 있는 픽셀; M은 지형이 없어 지면 NA. 다른 건물 픽셀은 집계 제외.
- 상수: 일관 시점 문턱 3(미사용), k=2.5, 이상치 3s, τ_spec L=0.12 m / M=1.0 m, τ_n 기본 10°. 잔차 r = MVS 깊이 − prior 깊이(카메라 Z, 표에서 `ray_depth_camZ`), 지붕 연직 잔차 = r × |n·d|/|n_z| (n = 그 픽셀 LoD2 면의 단위 법선, d = 비정규화 세계 광선 R^T(x,y,1); 수평면이면 r×|d_z|와 같음. 표에서 `vertical`; +는 prior가 MVS보다 높음). 발주서의 '광선 방향의 연직 성분' 환산을 경사면까지 일반화한 것으로, 수평면 식 r×|d_z|만 쓰면 카메라를 향한 경사 지붕을 스치듯 보는 시점에서 연직 값이 절반 이하로 줄어든다(수평면 식의 값은 `checks`의 vertical_conversion에 기록).
- τ와 충돌 문턱의 기준 영역: 지붕(두 바퀴 m2, s2). 충돌 = 신뢰도 1 ∧ prior 마스크 1 ∧ |r − m2_정상,영역| > 3·s2_정상,영역 (영역별 정상 조건 값). τ_n = m2_n + 2.5·s2_n(부호 없는 각도라 중앙값 보정; 문자 그대로의 2.5·s2_n도 기록).

## 2. 개요표 (전체 시점 합산, 지붕 기준)

| 항목 | L(ALS) 정상 | L(ALS) 편향+1.0 | M(LoD2) 정상 | M(LoD2) 편향+1.0 |
|---|---:|---:|---:|---:|
| τ_data (m) | 0.050 | 0.359 | 0.111 | 0.323 |
| τ_spec (m) | 0.120 | 0.120 | 1.000 | 1.000 |
| τ (m) | 0.120 | 0.359 | 1.000 | 1.000 |
| τ 출처 | spec | data | spec | spec |
| τ_n (°) | 10.339 | 11.420 | 3.289 | 3.098 |
| m 지붕 1차 (m) | -0.027 | 1.256 | 0.013 | 1.145 |
| s 지붕 1차 (m) | 0.025 | 0.195 | 0.051 | 0.170 |
| m2 지붕 2차 (m) | -0.024 | 1.268 | 0.012 | 1.144 |
| s2 지붕 2차 (m) | 0.020 | 0.144 | 0.044 | 0.129 |
| 이상치 비율 | 0.1439 | 0.2114 | 0.1084 | 0.2037 |
| 연직 m2 지붕 (m) | -0.019 | 0.983 | 0.009 | 0.882 |
| 지붕 픽셀 수 | 35,493,333 | 35,507,055 | 35,508,890 | 35,508,893 |
| 커버리지 지붕 | 95.5% | 95.5% | 95.5% | 95.5% |
| 커버리지 벽면 | 88.5% | 88.5% | 88.5% | 88.2% |
| 커버리지 지면 | 74.7% | 74.7% | NA | NA |
| 커버리지 전체(지붕+벽면) | 90.8% | 90.8% | 90.8% | 90.7% |
| 충돌 비율 지붕 | 17.2% | 98.3% | 12.4% | 99.0% |
| 충돌 비율 벽면 | 13.8% | 15.8% | 24.4% | 23.6% |
| 충돌 비율 지면 | 50.8% | 97.5% | 0.0% | 0.0% |
| 충돌 비율 전체(지붕+벽면) | 14.9% | 44.3% | 20.3% | 50.3% |
| m2/s2 벽면 (m) | 0.234/0.236 | 0.265/0.253 | 0.285/0.097 | 0.271/0.092 |
| m2/s2 지면 (m) | -0.065/0.055 | 1.093/0.234 | NA/NA | NA/NA |

진단 실험 N 조건(GeoGS 출력 vs GT, 부호 최근접 거리): 지붕 중앙값 0.225 m, NMAD 0.062 m; 벽면 0.114 / 0.225 m. 이 값은 MVS−prior 잔차와 다른 양이므로 `compare_L_vs_M.csv`에 별도 열로 나란히 두었다.

## 3. 정합 점검과 편향 검증

- L(ALS) 정상: |m2|=0.024 m, s2=0.020 m → R1 registration_ok = 아니오. **경고: 정상 조건 지붕 |m2|=0.024 m ≥ s2=0.020 m: 계통 편차**
- L(ALS) 편향: 연직 m2 = 0.983 m (정상 -0.019 m, 차 1.002 m, 1.0 m에서 0.017 m) → R2 bias_verified(0.8~1.2 m) = 예.
- M(LoD2) 정상: |m2|=0.012 m, s2=0.044 m → R1 registration_ok = 예.
- M(LoD2) 편향: 연직 m2 = 0.882 m (정상 0.009 m, 차 0.873 m, 1.0 m에서 0.118 m) → R2 bias_verified(0.8~1.2 m) = 예.
- 편향 파일 검증(7절 함정 1): 편향 LoD2 렌더 − 복구 정상 렌더의 지붕 연직 차 중앙값 = -1.000 m (기대 -1.0 m, prior가 올라가면 깊이는 준다). 진단 실험의 B+1.0 `lod2_prior`는 실행 시점에 아직 생성되지 않아 같은 OBJ·같은 스크립트로 재생성했다.
- 저자 제공 LoD2 배열 − 복구 메시 렌더의 지붕 연직 차 중앙값 = -0.122 m. 정상 M은 제공 배열, 편향 M은 복구 메시(+1.0)이므로 이 메시 출처 차이가 편향에 동반된다.
- 연직 환산 비교(사실): 수평면 식 r×|d_z|만 쓰면 편향 조건 지붕 연직 m2가 L 0.445 / M 0.406 m로 나온다(면 법선 식: 0.983 / 0.882 m).
- MVS 단위·스케일 검증(7절 함정 3): 시점별 median(MVS − 제공 LoD2) = -0.045 ~ +0.206 m (전 건물 픽셀, 8픽셀 보폭). 수 m 차이 없음.
- 면 id 렌더와 공식 main.py 깊이의 일치: 최대 |Δ깊이| = 0.00e+00 m, 히트 마스크 불일치 픽셀 최대 0개 (Open3D 0.19.0).
- 정합 경고 후속 사실(2026-09-22): 이 건물 위치의 GCG2016 준지오이드 = 45.660 m(이중선형)로 사용한 상수 45.66 m와 1 mm 안에서 같다. L의 지붕 연직 m2는 15시점 모두 음(−0.011~−0.031 m)인 블록 이동이며, M은 대부분 양(+0.004~+0.037 m)이다. 즉 2.4 cm는 높이 기준 상수 오류가 아니라 2022 ALS 블록과 2024 영상 프레임 사이의 실제 어긋남이다(`provenance/registration_check.json`).

## 4. 정상 조건 지붕 충돌의 위치 사실 (4-8절)

- L(ALS): 지붕 신뢰도 픽셀 35,493,333 중 충돌 6,099,083 (17.2%); 면 경계 40픽셀 이내 53.2%; MVS가 prior보다 가까움(prior 지붕 위 구조물: 도머·굴뚝·설비 후보) 83.4%, 먼 쪽 16.6%.
- M(LoD2): 지붕 신뢰도 픽셀 35,508,890 중 충돌 4,413,600 (12.4%); 면 경계 40픽셀 이내 57.0%; MVS가 prior보다 가까움(prior 지붕 위 구조물: 도머·굴뚝·설비 후보) 34.7%, 먼 쪽 65.3%.
- 면별 충돌 비율·잔차 중앙값은 `lod2_faces_{prior}_{cond}.csv`; 도머·굴뚝·처마와의 대조는 뷰어 패널 2·3에서 사람이 기록한다(자동 판정 없음).

## 5. L과 M 비교 (4-8절)

- τ: L 0.120 m vs M 1.000 m (상대차 88.0%). 지붕 충돌 비율 상대차: 정상 27.7%, 편향 0.7%. → R5 run_both_priors = 예.
- s2_L < s2_M: 예 (0.020 vs 0.044 m). 지붕 커버리지 L 95.5% vs M 95.5% (5%p 이내: 예); 벽면 L 88.5% vs M 88.5%.
- 편향 조건에서 지붕 충돌이 켜진 비율: L 98.3%, M 99.0% (정상: L 17.2%, M 12.4%). 벽면: L 13.8%→15.8%, M 24.4%→23.6%. L의 벽면 잔차는 TIN 브리징 삼각형이라 참고값이다.
- 지붕 잔차 분포 분위수는 `compare_L_vs_M.csv`(p05~p95, ray/vertical)와 뷰어 패널 4의 히스토그램에 있다.

## 6. 그림·파일 경로

- 시점별: `out/{prior}/{cond}/{view}_res.npy|png`, `_resv.npy`, `_conflict.npy|png`, `_region.npy`(정상 폴더); 신뢰도: `out/conf/{view}_conf.npy|png` (prior와 무관하므로 한 곳에 둠).
- 면 속성: `out/lod2_faces_{prior}_{cond}.csv|ply`, 위에서 본 렌더 `out/figures/faces_{prior}_{cond}_conflict.png`. ALS 점: `out/als_points_{cond}.ply`, `out/figures/als_points_{cond}_conflict.png`.
- 표: `out/stats.csv`, `out/tolerance.json`, `out/coverage.csv`, `out/conflict.csv`, `out/compare_L_vs_M.csv`, `out/checks.json`. 설정: `out/stage2_config_L.json`, `out/stage2_config_M.json`. 뷰어: `out/viewer.html` (+`viewer_png/`, `viewer_data/`), `out/viewer_README.md`.
- 실행 기록: `logs/*.log`, `logs/*.host_receipt.json`, `logs/receipt_*.json`, `logs/issues.jsonl`, `provenance/*.json`.

## 7. 문제와 예외

- GEOM-001 (RESOLVED): First ALS TIN kept only 15,481 of 120,333 points: scipy/qhull Delaunay on raw EPSG:25832 coordinates (~5e6 m) dropped most points as coplanar. Fixed by mean-centring XY before Delaunay; the two ALS renders started on the wrong TIN were killed (logs kept as *.killed_wrong_tin.log) and rerun. LoD2 outputs of the first run were byte-identical and unaffected.
- VERT-001 (RESOLVED): First analysis converted roof residuals to vertical with the horizontal-plane formula r*|d_z|; on this scene's pitched roofs seen at grazing angles (14-25 deg below horizon) it returned m2_v 0.41-0.45 m for the +1.0 m bias. Replaced by the parallel-plane formula r*|n.d|/|n_z| with the pixel's LoD2 face normal (identical for horizontal faces); the horizontal-formula values are kept in checks.json facts.vertical_conversion for comparison. Analysis container killed and rerun; log kept as analyze.killed_horizontal_vertical_formula.log.
- 일관 시점 수 배열(nviews)은 원천 데이터가 없어 만들지 않았다(문턱 3은 미사용).
- L prior의 벽면 픽셀 잔차는 2.5D TIN의 브리징 삼각형에서 나온 참고값이다. M prior의 지면은 NA다.

## 8. 둘째 단계 반영

| 첫 단계 산출 | 둘째 단계의 자리 | 실제 값 (L / M) |
|---|---|---|
| conf.npy(시점별) | 손실의 픽셀 가중 | `out/conf/{view}_conf.npy` 15개, prior 가중 = (1−conf)×prior 마스크, MVS 가중 = conf×MVS 마스크 (공통) |
| conf.npy | 원반 신뢰도 E | 8000회에 원반 중심을 각 시점에 투영해 conf 평균, 500회마다 갱신 (공통) |
| E | 기울기 배율·불투명도 하한 | E<0.5: lr×0.01, 불투명도 하한 0.5; E≥0.5: 배율 1 (공통) |
| E | 밀집화·가지치기 | prior 출신 E<0.5 동결, 가지치기 기록 (공통) |
| tolerance.json의 τ | 허용 구간·절단 | τ = 0.120 / 1.000 m; 4τ = 0.480 / 4.000 m; 상수 3τ = 0.360 / 3.000 m |
| τ | 초기화 관측 점 선택 | prior 표면 거리 > 0.120 / 1.000 m인 MVS 점만 시드 |
| τ | 판독 문턱 | 이동량 < τ 보존, ≥ τ 보정 (같은 값) |
| τ_n | prior 법선 항 허용 각도 | 10.3° / 3.3° (출처 data / data) |
| coverage.csv | 판독 기대치 | 지붕 커버리지 95.5% / 95.5% → 미판정 상한 ≈ 4.5% / 4.5% |
| 면별 충돌 비율(편향) | 판독 검증 기준 | 지붕 충돌 비율 98.3% / 99.0%; 면별 값은 `lod2_faces_*_biased.csv` |
| 면별 충돌 비율(정상) | 다듬기 기대 자리 | 지붕 충돌 비율 17.2% / 12.4%; 면별 값은 `lod2_faces_*_nominal.csv` |
| stats의 연직 m(편향) | 보정 이동량 기대치 | m2_v = 0.983 / 0.882 m |
| compare_L_vs_M | arm 구성 | run_both_priors = 예 (τ 상대차 88.0%, 지붕 충돌 상대차 정상 27.7%·편향 0.7%) |
| 정합 경고 | 착수 조건 | 경고 L: 예, M: 아니오 |

진행 규칙 판정:

- L(ALS): R1 registration_ok=아니오, R2 bias_verified=예, R3 tolerance_source=spec (τ_data>2τ_spec: 아니오), R4 지붕 커버리지=95.5% (미판정 상한 4.5%), R6 conflict_sane=예, 벽면 충돌 비슷(|Δ|≤0.10)=예.
- M(LoD2): R1 registration_ok=예, R2 bias_verified=예, R3 tolerance_source=spec (τ_data>2τ_spec: 아니오), R4 지붕 커버리지=95.5% (미판정 상한 4.5%), R6 conflict_sane=예, 벽면 충돌 비슷(|Δ|≤0.10)=예.
- 공통: R5 run_both_priors=예, s_L<s_M=예, 커버리지 차 5%p 이내=예. 모두 초록(R1·R2·R6 양 prior): 아니오.

stage2_config_L.json / stage2_config_M.json 내용은 `out/`에 있으며 뷰어 패널 6에 그대로 표시된다.

<!-- END PHD-STAGE1-CONF-TOL-CONFLICT-v1 -->
