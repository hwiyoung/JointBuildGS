# 원사진 관측과 DA3 target 불일치 — 고정 A–F 사례 검토

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- scientific_verdict: null
- 상태: `INPUT_CASE_REVIEW_COMPLETE / MODEL_COMPARISON_PARTIAL_FIRST6`
- 2026-09-11 08:30 KST; 본 학습의 config·입력·source·문턱 변경 없음

**사진에서 표면이 보인다는 것과 영상 파생 depth가 그 표면의 높이를 맞힌다는 것은 별개다.** P1의 A·B 포장면은 실제 사진에서 타일 무늬와 이음선이 보이지만, 같은 참조점에 대응한 DA3 목표가 UAS보다 약2.4–2.7m 높다. A에서 현재 국소 규칙은 관측 prior를 제거하고 이 DA3 목표를 유지한다. 첫 .005 비교에서 기존 G가 보존한 A의 근접 표면을 LC가 잃은 반면, C의 기존 회복과 F의 기존 보존은 LC에서도 유지됐다. 이 공존을 하나의 성공/실패 사례로 축약하지 않는다.

## 선택과 계산의 계보

위치는 [기존 공간 진단](../geogs_p1p2p3_v1/DA3_REFINEMENT_SPATIAL_RESULTS_ko_v1.md)의 A–F 2m 타일이다. 각 지정 DA3 편차·Anchor 상태 cohort의 점 수가 가장 많은 격자를 고른 과거 사후 진단이며, 이번 LC 결과를 보기 전에 정해진 위치를 그대로 재사용했다. 코드가 같은 max-count 선택·좌표·점 수와 과거 CSV6조건의 일치를 다시 확인했다. 모집단 대표 사례 또는 독립 표본은 아니다.

각 타일에서 strict 관측 참조점이 가장 많은 학습 사진을 선택하고 동률은 사진명 사전순으로 정했다. LC/G의 최종 결과나 잔차 크기로 사진을 선택하지 않았다. 선택된 참조점의 투영 bbox에64pixel context를 더하고 원 RGB crop을 별도로 저장했다. 전체 사진·표시 overlay는 위치 설명이며, 원 crop은 재저장 후 pixel이 정확히 같은지 검사했다.

봉인 main input binding→manifest→camera/RGB/prior/DA3 파일의 SHA를 확인했다. 원 DA3 depth를 기존 nearest raster 방식으로 표본화하여 camera-Z 및 world-Z 잔차를 다시 계산했고, 저장된 strict per-view 배열과 절대오차2e-5m 이내에서 모두 일치했다. 카메라 역투영도 원 XYZ와1e-8m 이내에서 일치했다. 이것은 계산 일관성 검증이며 pose·절대 datum·물리적 가시성 인증이 아니다. Prior는 기존 반픽셀 ray 관례를 상속한다. 원 depth/pose를 GT로 보정하지 않았다.

## 실제 사진 검토와 서로 다른 분모

6개 사진/깊이 figure와 별도 원 crop6개를 실제 열어 검토했다. 아래의 ‘보임’은 제한된 사진 판독이며 공식 O/X 라벨 또는 모든 참조점의 가시성 인증이 아니다.

| 사례 | Local XY 타일 하한(m) | 전체 cohort / 선택 사진 strict점 | 사진에서 확인한 내용 | 전체 cohort의 뷰median 편차 / 선택 사진 편차 중앙값(m) |
|---|---|---:|---|---:|
| A/P1 | −12, 4 | 749 / 749 | 곡선 지붕 앞의 노출된 포장면. 타일과 이음선이 보이고 표시 patch 위의 큰 가림은 보이지 않음 | +2.440 / +2.440 |
| B/P1 | −6, −18 | 712 / 712 | 광장 포장면. 타일·이음선과 인접 작은 물체가 보이며 patch는 노출됨 | +2.685 / +2.685 |
| C/P2 | 120, 92 | 663 / 663 | 지붕 식재/피복면과 주변 난간·설비가 보임. DA3가 해당 UAS 높이에 가까움 | +.396 / +.252 |
| D/P2 | 110, 112 | 744 / 720 | 입면 옆 어두운 포장 띠의 패턴이 구별됨. 그림자·입면 인접으로 A/B보다 해석이 제한됨 | +1.715 / +2.530 |
| E/P3 | −34, −36 | 345 / 200 | 나뭇가지·수관이 보이며 어느 참조 표면이 직접 보이는지 불명확. 명확한 DA3 오류 사례로 판정하지 않음 | −3.435 / −3.015 |
| F/P3 | −28, 0 | 690 / 682 | 곡선 금속 지붕과 줄무늬가 보임. 선택 사진은 전체 뷰median보다 목표가 가까움 | +1.675 / +.337 |

