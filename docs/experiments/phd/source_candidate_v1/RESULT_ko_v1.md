# P1/P2/P3 다중뷰 소스별 3D 후보 평가기 — 실행 결과

Task `PHD-SOURCE-CANDIDATE-P1P2P3-v1` · 2026-09-08 · 개발 검증 · `scientific_verdict: null`

**평가기 구현과 세 영역 실행은 완료했다. 현재 고정 규칙의 선택 범위는 좁으며, 큰 이격 영역 전반에서 유효 소스를 선택하는 능력은 아직 입증되지 않았다.**

P2에서는 2 m 초과 이격의 선택 36셀 모두 영상 후보가 참조에 더 가까웠다. 반면 전체 선택률은 42/1,317=3.19%이며, 큰 이격에서 prior를 구제한 증거는 없다. P2의 동일 선택 셀에서 영상 단독 대비 평균 거리 감소는 약 9.5 mm이고, P3 유일 prior 선택은 약 6.2 cm 악화했다. 좋은 국소 선택 사례와 넓은 미해결 영역이 함께 존재한다.

## 1. 후보 입력 → 관측 평가 → 소스 판단

| 영역 | 전체 셀 | MVS / ALS 원점 수 | 영상 수 | 두 후보 유효 | 공통 점수 있음 | 관측 최소조건 충족 | IMAGE / PRIOR / ABSTAIN | 전체 선택률 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | 225 | 139,033 / 20,189 | 113 | 150 | 52 | 20 | 0 / 0 / 225 | 0.00% |
| P2 | 552 | 330,679 / 45,986 | 66 | 282 | 270 | 81 | 38 / 3 / 511 | 7.43% |
| P3 | 540 | 865,108 / 52,762 | 157 | 190 | 86 | 25 | 0 / 1 / 539 | 0.19% |

셀은 고정 2 m XY 구획이다. 원점은 모두 보존하고 각 소스에서 국소 dominant plane과 native inlier membership을 독립 구성했다. 한 셀의 단일 평면이 부적합하거나 소스가 없는 경우도 전체 분모에 포함했다.

관측 최소조건은 같은 픽셀·마스크의 영상쌍 3개 이상, 영상 4개 이상, 카메라를 공유하지 않는 쌍 2개 이상이다. 원 K/R/t로 후보 평면의 영상 warp를 만들고 ZNCC 비용을 비교했다. 이 쌍 구성은 통계적 독립 관측을 뜻하지 않는다.

소스 판단은 비용 ≤0.25, 소스 차이 ≥0.05, 쌍별 우세 비율 ≥0.75와 후보 법선 방향 ±0.5/1/2 m 변위 검사를 통과해야 한다. 통과하지 않으면 ABSTAIN이다. 후보가 동등한 경우와 둘 다 불량인 경우도 강제로 선택하지 않는다.

![단계별 전체 분모와 선택 결과](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/00_stage_summary.png)

## 2. 같은 선택 셀에서의 참조 기하 비교

| 영역 | 같은 선택 셀 n | 항상 MVS (m) | 항상 ALS (m) | 선택 결과 (m) | 셀별 oracle (m) | 평균 regret (m) | 명확한 차이에서 정선택 | 참조 차이 ≤0.1 m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | 0 | NA | NA | NA | NA | NA | 0 / 0 (NA) | 0 |
| P2 | 41 | 0.207 | 3.771 | 0.197 | 0.194 | 0.003 | 40 / 41 (97.56%) | 0 |
| P3 | 1 | 0.057 | 0.118 | 0.118 | 0.057 | 0.062 | 0 / 0 (NA) | 1 |

각 셀의 오차는 해당 셀 native candidate inlier와 UAS의 양방향 최근접거리 평균을 절반씩 합한 값이다. 위 표는 **동일한 선택 셀 집합에서 셀별 동일 가중 평균**이다. 선택 영역 평균을 전체 영역 baseline과 비교하지 않는다. Oracle은 UAS에 더 가까운 소스를 사후 선택한 평가 전용 하한이며 학습·판단에 전달되지 않았다.

