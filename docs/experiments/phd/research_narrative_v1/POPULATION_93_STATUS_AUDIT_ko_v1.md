# Journal1 93동 지위 감사 (v1) — 정본·선정·노출·독립성

> **지위: READ-ONLY DATA/LINEAGE AUDIT.** 실행·재학습·재평가 없음.
> `scientific_verdict: null`. 작성 2026-08-28. 리뷰어: 김휘영.
>
> 목적: 새 박사 서사에서 사용하는 “93동”의 정확한 정체와 허용 용도를 확정하고,
> 같은 숫자의 P0 `coverage-control 93`과 혼용되는 것을 막는다.

## 0. 최종 판정

`selection_confirm_v1.json`의 Journal1 93동은 다음 지위다.

> **한 장면의 199동에서 E1 조사범위 평가가능성 규칙과 사람 오버라이드로 동결한,
> exact stable-ID 개발 부분집합. 후속 실험의 공통 마스크로는 유효하지만,
> 미접촉 독립 시험집합 또는 확증 모집단은 아니다.**

- 정본성: **PASS** — 93개 ID, 93개 unique, 전부 199동의 부분집합, SHA-256/receipt
  존재
- 조건 간 공정성: **PASS** — 같은 마스크를 모든 조건에 적용
- 결과 독립 선정: **PARTIAL / 미입증** — 자동 규칙은 outcome-free지만 5건의 사람
  오버라이드는 조건별 지표를 볼 수 있는 뷰어에서 수행됐고 사유·블라인드 절차가
  정본에 없음
- 미접촉 독립 시험성: **FAIL** — 199동 전수 기술 결과와 Journal1 199동 지표가
  이미 열린 뒤 선정됐고, 이후 반복 개발·판독에 사용됨
- 장면 일반화: **FAIL** — 단일 AOI/취득 장면의 공간 상관된 건물들임

## 1. 감사 단위와 정본

### 1.1 의도한 grain

감사 단위는 `stable_id`로 식별되는 **건물 1동당 1행**이다. 동일 건물 안의
held-out camera view는 별도 grain이며, 그 존재가 건물 집합을 held-out test로
만들지 않는다.

### 1.2 정본 소스

| 소스 | 역할 | 무결성 |
|---|---|---|
| `phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/labels/selection_confirm_v1.json` | Journal1 93 exact ID | `f7124b727aee2415945292c6c92c47db31c50b4a37e1ef3691a231d93236cb41` |
| 같은 경로 `selection_confirm_v1.receipt.json` | freeze 출처·역할 | `412db9566ceeaa84ba74c6252db0cbba60f4bc44271befb814f51bea4c6b4c1d` |
| `.../c1_c2_shared_footprint_199_v3/.../shared_footprints_199.geojson` | 199동 stable-ID universe | `5f9b703b06676db4400f6568fc3db315e319913f98ba491e98922eb747e4488a` |
| `docs/evidence/p0_g1_20260613/w4b_population_profile_building_metrics.csv` | P0 control 93 비교 | `3c5d07e4c5f722203812710a58abae5d258270632b16901eb0a429433c4da32f` |

외부 artifact 경로는 Git 정본이 아니라 현재 로컬 artifact resolver의 payload다.
위 해시는 이번 감사에서 읽은 바이트를 고정한다.

### 1.3 기본 품질 프로파일

| 검사 | 결과 |
|---|---:|
| effective ID 원소 수 | 93 |
| unique stable-ID 수 | 93 |
| 중복 | 0 |
| 199동 universe 밖 ID | 0 |
| 199동 대비 비율 | 93/199 |

## 2. 선정 과정

### 2.1 자동 규칙: 199 → 94

E1 full-scene any-return 점유를 1 m cell로 만들고, 가장 큰 연결 성분의 내부 구멍을
채워 조사영역을 정의했다. 표준 footprint가 다음을 만족하면 선정했다.

- 조사영역을 5 m 침식한 내부에 완전히 포함: 전부 포함
- 경계와 교차: footprint의 0.5 m cell 중 E1 any-return coverage가 0.80 이상이면 포함
- 조사영역 밖: 제외

| zone | 전체 | 규칙 선정 |
|---|---:|---:|
| interior | 68 | 68 |
| boundary | 56 | 26 |
| outside | 75 | 0 |
| 합 | 199 | 94 |

