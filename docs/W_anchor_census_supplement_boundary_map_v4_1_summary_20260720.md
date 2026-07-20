# 앵커 census 보강 측정 및 boundary_map_v4.1 요약

- 범위: 고정 9동 동일 취득 분-블록 쌍 재풀링·기계 셀 재배정
- 신규 MASt3R 추론: `0` · GPU 사용: `false` · 학습 실행: `0`
- 쌍 표기: `low_same_block` · 건물 표기: `same_block_only=true`
- 지도 그림: 재생성하지 않음

## 1. 셀 인원 전후

| 셀 | v4 전체 | v4.1 전체 | v4 소형 | v4.1 소형 |
|---|---|---|---|---|
| cell_1_assembled | 114 | 114 | 19 | 19 |
| cell_2_anchored | 18 | 23 | 4 | 8 |
| cell_3_outline_only | 46 | 41 | 14 | 10 |
| cell_4_beyond_image | 0 | 0 | 0 | 0 |

## 2. 고정 9동 재풀링 측정값

| building_id | 인정 쌍 | 2px 점 | inside 점 | inside z 중앙(m) | inside z MAD(m) | 이전 셀 | 재배정 셀 |
|---|---|---|---|---|---|---|---|
| DEBY_LOD2_42364609 | 10 | 22736 | 10811 | -40.838065 | 0.110847 | cell_3_outline_only | cell_2_anchored |
| DEBY_LOD2_4907031 | 10 | 15908 | 0 |  |  | cell_3_outline_only | cell_3_outline_only |
| DEBY_LOD2_4907510 | 10 | 25062 | 12312 | -43.424649 | 0.329260 | cell_3_outline_only | cell_2_anchored |
| DEBY_LOD2_4908051 | 10 | 6153 | 0 |  |  | cell_3_outline_only | cell_3_outline_only |
| DEBY_LOD2_4908052 | 10 | 9978 | 0 |  |  | cell_3_outline_only | cell_3_outline_only |
| DEBY_LOD2_4908054 | 10 | 3744 | 0 |  |  | cell_3_outline_only | cell_3_outline_only |
| DEBY_LOD2_4908166 | 10 | 19240 | 7273 | -41.224573 | 0.074135 | cell_3_outline_only | cell_2_anchored |
| DEBY_LOD2_4908167 | 10 | 12815 | 19 | -35.981647 | 1.820859 | cell_3_outline_only | cell_2_anchored |
| DEBY_LOD2_4908169 | 10 | 11098 | 1145 | -36.730146 | 0.229714 | cell_3_outline_only | cell_2_anchored |

> 위 9행은 모두 `same_block_only=true`, `pair_independence=low_same_block`이며 사전등록 §2 주 명단 산입 불가 표기를 포함한다.

## 3. 104586480 원 규칙 재현

| inside 점 | inside z 중앙(m) | inside z MAD(m) | 재현 일치 |
|---|---|---|---|
| 3364 | -43.161802 | 0.071273 | true |

## 4. 동일 블록 쌍 |Δz| 대조

- 대상: 24쌍 / 11동
- 중앙: 0.271461 m
- p90: 5.092229 m (`numpy.quantile(method=lower)`)
- 최대: 7.275130 m
- |Δz|≤0.5 m: 13/24 (54.17%)

## 5. 범위·상태 기록

- 9동 외 169행의 기존 열 값 동일: `169`행
- dense 실패 비대상 55동 원 값 재풀링 없음
- 보강 후 `unmeasurable` 유지: `0`동
- 참조 LoD2: 투영·분류 전용