이 수치는 보존된 좌표에서의 UAS discrepancy다. 점 밀도·결측과 기존 수직기준/정합 불확실성을 포함하므로 보정된 절대 정확도나 실제 변화의 정답률로 해석하지 않는다. 참조 차이 0.1 m 이하 셀은 소스 정선택 비율의 분모에서 뺐다.

| 영역 | 전체 MVS 원점 → 평면 inlier (m) | 전체 ALS 원점 → 평면 inlier (m) | 선택 결과 전체 참조 완전성 @0.5 m |
| --- | --- | --- | --- |
| P1 | 0.167 → 0.224 | 1.190 → 1.444 | 0.00% |
| P2 | 0.213 → 0.237 | 1.515 → 1.795 | 7.09% |
| P3 | 0.246 → 0.375 | 0.222 → 0.557 | 0.07% |

위 원점/inlier 표는 영역 전체의 점 가중 기하 진단이며 앞의 셀 동일 가중 표와 다른 지표다. 특히 P3에서 단일 평면 inlier만 남기면 지지·세부가 사라져 참조 거리가 커진다. 후보 표현 자체의 손실을 선택 모듈의 성과로 숨길 수 없다.

## 3. 큰 소스 이격과 미해결 영역

| 영역 | 평면 높이 이격 | 두 유효 후보 셀 | 공통 점수 셀 | 선택 셀 | IMAGE / PRIOR | 선택률 | 정선택 / 명확 차이 | regret (m) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | ≥1 m | 75 | 23 | 0 | 0 / 0 | 0.00% | 0 / 0 | NA |
| P1 | <1 m | 75 | 29 | 0 | 0 / 0 | 0.00% | 0 / 0 | NA |
| P2 | ≥1 m | 145 | 143 | 36 | 36 / 0 | 24.83% | 36 / 36 | 0.000 |
| P2 | <1 m | 137 | 127 | 5 | 2 / 3 | 3.65% | 4 / 5 | 0.025 |
| P3 | ≥1 m | 19 | 6 | 0 | 0 / 0 | 0.00% | 0 / 0 | NA |
| P3 | <1 m | 171 | 80 | 1 | 0 / 1 | 0.58% | 0 / 0 | 0.062 |

큰 이격은 추정 중력 방향의 두 평면 중심 차이로 정의한 진단 구분이다. 실제 변화 라벨이 아니며, 유효한 두 후보가 없는 셀은 첫 표에 남아 있다.

| 영역 | 2 m 초과 이격 선택 셀 | IMAGE / PRIOR | 정선택 / 명확 차이 | 같은 셀 MVS (m) | 같은 셀 ALS (m) |
| --- | --- | --- | --- | --- | --- |
| P1 | 0 | 0 / 0 | 0 / 0 | NA | NA |
| P2 | 36 | 36 / 0 | 36 / 36 | 0.205 | 4.253 |
| P3 | 0 | 0 / 0 | 0 / 0 | NA | NA |

| 영역 | 참조상 더 가까운 소스 | 차이 >0.1 m 셀 | 맞게 선택 | 잘못 선택 | 보류 |
| --- | --- | --- | --- | --- | --- |
| P1 | MVS | 75 | 0 | 0 | 75 |
| P1 | ALS | 2 | 0 | 0 | 2 |
| P2 | MVS | 153 | 37 | 0 | 116 |
| P2 | ALS | 19 | 3 | 1 | 15 |
| P3 | MVS | 13 | 0 | 0 | 13 |
| P3 | ALS | 39 | 0 | 0 | 39 |

위 oracle 분해는 좋은 후보가 존재해도 관측 평가·판단에서 얼마나 놓치는지 보여준다. 전체 참조점에 대한 완전성은 `run/evaluation/summary.json`의 `selected_full_target_cell_constrained_completeness`에 별도로 기록했으며, 보류 셀의 모든 참조점을 미복원으로 계산한다.

## 4. 판단 이유와 고정 규칙 민감도

