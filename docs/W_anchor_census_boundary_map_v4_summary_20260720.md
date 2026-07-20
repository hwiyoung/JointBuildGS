# 앵커 census 및 boundary_map_v4 측정 요약

- 산출 상태: `complete_with_unmeasurable`
- 실행 범위: 정본 dense 실패 64동 중 기측정 6동을 제외한 58동 + 4907199 재현 확인 1행
- 학습 실행 수: `0`
- 신규 추론 allowlist: `census_FM_dense_dial_2px_only`
- 참조 LoD2/ALS 역할: 투영·분류 전용

## 1. 대상 및 완료 행

| 항목 | 수 |
|---|---:|
| 정본 raw_lidar 조립 성공 | 178 |
| 정본 raw_dense 조립 실패 | 64 |
| 기측정 실패 건물 | 6 |
| census 고정 명단 | 58 |
| 재현 확인 포함 측정 CSV 행 | 59 |

## 2. 중립 셀 인원

| 셀 | 전체 | 비소형 | 소형(<50㎡) |
|---|---:|---:|---:|
| `cell_1_assembled` | 114 | 95 | 19 |
| `cell_2_anchored` | 18 | 14 | 4 |
| `cell_3_outline_only` | 46 | 32 | 14 |
| `cell_4_beyond_image` | 0 | 0 | 0 |

## 3. census에서 기록된 cell_2 행

| building_id | inside 점수 | inside z MAD(m) | ref roof type | 수평/경사 | small |
|---|---|---|---|---|---|
| DEBY_LOD2_104586480 | 3364 | 0.071273 | horizontal | horizontal | true |
| DEBY_LOD2_107802038 | 4 | 0.127067 | slanted | sloped | false |
| DEBY_LOD2_107807336 | 22 | 0.740816 | slanted | sloped | false |
| DEBY_LOD2_42364659 | 5062 | 0.510582 | slanted | sloped | false |
| DEBY_LOD2_4907013 | 202 | 0.690746 | slanted | sloped | false |
| DEBY_LOD2_4907032 | 319 | 0.785923 | slanted | sloped | false |
| DEBY_LOD2_4907033 | 355 | 1.377241 | slanted | sloped | false |
| DEBY_LOD2_4907034 | 41 | 0.529169 | slanted | sloped | false |
| DEBY_LOD2_4907036 | 403 | 1.729978 | slanted | sloped | false |
| DEBY_LOD2_4907167 | 2688 | 1.270808 | slanted | sloped | false |
| DEBY_LOD2_4907169 | 156 | 1.954080 | slanted | sloped | false |
| DEBY_LOD2_4907508 | 156 | 1.228451 | multiple horizontal | horizontal | false |
| DEBY_LOD2_4908048 | 1379 | 0.039240 | multiple horizontal | horizontal | false |
| DEBY_LOD2_4908176 | 6012 | 0.149244 | slanted | sloped | true |

## 4. 애매 지대 A — 발자국 안 점수 1~99

| building_id | inside 점수 | inside z MAD(m) | ref roof type | small |
|---|---|---|---|---|
| DEBY_LOD2_107802038 | 4 | 0.127067 | slanted | false |
| DEBY_LOD2_107807336 | 22 | 0.740816 | slanted | false |
| DEBY_LOD2_4907034 | 41 | 0.529169 | slanted | false |
| DEBY_LOD2_8568392 | 6 | 0.069191 | slanted | true |

> 전례: 8568392의 6점은 2026-07-15 검수에서 n<20 재료 미달로 기록됐다.

## 5. 애매 지대 B — 점수 ≥100 및 inside z MAD >0.5 m

| building_id | inside 점수 | inside z MAD(m) | ref roof type | small |
|---|---|---|---|---|
| DEBY_LOD2_42364659 | 5062 | 0.510582 | slanted | false |
| DEBY_LOD2_4907013 | 202 | 0.690746 | slanted | false |
| DEBY_LOD2_4907032 | 319 | 0.785923 | slanted | false |
| DEBY_LOD2_4907033 | 355 | 1.377241 | slanted | false |
| DEBY_LOD2_4907036 | 403 | 1.729978 | slanted | false |
| DEBY_LOD2_4907167 | 2688 | 1.270808 | slanted | false |
| DEBY_LOD2_4907169 | 156 | 1.954080 | slanted | false |
| DEBY_LOD2_4907508 | 156 | 1.228451 | multiple horizontal | false |

## 6. 4907199 재현 확인

| selected DLT | footprint inside | inside z median(m) | cache/new |
|---:|---:|---:|---|
| 538 | 373 | -34.347425 | cache_reuse |

## 7. 측정불능 및 미완 목록

### 측정불능

| building_id | anchor status | cell | 딱지 |
|---|---|---|---|
| DEBY_LOD2_42364609 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4907031 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4907510 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908051 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908052 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908054 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908166 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908167 | unmeasurable | cell_3_outline_only | 앵커 미판정 |
| DEBY_LOD2_4908169 | unmeasurable | cell_3_outline_only | 앵커 미판정 |

### 예산·진행 미완

| building_id | anchor status | cell | 딱지 |
|---|---|---|---|
| 없음 |  |  |  |

## 8. 점수 분포 기록

- 측정 완료 실패동: 0점 37동 · 1~99점 4동 · 100점 이상 14동
- 측정불능 9동 · 미완 0동
- 위 구간은 고정 문턱(inside 점수 1) 민감 구간과 고점수·고MAD 조건을 그대로 집계한 값이다.