편차는 DA3 target world-Z−UAS world-Z다. A/B는각1뷰이므로 다중뷰 일관성 증거가 아니다. D/E/F는 전체 cohort와 선택 사진의 점 수 및 요약값이 다르다. E의 식생 가림·여러 표면 문제, F의 단일뷰와 뷰median 차이를 삭제하거나 동일한 오류율로 묶지 않는다. Camera-Z 차이의 부호는 world-Z와 다르며 원 CSV에 두 값을 구분한다.

| 사례 | 선택 학습 사진 / image_id / camera_id | 원 crop bbox |
|---|---|---|
| A | `DJI_20241217084553_0100_D.JPG` /91/1 | `[908,582,1071,746]` |
| B | 동일 사진 /91/1 | `[694,397,857,559]` |
| C | `DJI_20241217084505_0076_D.JPG` /67/1 | `[894,843,1065,1013]` |
| D | `DJI_20241217091249_0147_D.JPG` /337/1 | `[1076,478,1233,638]` |
| E | `DJI_20241217084713_0140_D.JPG` /131/1 | `[779,191,943,353]` |
| F | `DJI_20241217084557_0102_D.JPG` /93/1 | `[1243,747,1400,914]` |

## 같은 픽셀에서 본 동결 상보 규칙

아래 값은 **선택 사진의 참조점 투영 표본**에서 계산했다. 같은 raster pixel이 여러 참조점에 반복될 수 있으므로 전체 학습 pixel 평균·면적 평균으로 해석하지 않는다. 두 source가 모두 유효한 점에서 `a=clip((|DP−DV|−.5)/1.5,0,1)`이고 `(prior,visual)=(1−a,a)`다. Single-valid는유효 source배율1이다.

| 사례 | both-valid / visual-only | both-valid 평균 a | prior 유효점 평균 배율 | visual 유효점 평균 배율 |
|---|---:|---:|---:|---:|
| A | 749 / 0 | 1.0000 | 0 | 1 |
| B | 712 / 0 | .2604 | .7396 | .2604 |
| C | 657 / 6 | 1.0000 | 0 | 1 |
| D | 720 / 0 | 1.0000 | 0 | 1 |
| E | 194 / 6 | .6767 | .3233 | .6864 |
| F | 681 / 1 | .00945 | .99055 | .01091 |

A와 D에서는 prior의 camera-Z가 UAS에 가깝고 DA3가 더 크게 어긋나지만 불일치가 커서 a=1이다. C도 a=1이지만 이곳은 DA3가 UAS에 더 가깝다. 따라서 같은 큰 불일치가 어느 source가 맞는지 구분하지 못한다. B에서는두 target이 UAS보다 높은 방향이고 서로 차이가 작아 prior 가중이 더 남는다. F에서는선택 사진의 두 target이 가까워 visual 감독 대부분을 줄인다. 이 입력 정책 관측은 최종 손상의 단독 원인 또는 학습 전체의 실현 gradient 비중을 뜻하지 않는다.

## 첫 .005 여섯 조건의 같은 위치 결과

아래는 **역사적 전체 case 참조점**을 분모로 한 raw512/거리`<.5m` 근접률이다. 선택 사진 subset만 집계한 별도 행도 CSV에 보존했다. 정확도·면적·시간적 유효성 또는 독립 반복을 뜻하지 않는다.