| 영역 | 판단 이유 | 셀 수 | 전체 비율 |
| --- | --- | --- | --- |
| P1 | INSUFFICIENT_COMMON_PAIRS | 129 | 57.33% |
| P1 | CANDIDATE_MISSING_OR_INVALID | 75 | 33.33% |
| P1 | SOURCES_NOT_DISTINGUISHABLE | 19 | 8.44% |
| P1 | INSUFFICIENT_DISTINCT_VIEWS | 1 | 0.44% |
| P1 | BOTH_SOURCES_POOR_IMAGE_SUPPORT | 1 | 0.44% |
| P2 | CANDIDATE_MISSING_OR_INVALID | 270 | 48.91% |
| P2 | INSUFFICIENT_COMMON_PAIRS | 200 | 36.23% |
| P2 | PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL | 41 | 7.43% |
| P2 | SOURCES_NOT_DISTINGUISHABLE | 39 | 7.07% |
| P2 | INSUFFICIENT_DISTINCT_VIEWS | 1 | 0.18% |
| P2 | INCONSISTENT_PAIRED_SOURCE_PREFERENCE | 1 | 0.18% |
| P3 | CANDIDATE_MISSING_OR_INVALID | 350 | 64.81% |
| P3 | INSUFFICIENT_COMMON_PAIRS | 153 | 28.33% |
| P3 | SOURCES_NOT_DISTINGUISHABLE | 16 | 2.96% |
| P3 | INSUFFICIENT_DISTINCT_VIEWS | 11 | 2.04% |
| P3 | INCONSISTENT_PAIRED_SOURCE_PREFERENCE | 4 | 0.74% |
| P3 | PROFILE_INSUFFICIENT_COVERAGE | 2 | 0.37% |
| P3 | BOTH_SOURCES_POOR_IMAGE_SUPPORT | 2 | 0.37% |
| P3 | PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL | 1 | 0.19% |
| P3 | INSUFFICIENT_DISJOINT_PAIRS | 1 | 0.19% |

| 영역 | 사전 고정 조합 수 | 선택 셀 최솟값–최댓값 | regret 최솟값–최댓값 (m) |
| --- | --- | --- | --- |
| P1 | 27 | 0–0 | NA–NA |
| P2 | 27 | 33–42 | 0.000–0.003 |
| P3 | 27 | 1–3 | 0.050–0.062 |

민감도는 UAS 접근 전에 고정한 비용 0.15/0.25/0.35 × 차이 0.02/0.05/0.10 × 우세비율 0.67/0.75/1.0의 27조합이다. 사후 참조 성능으로 최적 조합을 선택하지 않았다. 전체 조합별 coverage·risk·regret는 원 CSV에 있다.

## 5. 정성 자료와 사례 선정

각 영역에 전체 단계 지도, 원점군 3D·단면, 실제 원영상 crop, 같은 기준 픽셀로 재생성한 후보별 warp 및 변위 비용곡선을 제공한다. 재생성된 영상쌍 비용은 저장한 값과 1e-6 허용차로 대조한다. 점군 표시용 다운샘플은 판단·수치 평가에 쓰지 않았다.

사례는 상태별 첫 cell_id, 점수가 존재하는 첫 ABSTAIN, 최대 평면 이격을 사용한다. 최대 accepted regret 사례만 참조 평가 후 선택한 명시적 실패 진단이다. 없는 선택 상태를 성공 사례로 만들지 않았다.

### P1

![P1 단계별 결과](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_stage_overview.png)

셀 16의 원영상에는 반복되는 줄무늬와 가로 경계가 보인다. MVS/ALS 높이 차이는 약 2.247 m이고 UAS 거리는 0.224/1.968 m지만, 표시한 한 patch의 비용은 MVS 0.590 / ALS 0.538로 prior 쪽이 오히려 낮다. 전체 영상쌍 조건에서는 서로 다른 영상 수가 부족해 보류했다. 이 사례는 단일 patch 순위만으로 더 유효한 기하를 결정할 수 없음을 보여준다. 반복 무늬가 오류의 유일한 원인이라는 뜻은 아니다.

[P1_case_0000 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0000.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0000.pdf)

