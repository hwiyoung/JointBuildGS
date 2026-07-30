# Boundary map 정본 지도

검토일: 2026-07-29  
범위: `boundary_map` v1-v4.1 문서, 표, manifest, 그림, 실행 코드, 실행 영수증
성격: 문서 관리 결정이며 측정값·실험 결과·과학적 판정을 변경하지 않는다.

사람이 탐색할 때는 [`docs/experiments/input-and-alignment/boundary_map/README.md`](../../experiments/boundary_map/README.md)를 진입점으로 사용한다.

## 지금 무엇을 봐야 하는가

| 질문 | 정본 |
|---|---|
| 현재 178동의 셀 배정과 행별 근거 | `docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv` |
| v4 전체 census의 범위와 결과 설명 | `docs/experiments/input-and-alignment/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md` |
| v4.1에서 바뀐 9동과 보강 한계 설명 | `docs/experiments/input-and-alignment/boundary_map/reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md` |
| v4 본 측정의 재현·hash 계보 | `docs/experiments/input-and-alignment/boundary_map/manifests/boundary_map_v4_manifest.json` |
| v4.1 보강의 재현·불변성·low-independence 계보 | `docs/experiments/input-and-alignment/boundary_map/manifests/anchor_census_supplement_manifest.json` |

읽는 순서는 **v4 본 요약 → v4.1 보강 요약 → v4.1 ladder**다. Manifest는 수치와 출처를 검증할 때 함께 본다. v4.1은 v4 설명 전체를 다시 쓴 문서가 아니라, v4에서 측정불능이던 고정 9동을 보강한 후속이다.

## 핵심 결정

- 현재 배정표는 `docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv` 하나다. 새 consumer는 이 경로를 사용한다.
- `docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv`는 v4.1의 직접 입력이자 이전 스냅샷이다. 현재 배정에는 사용하지 않는다.
- `docs/archive/boundary_map/v4/tables/boundary_map_v4_targets.csv`는 v4 당시 64동 스냅샷이다. v4.1이 9행을 보강했으므로 현재 target/셀 값은 v4.1 ladder를 필터링해 읽는다.
- `docs/figs/boundary_map/boundary_map_v4_map.png`는 최신 존재 그림이지만 현재 그림은 아니다. v4.1 manifest가 그림을 재생성하지 않았다고 명시하며, 이 그림에는 5동의 셀 변경이 반영되지 않는다.
- v1-v3 파일은 삭제 대상이 아니다. 이전 규칙·측정·검증을 재현하는 역사 자료로 보존하되 현재 배정 근거로 사용하지 않는다.

## 버전 계보

```text
v1 (20260716_boundary_map)
  -> v2 (20260718_boundary_map_v2: canonical 178 재구성)
    -> v3 (20260719_boundary_map_v3: 재측정·provenance QA)
      -> v4 (20260720_anchor_census: neutral cell census)
        -> v4.1 (20260720_anchor_census_supplement: 고정 9동 cache-only 보강)
```

Git에서도 각 공개 bundle은 순서대로 `52c84f7`, `5c1331b`, `17ab65d`/`1995494`, `2cd9e9d`, `e351c68`에 기록되어 있다. 파일 내용의 manifest 계보도 v3가 v2를, v4가 v3를, v4.1이 v4 ladder와 manifest를 입력으로 기록한다.

## 역할별 상태

| 역할 | canonical | supporting | superseded |
|---|---|---|---|
| 현재 배정 | v4.1 ladder | v4/v4.1 measurement tables | v1-v4 ladders, v4 targets |
| 설명 | v4 본 요약 + v4.1 보강 요약 | - | v2-v3 요약 |
| provenance | v4 manifest + v4.1 supplement manifest | v1-v3 manifests | - |
| 검증표 | - | v2 boundary cases, v3 metrics/confusion/conditional targets, census·supplement tables | 직접 후속이 있는 v1-v2 표 |
| 그림 | 현재 정본 없음 | v4 그림(보강 전임을 명시) | v1-v3 그림 |

개별 파일의 기계 판독 상태와 `supersedes`/`derived_from` edge는 `configs/repo_inventory.json`의 `reviewed_family_maps`에 있으며, 생성된 `docs/catalog/DOCUMENT_CATALOG.csv`와 `docs/catalog/DOCUMENT_LINEAGE.csv`에 반영된다.

## 실행 영수증

| 버전 | 공개 결과 | 주요 실행 영수증 |
|---|---|---|
| v1 | `docs/archive/boundary_map/v1/` + v1 manifest | `phases/p2-gsjso/runs/20260716_boundary_map/` |
| v2 | `docs/archive/boundary_map/v2/` + supporting v2 files | `phases/p2-gsjso/runs/20260718_boundary_map_v2/` |
| v3 | `docs/archive/boundary_map/v3/` + supporting v3 files | `phases/p2-gsjso/runs/20260719_boundary_map_v3/` |
| v4 | current report/manifest/tables + `docs/archive/boundary_map/v4/` | `phases/p2-gsjso/runs/20260720_anchor_census/` |
| v4.1 | current ladder + supplement bundle | `phases/p2-gsjso/runs/20260720_anchor_census_supplement/` |

실행 디렉터리는 provenance 영수증과 세부 측정의 소유자다. 연구 문서의 정본 여부는 실행 디렉터리의 위치가 아니라 위 역할 지도와 manifest 연결로 판단한다.

## 실행 코드 소유권

- Boundary-map 전용 driver 12개는 `scripts/experiments/boundary_map/`이 소유한다.
- `population_aux_v3.py`, `projection_datum.py`, E5 retriangulation/rescore 계열처럼 다른 P2 실험도 쓰는 helper는 `phases/p2-gsjso/scripts/`에 남긴다.
- 외부 multi-wave driver는 원래 phase 위치를 유지하고 새 family script 경로를 호출한다.
- 정확한 old/new 경로와 이동 전후 SHA-256은 [`BOUNDARY_MAP_SCRIPT_PATHS.csv`](../migrations/BOUNDARY_MAP_SCRIPT_PATHS.csv)에 기록한다.

## 경로 이동 상태

`DOC-IA-03`에서 35개 원본의 목표 경로와 SHA-256을 [`BOUNDARY_MAP_PATHS.csv`](../migrations/BOUNDARY_MAP_PATHS.csv)에 고정했다. 원본 CSV·JSON·Markdown·PNG 내용과 run receipt는 수정하지 않는다.

- 33개 이전 경로는 새 owner 디렉터리로 이동한다.
- `docs/boundary_map_v2_ladder.csv`는 현재 staged workflow 보호를 위해 임시 direct input으로 남긴다.
- v4.1 이전 root copy는 byte-identical 상태로 `docs/archive/compatibility/root-mirrors/tables/`에 보존했다. 새 문서·코드·config는 새 owner 경로를 사용해야 한다.
- 과거 manifest와 run receipt의 old path 문자열은 당시 provenance이므로 rewrite하지 않고 migration manifest로 해석한다.
- phase run 디렉터리와 원본 실험 결과는 이동하지 않는다.
- `DOC-IA-04`에서 boundary 전용 실행 코드만 family owner로 이동하고 공용 helper는 이동하지 않는다.