| 사례 | native G→LC 근접률 (%) | native 수정 / 손상 | release G→LC 근접률 (%) | release 수정 / 손상 |
|---|---:|---:|---:|---:|
| A | 95.327→0 | 0 /714 | 91.589→0 | 0 /686 |
| B | 98.596→98.736 | 10 /9 | 94.663→94.382 | 38 /40 |
| C | 100→100 | 0 /0 | 100→100 | 0 /0 |
| D | 68.683→68.145 | 88 /92 | 13.978→0 | 0 /104 |
| E | 0→0 | 0 /0 | 2.319→0 | 0 /8 |
| F | 100→100 | 0 /0 | 100→100 | 0 /0 |

A는원래 Anchor-near이고 G가 유지한 근접점714/686개를 LC가 추가로 잃었다. C는Anchor-far663개를 기존 G가 이미 모두 회복했으며 LC도 이를 유지했다. B는작은 순변화 속에 수정·손상이 공존한다. D native도88개 회복과92개 손상이 함께 있다. E의0→0은동일 형상이 아니라 문턱을 넘는 수정이 없다는 뜻이다. F는높은 뷰median 편차에도 유지되는 반례이며 선택 사진은가까운 target을 가진다. 기존 성과를 새 방법의 추가 기여로 계산하지 않는다.

이 표는 첫 .0056개만 사용한 명시적 부분 비교다. 전체18개 평가 후 같은 사례/사진/원본 ID를 고정한 전체 표를 추가하며, 이 부분 결과로 문턱·조건을 바꾸지 않는다.

## 재현·검증과 한계

설정은 [photo_target_diagnostic_v2.json](../../../../configs/phd/local_complementary_refinement_v1/photo_target_diagnostic_v2.json)이며 실행은 `run_photo_target_audit_v2.sh`와 `run_photo_case_summary_v2.sh`다. 원사진 진단은 기존 입력/strict 진단만 읽고 모델 결과는 읽지 않았다. 모델 비교는 별도 완료 평가 attempt와 정확한 원본 ID/XYZ의 교차 일치를 검사한다. 두 실행 모두 Docker CPU2/RAM4GiB/no swap/network none이며 원자료는읽기 전용이다. 직전 MemAvailable=63,957,884kB였고 P3 학습과겹쳤다.

외부 task root는 [resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml)에 있다.

- 사진/target audit: `main_v2/photo_target_audit/attempt_20260910T232336_211760Z/`; receipt SHA256 `45cf8a6fff1d21cfc2b3540b8e537a34d2695f2f0ae97de400d073378f434b9c`.
- 첫6개 case 비교: `main_v2/photo_case_summary/attempt_20260910T232835_852311Z/`; receipt SHA256 `f7fa55ba5cfc01f65abfe1c312d1903f7b30013a2d8aa1c8db28e439a22b89d3`.
- 각 `A_P1` 같은 prefix의 `*_photo_targets.png`, `*_native_crop.png`, `*_points.npz`, `*_pixels.csv`가 원사진·표본을 연결한다. 모델 표는 `all_methods.csv`, `paired_changes.csv`, 입력 규칙은 `selected_photo_policy.csv`다.
- 사진 audit6개 및 부분 모델 사례24행(전체 case/선택 사진 subset 분리)은 PASS했다. 실제 시각 검토는 이 문서에 별도로 기록했다. 최초 옵션 이름 오류는 [issue](ISSUES_ko_v2.md)에 보존했다.

**문제 차별성**은 보이는 영상 정보·그로부터 얻은 depth 품질·기존 구조의 유효성이 서로 다를 수 있다는 것이다. **원인 설명**은 이 불일치와 국소 규칙의 반응 및 결과의 연관까지다. **방법 신규성** 또는 공간 배분의 고유 이득은 입증하지 않는다. **검증 기여**는 보이는 원사진과 틀어진 target을 구분하고, 같은 위치에서 기존 성공·새 손상·보존 반례를 함께 추적한 것이다. 평균 배율 전역 대조·controller replay·반복이 없어 DA3 단독 인과·작은 차이 재현성·일반화는 확정하지 않는다. GT는 평가 전용이며 scientific_verdict는 null이다.