셀 0: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 0.314 m / ALS 1.465 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_ABSTAIN`. 공통 점수가 없어 영상 비교를 만들지 않았다.

[P1_case_0016 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0016.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0016.pdf)

셀 16: **ABSTAIN** · `INSUFFICIENT_DISTINCT_VIEWS`. MVS 0.224 m / ALS 1.968 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_SCORED_ABSTAIN`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P1_case_0045 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0045.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P1_case_0045.pdf)

셀 45: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 0.491 m / ALS 1.814 m / regret NA m.

선정 규칙: `PRE_REFERENCE_MAX_ABSOLUTE_SOURCE_HEIGHT_GAP`. 공통 점수가 없어 영상 비교를 만들지 않았다.

### P2

![P2 단계별 결과](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_stage_overview.png)

셀 5에서는 두 native 표면이 약 4.763 m 떨어져 있고 목표 영상에서 투영 위치도 분리된다. MVS warp가 anchor의 밝기 구조를 더 잘 재현하며 법선 방향 변위 0 부근에서 비용이 낮다. 표시 patch 비용은 0.050/0.334, UAS 거리는 0.263/4.879 m로 영상 선택을 지지한다. 다른 셀의 prior 선택과 최대 regret 오판도 아래에 함께 제시한다.

[P2_case_0005 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0005.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0005.pdf)

셀 5: **IMAGE** · `PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL`. MVS 0.263 m / ALS 4.879 m / regret 0.000 m.

선정 규칙: `PRE_REFERENCE_FIRST_IMAGE`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P2_case_0120 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0120.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0120.pdf)

셀 120: **PRIOR** · `PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL`. MVS 0.211 m / ALS 0.107 m / regret 0.000 m.

선정 규칙: `PRE_REFERENCE_FIRST_PRIOR`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P2_case_0000 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0000.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0000.pdf)

셀 0: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 0.475 m / ALS 0.443 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_ABSTAIN`. 공통 점수가 없어 영상 비교를 만들지 않았다.

[P2_case_0004 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0004.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0004.pdf)

셀 4: **ABSTAIN** · `INSUFFICIENT_COMMON_PAIRS`. MVS 0.180 m / ALS 4.163 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_SCORED_ABSTAIN`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P2_case_0139 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0139.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0139.pdf)

셀 139: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 6.656 m / ALS 1.388 m / regret NA m.

선정 규칙: `PRE_REFERENCE_MAX_ABSOLUTE_SOURCE_HEIGHT_GAP`. 공통 점수가 없어 영상 비교를 만들지 않았다.

[P2_case_0195 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0195.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P2_case_0195.pdf)

셀 195: **IMAGE** · `PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL`. MVS 0.242 m / ALS 0.118 m / regret 0.124 m.

선정 규칙: `POST_REFERENCE_MAX_ACCEPTED_REGRET_DIAGNOSTIC`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

### P3

![P3 단계별 결과](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_stage_overview.png)

전체 540셀 중 350셀은 두 후보의 단일 평면 표현 조건을 통과하지 못했다. 유일한 prior 선택 셀 43의 UAS 거리는 MVS 0.057 m, ALS 0.118 m다. 이는 prior 구제의 성공 사례로 해석할 수 없으며, 관측 적합도 우세와 기하 거리 개선이 일치하지 않을 수 있음을 보여준다.

[P3_case_0043 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0043.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0043.pdf)

셀 43: **PRIOR** · `PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL`. MVS 0.057 m / ALS 0.118 m / regret 0.062 m.

선정 규칙: `PRE_REFERENCE_FIRST_PRIOR, POST_REFERENCE_MAX_ACCEPTED_REGRET_DIAGNOSTIC`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P3_case_0000 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0000.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0000.pdf)