이 규칙 자체는 방법 성과가 아니라 E1 조사범위만 사용하므로 outcome-free
evaluability rule로 해석할 수 있다. 다만 E1 coverage가 있는 공간으로 평가 범위를
조건화하므로, “일반 영상 기반 점군의 전체 배포 모집단”이 아니라 **현재 E1로
평가 가능한 단일 장면 영역**을 정의한다.

### 2.2 사람 오버라이드: 94 → 93

| stable-ID | 규칙 | 최종 | E1 any coverage | zone |
|---|---:|---:|---:|---|
| `DEBY_LOD2_4907180` | 제외 | 포함 | 0.765 | boundary |
| `DEBY_LOD2_4907196` | 제외 | 포함 | 0.796 | boundary |
| `DEBY_LOD2_4908166` | 포함 | 제외 | 1.000 | boundary |
| `DEBY_LOD2_42364609` | 포함 | 제외 | 1.000 | boundary |
| `DEBY_LOD2_42364657` | 포함 | 제외 | 0.838 | boundary |

receipt에는 “user-confirmed export from the 8882 conditions viewer”라고만 있고,
각 변경의 사유·판정자·블라인드 여부는 없다. 선정 시점 전에 적어도 E1–E5의
199동 dual-GT 지표가 이미 존재했고, 선택 UI 자체가 arm별 지표·tier·점군과 같은
화면에 있다. 현재 보존된 뷰어 코드는 E1/E2/E3/E4/E5/E7/E8별 `f1_lod2`,
`f1_e1`, `O50`을 표시한다.

따라서 다음 두 문장은 구분해야 한다.

- **확인됨:** 최종 93은 이후 조건에 동일 적용됐고, 선택 마스크 자체가 방법의
  파라미터 입력이나 outcome classifier로 쓰이지 않았다.
- **확인되지 않음:** 다섯 오버라이드가 결과를 보지 않은 상태에서 오직 E1
  경계 품질만으로 결정됐다.

“성능과 무관하게 사전 동결”은 후속 D1/X4 등에 대해 사용할 수 있는 운영상
표현이지만, 결과 블라인드 독립 시험집합이라는 의미로 확장하면 안 된다.

## 3. 199동 및 다른 93과의 관계

### 3.1 199동과의 관계

Journal1 93은 199동의 정확한 부분집합이다. 199동 밖 ID는 없다. 그러나 199동은
`DEC-P1-015`에 의해 2026-08-03 C1/C2/C3 전수 기술 census에 사용됐고, 이 결정은
기존 validation/held-out membership을 열어 더 이상 untouched confirmatory set으로
주장하지 않도록 명시한다.

### 3.2 P0 `coverage-control 93`과는 다른 집합

P0 93은 `coverage_control_population=yes`인 ALS/DIM 통제 비교 부분집합이고,
Journal1 93은 E1 조사범위 evaluability mask다.

| 집합 비교 | 동 수 |
|---|---:|
| Journal1 93 | 93 |
| P0 control 93 | 93 |
| 교집합 | 84 |
| Journal1에만 | 9 |
| P0에만 | 9 |
| 대칭차 | 18 |

Journal1에만 있는 9동:

`104583447`, `104586480`, `108250120`, `42364661`, `4907508`, `4908351`,
`4959465`, `8568403`, `8573848`.

P0에만 있는 9동:

`42364609`, `42364657`, `4907182`, `4907205`, `4907207`, `4907506`,
`4908050`, `4908166`, `4908176`.

위 축약 ID는 모두 `DEBY_LOD2_` 접두사를 가진다. 새 서사의 45/93, 86/93,
X4 80/93은 `selection_confirm_v1.json`의 Journal1 93에 묶여 있다. P0의
87/93, 75/93, 88/93, 83/93 등과 모수를 섞으면 안 된다.

## 4. 결과 노출 이력과 독립성

| 시점 | 사건 | 독립성에 대한 의미 |
|---|---|---|
| 2026-08-03 | `DEC-P1-015`: 199동 C1/C2/C3 전수 기술 실행 | 기존 validation/held-out 건물의 미열람성 종료 |
| 2026-08-12 20:42 KST 이전 | Journal1 A3가 E1–E5 199동 dual-GT 지표 생성·등재 | 93 확정 전 동일 199동의 조건 성과가 이미 존재 |
| 2026-08-12 22:52 KST | `selection_confirm_v1.json` export, 5건 override, 93동 freeze | 후속 공통 mask 고정. 오버라이드 outcome blindness는 미입증 |
| 2026-08-13 이후 | E7/E8, D1 δ, E9, AX10, ARRGS/X4 등 반복 판독 | 명백한 방법 개발·가설 형성 집합으로 사용 |

