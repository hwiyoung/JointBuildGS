# P1/P2/P3 다중뷰 소스 후보 평가기 — 실행 계약

- Task: `PHD-SOURCE-CANDIDATE-P1P2P3-v1`
- 사용자 승인: 2026-09-08 현재 대화에서 P1/P2/P3 실행 및 단계별 정량/정성 분석 요청.
- 상태: 개발 검증. `scientific_verdict: null`.
- 정본: `DEC-P1-025`의 두 소스 오류·현재성/기하 권한 분리와 GT separation을 따른다.
  이번 사용자가 승인한 실행 범위는 GS **전 후보 평가기**다. E1–E6, 기존 결과,
  GS 학습 및 scientific verdict를 변경하지 않는다.

## 판단 의미와 단계

1. 후보 입력: 동일한 기존 P1/P2/P3 prism 전체에 2 m XY 셀을 만들고, 소스별
   native point의 dominant local plane을 독립적으로 구성한다. 원행·inlier/outlier
   membership은 보존한다. 평면 적합은 표현용이며 정답성·시효의 증거가 아니다.
   후보가 없거나 혼합/비평면/선형인 셀도 전체 분모에 포함한다.
2. 관측 평가: 원래 undistorted RGB와 원래 K/R/t를 사용한다. 후보에 동일 기준
   픽셀과 동일 영상쌍을 사용하고 native support 밖의 무한 평면 외삽을 제외한다.
   기하로 영상쌍을 선택하고 ZNCC와 변위 후보의 식별성을 측정한다. COLMAP
   PatchMatch 자체를 실행하는 것이 아니라 해당 관측 평가 원리의 별도 구현이다.
3. 소스 판단: 두 유효 후보, 공통 관측, 시차/texture, 여러 영상쌍의 일관된 우세와
   국소 변위 검사를 통과할 때만 IMAGE/PRIOR를 조건부 채택한다. 그 외는 ABSTAIN.
   융합 기하를 검증하지 않았으므로 FUSION은 만들지 않는다. 낮은 영상 지지로
   prior를 자동 채택하지 않는다.

## 자료와 한계

- 입력: matched v5의 원 MVS·Existing ALS와 기존 113/66/157 regional views.
- working CRS EPSG:25832, 기존 scene-local coordinates. 변환을 재적용하지 않는다.
- 중력: Gate-S0에 보존된 terrain-MVS estimate를 읽는다. 상수를 새로 정하지 않는다.
- 정합/카메라는 제공값 고정. 후보 법선 변위 검사는 정합 불확실성의 확률 보정이나
  전역 정합 회복이 아니다. 큰 소스 차이가 실제 변화라는 정답 라벨도 아니다.
- 각 소스 자체의 native-core point-depth는 자기 가림의 모델 가설일 뿐이다.
  대상 영역 MVS를 prior의 정답 가림/빈 공간으로 사용하지 않는다. 전체 장면 외부
  occluder와 실제 현재성이 검증되지 않으므로 결과는 조건부 선택이다.
- 현재 MVS와 RGB는 같은 개발 자료 계보다. 독립 판단/확증 표본으로 부르지 않는다.
- UAS는 세 지역의 후보·관측·판단 산출물 해시를 먼저 고정한 뒤 별도 Docker 단계에서
  평가한다. 평가 전용 경로는 후보 컨테이너에 마운트하지 않는다.
- UAS header EPSG:32632와 working EPSG:25832의 기존 bridge/수직기준 불확실성이
  있으므로 수치는 보존된 좌표계에서의 reference discrepancy이며 보정된 절대 정확도
  또는 정답 변화율로 승격하지 않는다.

## 정량·정성 산출물

- 후보: native counts, valid/missing/mixed census, 소스 이격·평면 적합 잔차, 두 3D overlay와 단면.
- 관측: 공통 영상쌍/픽셀, NCC, 시차, 후보별 변위 비용곡선, 실제 원영상 crop/warp.
- 판단: IMAGE/PRIOR/ABSTAIN 및 이유, coverage, 고정된 모든 sensitivity 조합.
- 참조 평가: 동일 선택 셀 집합에서 MVS/ALS/선택 기하를 함께 비교하고, 전체 모집
  표본의 값과 혼합하지 않는다. 더 나은 소스 oracle과 regret는 score-only다.
- 정성: 각 상태의 cell_id 첫 사례와, 평가 후 선정하는 명시적 최악 오판/큰 이격 사례.
  성공 사례뿐 아니라 관측 부족·오판·유보와 재현 한계를 보인다.

## Figure contract

Standalone scientific PNG/PDF figures and repository Markdown report; static Matplotlib
is used under the repository's reproducible scientific-artifact workflow.
Comparison bars: three regions × common pipeline stages, zero baseline, exact counts.
Maps: source geometry heights/discrepancy and categorical actions on the same fixed XY cells.
Profiles: normal-offset metres × multiview cost, with source identity and support counts.
Cases: source-native 3D/cross-section plus actual paired RGB/warps and traceable IDs.
Palette: blue MVS, orange ALS, gray abstention/reference; marker/line styles distinguish
sources without relying on color. CSV/JSON retain denominators, reasons and provenance.
No chart implies calibrated confidence or a scientific verdict. Inspect exported images.