셀 0: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 0.436 m / ALS 0.539 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_ABSTAIN`. 공통 점수가 없어 영상 비교를 만들지 않았다.

[P3_case_0006 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0006.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0006.pdf)

셀 6: **ABSTAIN** · `INSUFFICIENT_COMMON_PAIRS`. MVS 0.077 m / ALS 0.105 m / regret NA m.

선정 규칙: `PRE_REFERENCE_FIRST_SCORED_ABSTAIN`. 저장된 실제 영상쌍과 warp 점수를 재현했다.

[P3_case_0498 PNG](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0498.png) · [PDF](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/P3_case_0498.pdf)

셀 498: **ABSTAIN** · `CANDIDATE_MISSING_OR_INVALID`. MVS 2.907 m / ALS 5.041 m / regret NA m.

선정 규칙: `PRE_REFERENCE_MAX_ABSOLUTE_SOURCE_HEIGHT_GAP`. 공통 점수가 없어 영상 비교를 만들지 않았다.

## 6. 해석 범위와 다음 알고리즘

현재 결과는 조건부 소스 선택의 개발 검증이다. 현재 MVS를 만든 영상과 평가 RGB의 계보가 겹치고, 기존 카메라·정합은 고정했다. 각 소스의 자기 가림은 모델 가설이며 실제 현재 장면의 free-space나 전체 장면 가림을 증명하지 않는다. 따라서 PRIOR 선택은 관측과 양립하는 구조 후보라는 의미이며 과거 구조가 현재에도 존재한다는 확정은 아니다.

다음 구현의 우선순위는 (1) 혼합 셀을 여러 유한 표면 후보로 유지하고 같은 reference ray가 교차하는 인접 셀의 실제 표면까지 후보로 조회하는 방식, (2) 후보별 지지/반증/미관측 검사와 후보 간 공통 관측 비교의 분리다. 특히 고정 XY 셀의 두 표면이 영상에서 서로 다른 위치에 투영되면 현재 공통 support 조건은 비교 자체를 막을 수 있다. 원인별 기여율은 아직 분해되지 않았으므로 기하 교집합, 자체 가림, texture 탈락을 별도 계수해야 한다. 단순 임계값 완화보다 후보·관측 대응 단위의 개선을 먼저 검증해야 한다.

공통 영역이 없는 후보들의 서로 다른 patch NCC를 그대로 비교해 순위를 매겨서는 안 된다. 각 후보의 SUPPORT/REJECT/UNDETERMINED를 먼저 계산하고, 실제 공통 관측이 있을 때만 paired contrast를 추가하는 구성이 적절하다. 후보 불확실성과 미관측은 계속 ABSTAIN으로 남겨야 한다.

GS 입력 연결은 후보 원행 membership과 IMAGE/PRIOR/ABSTAIN 결과를 전달하는 방식으로 준비되어 있다. 이번 실행에서는 GS 학습, 외관 복원, LoD2 완성도 또는 최종 과학적 성능을 측정하지 않았다.

## 7. 재현·검증·산출물

- 소스: `src/phd/source_candidate_v1/`, driver: `scripts/phd/source_candidate_v1/`, 고정 설정: `configs/phd/source_candidate_v1/`.
- Docker에서 후보/관측/판단 테스트 27개, 참조 평가 테스트 9개 통과. 실자료 3영역 method seal 이후에만 UAS 접근.
- 평가 첫 시도는 UAS 배열 키 불일치로 중단했다. 정확한 `uas_xyz`/`uas_raw_rows` 스키마로 평가 로더만 수정했으며 실패 소스·로그를 보존했다. 재시도 보존 디렉터리 권한 문제도 해당 task 범위의 atomic rename으로 해소했다.

```bash
/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py method --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py evaluation --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py figures --run-id NEW_RUN_ID
/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py report --run-id NEW_RUN_ID
```

- [전체 셀 평가 CSV](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/run/evaluation/per_cell.csv)
- [27조합 민감도 CSV](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/run/evaluation/risk_coverage.csv)
- [파생 분석 JSON](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/report/analysis.json)
- [고정 method seal](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/run/method_seal.json)
- [그림 provenance](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/source_candidate_v1/PHD-SOURCE-CANDIDATE-P1P2P3-v1/figures/figure_manifest.json)

Method seal SHA256: `481f6f7fa22371607aa058706137e8ba90094049471f105a9bb6c1ea3378d978`

기존 실험·원자료는 변경하지 않았다. 수치와 그림은 기술적 산출물이며 최종 과학적 판단은 연구자에게 남긴다.