따라서 93동의 결과는 완전히 버려야 할 누출 데이터가 아니다. 올바른 지위로
낮추면 유용하다. 하지만 건물 내부의 일부 view를 held-out으로 떼거나, 지금 새
split을 만들어도 과거 건물 수준 결과 노출을 되돌릴 수는 없다.

## 5. 발견사항 — 심각도와 신뢰도

| ID | 발견 | 심각도 | 신뢰도 | 조치 |
|---|---|---|---|---|
| F1 | exact ID·count·subset·hash는 일관됨 | 정보/PASS | 높음 | 현 JSON과 해시 유지 |
| F2 | 숫자가 같은 서로 다른 93 두 개가 존재, 18개 ID가 다름 | 높음 | 높음 | 모든 표에 `journal1_e1_coverage_93` 또는 `p0_coverage_control_93` 명시 |
| F3 | 자동 규칙은 outcome-free지만 5 override의 블라인드 사유가 없음 | 높음 | 높음 | 최종 시험에서는 수동 변경 금지 또는 사유·판정자·블라인드 receipt 고정 |
| F4 | 93은 199 census와 Journal1 성과 노출 뒤 선정·반복 사용 | 치명적(확증 용도) | 높음 | 개발용으로만 사용, 독립 시험장면 신설 |
| F5 | E1 coverage 조건화로 평가범위가 현재 참조 가용 영역에 한정 | 중간 | 높음 | target population을 명시하고 E1 미가용 영역 주장을 분리 |
| F6 | 한 AOI의 공간 상관 건물이라 93 independent repetition이 아님 | 높음(일반화) | 높음 | scene/spatial-group 단위 추론·독립 장면 시험 |

## 6. 허용 용도와 금지 용도

### 허용

- K1의 문제 실재성·실패 유형·하류 오류 전파 진단
- K2의 구현 개발, 하이퍼파라미터 선택, ablation, 실패 사례 분석
- 동일 93 안의 paired 기술 비교와 통제 `δ`/변화 주입
- 추가 취득/view-count 기준선 설계와 내부 교차검증
- 독립 시험 전에 동결할 지표·성공 계약·시각화 형식 개발

이때 결과 표기는 `DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`을
유지하고, 건물을 93개의 완전 독립 반복으로 간주하지 않는다.

### 금지

- “독립 시험 93동”, “held-out 93동”, “미접촉 test set” 표기
- 93동 수치만으로 새 장면·도시·센서·시점에 대한 일반화 주장
- P0 93과 Journal1 93의 수치 또는 ID 무표기 혼합
- 건물 내부 held-out view 성능을 건물/장면 독립성의 증거로 사용
- 93 결과를 본 뒤 정한 하류 작업·임계값을 confirmatory라고 재명명

## 7. 독립 시험설계에 필요한 조치

1. **새 장면을 unit으로 확보한다.** 기존 199동 밖의 공간이며, 가능하면 다른
   촬영기하·건물형태·prior 품질을 포함한다.
2. **장면을 열기 전에** target population, 포함/제외 규칙, stable-ID, primary
   metric, 하류 작업, missing 처리, 비용 비교를 동결한다.
3. 평가가능성 규칙은 outcome-free 코드로만 실행한다. 수동 예외가 필요하면 방법
   결과를 가린 별도 화면에서 사유·판정자·시간을 receipt로 남긴다.
4. 방법 개발은 현 93/199에서 끝내고, 독립 장면에서는 재학습·임계 조정 없이 한 번
   실행한다.
5. 건물 수뿐 아니라 scene/spatial group 수를 보고한다. 다장면이면 scene-level
   불확실성과 leave-one-scene-out 결과를 함께 둔다.
6. 추가 취득 비교도 같은 장면에서 사전 동결된 view-count/geometry ladder로
   수행한다.

새 독립 장면이 없다면 현 93을 재분할해 확증성을 복구할 수 없다. 그 경우 가능한
정직한 결론은 “단일 장면 개발 증거 + 통제 기제 검증”까지이며, 외부 일반화는
보류한다.

## 8. 새 서사에서 사용할 권장 명칭

- 첫 등장: **“Journal1 E1-coverage evaluability subset 93동(개발·비확증)”**
- 짧은 표기: `journal1_e1_coverage_93`
- P0 집합: `p0_coverage_control_93`
- 금지할 축약: 출처 없는 `93동`, `control 93`, `test 93`
