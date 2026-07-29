---
doc_id: boundary-map-family-index
family_id: boundary_map
document_type: guide
status: canonical
canonical_for: boundary_map_family_index
run_ids:
  - 20260716_boundary_map
  - 20260718_boundary_map_v2
  - 20260719_boundary_map_v3
  - 20260720_anchor_census
  - 20260720_anchor_census_supplement
---

# Boundary map

이 디렉터리는 `boundary_map` 실험군의 현재 보고서, compact evidence table, provenance manifest를 한곳에서 찾는 진입점이다. 원본 측정값과 역사 manifest 내용은 이동 전후 byte-identical로 유지한다.

## 현재 읽는 순서

1. [`W_anchor_census_boundary_map_v4_summary_20260720.md`](./reports/W_anchor_census_boundary_map_v4_summary_20260720.md) — v4 전체 census
2. [`W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md`](./reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md) — 고정 9동 보강
3. [`boundary_map_v4_1_ladder.csv`](tables/boundary_map_v4_1_ladder.csv) — 현재 178동 셀 배정

## 정본

| 목적 | 경로 |
|---|---|
| v4 base census summary | [`reports/W_anchor_census_boundary_map_v4_summary_20260720.md`](./reports/W_anchor_census_boundary_map_v4_summary_20260720.md) |
| v4.1 supplement summary | [`reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md`](./reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md) |
| current 178-row assignment ladder | [`tables/boundary_map_v4_1_ladder.csv`](tables/boundary_map_v4_1_ladder.csv) |
| v4 base provenance | [`manifests/boundary_map_v4_manifest.json`](manifests/boundary_map_v4_manifest.json) |
| v4.1 supplement provenance | [`manifests/anchor_census_supplement_manifest.json`](manifests/anchor_census_supplement_manifest.json) |

이 README가 실험군 탐색의 정본 진입점이다. 개별 과학적 목적의 정본은 위 다섯 파일로 분리한다.

## 보조자료

- `tables/`: v2 boundary cases, v3 검증표, v4 census, v4.1 supplement 측정표
- `manifests/`: v1-v3의 재현 provenance와 v4/v4.1 정본 provenance
- [`../../figs/boundary_map/boundary_map_v4_map.png`](../../figs/boundary_map/boundary_map_v4_map.png): 최신 존재 그림이지만 v4.1에서 변경된 5동은 반영하지 않은 보조 그림

대체된 v1-v4 자료는 [`../../archive/boundary_map/`](../../archive/boundary_map/)에 버전별로 보존한다. Archive 파일은 현재 입력으로 사용하지 않는다.

## 실행 이력

| 버전 | run receipt |
|---|---|
| v1 | `phases/p2-gsjso/runs/20260716_boundary_map/` |
| v2 | `phases/p2-gsjso/runs/20260718_boundary_map_v2/` |
| v3 | `phases/p2-gsjso/runs/20260719_boundary_map_v3/` |
| v4 | `phases/p2-gsjso/runs/20260720_anchor_census/` |
| v4.1 | `phases/p2-gsjso/runs/20260720_anchor_census_supplement/` |

Run 디렉터리는 이동하지 않는다. 실행 당시 코드·config·입출력 경로와 hash를 보존하는 provenance ledger다.

## 경로 이동과 과거 참조

정확한 이전 경로와 현재 경로, lifecycle 상태, 원본 SHA-256은 [`../../catalog/migrations/BOUNDARY_MAP_PATHS.csv`](../../catalog/migrations/BOUNDARY_MAP_PATHS.csv)에 있다. 과거 manifest와 run receipt 안의 이전 경로 문자열은 당시 사실이므로 rewrite하지 않는다. 인벤토리는 migration manifest를 통해 그 문자열을 현재 경로로 해석한다.

활성 staged workflow가 아직 고정한 v2·v4.1 ladder의 두 이전 경로는 동일 SHA의 compatibility mirror로 잠정 유지한다. 두 mirror는 정본이 아니며 새 코드와 문서는 이 디렉터리의 경로를 사용한다.
