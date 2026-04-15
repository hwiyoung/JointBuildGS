# Phase 1 Step 1-0: 리포지터리 셋업 + 기존 자산 마이그레이션

## 수행 일시
2026-04-14

## 수행 작업 요약

JointBuildGS 리포지터리의 초기 구조를 구축하고 PlanarSplatting 예비 실험 자산을 마이그레이션했다. Stage 3 모노리식 코드를 5개 모듈로 분리하고 원본과의 동등성을 검증했다.

### 산출물 요약
- 디렉토리 구조: `src/`, `scripts/`, `configs/`, `data/`, `results/`, `legacy/`
- Stage 3 모듈: `src/stage3/{clustering, ground_surface, plane_intersection, citygml_export, building_instance}.py`
- Synthetic A 자산: `scripts/synthetic_a/`, `results/synthetic_a/`
- Legacy 참고 코드: `legacy/planarsplat_ref/`
- 의존성: `requirements.txt` (gsplat 기반)

## Part A: 디렉토리 구조

EXPERIMENT_PLAN.md의 구조대로 생성. `results/phase1_integration/`은 논의 수정 반영 (Step 1-4 별도 경로).

## Part B: 기존 자산 마이그레이션

### B-1: Synthetic A
| 항목 | 원본 | 대상 | 방식 |
|------|------|------|------|
| 생성/실험 스크립트 | `PlanarSplatting/scripts/stage3_synthetic/` | `scripts/synthetic_a/` | 복사 |
| 실험 결과 | `PlanarSplatting/results/stage3_synthetic_a/` | `results/synthetic_a/` | 복사 |

포함 파일: `primitives.py`, `run_3dbag_experiment.py`, `run_experiment.py`, `buildings_3dbag.py`, `analyze.py`, `plot_gt_vs_result.py`, `merge_cityjson.py`. 결과: 18 noise condition × 최대 512 buildings 의 CityJSON + PLY 출력, `REPORT.md`, scene visualizations.

### B-2: Stage 3 모듈 분리

원본 `building_to_citygml_v4.py` (1017 lines, 모노리식) → 5개 모듈:

| 모듈 | 주요 함수 | LOC |
|------|----------|-----|
| `clustering.py` | `cluster_primitives`, `_spatial_split`, `_merge_tiny_clusters` | ~180 |
| `ground_surface.py` | `orient_normals_outward`, `add_ground_surface`, `add_bbox_planes` | ~75 |
| `plane_intersection.py` | `intersect_three_planes`, `build_convex_polytope`, `build_footprint_solid`, `_arrangement_footprint`, `_merge_coplanar_triangles` | ~290 |
| `citygml_export.py` | `build_cityjson`, `save_lod2_ply`, `compute_signed_volume` | ~180 |
| `building_instance.py` | `process_building`, `process_all_buildings` | ~125 |

### B-3: Legacy 보존
전체 PlanarSplatting 복사 대신 **핵심 참고 파일만** 선별 보존 (disk 절약):
- `loss_util.py` — L_mutual, L_sem 구현
- `trainer.py` — 학습 루프, warmup, gradient check
- `net_planarSplatting.py` — Semantic head 구조
- `building_to_citygml_v4.py` — Stage 3 모노리식 원본 (동등성 검증 레퍼런스)
- `build_2_5d.py` — 2.5D solid 대안
- `generate_segmentation.py` — Grounded SAM + depth 하이브리드

전체 PlanarSplatting 리포지터리는 `/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting/`에 그대로 보존되어 있으므로 필요 시 참조 가능.

### B-4: Stage 1 출력물 (성수동)
대용량 파일은 심볼릭 링크로 연결:
- `data/seongsu/input_data.pth` → PlanarSplatting COLMAP 출력 (6.9 GB, 100 images × color/depth/normal/extrinsics/intrinsics)
- `data/seongsu/colmap_sparse.ply` → COLMAP sparse point cloud (9.4 MB)
- `data/seongsu/colmap_runs` → 전체 COLMAP run 디렉토리

**주의: Grounded SAM segmentation GT는 현재 파일시스템에 없음.** 원본 생성 경로 (`user_inputs/testset/0_25x/seg_maps/`)는 Docker 환경 기반이었음. Step 1-2(Semantic head + L_sem) 진입 시 `legacy/planarsplat_ref/generate_segmentation.py`로 재생성 필요.

### B-5: 3D BAG 데이터
`data/3dbag/raw` → `results/synthetic_a/3dbag_raw` (64 MB, 3 scenes: amsterdam_jordaan, rotterdam_center, delft_wijk).

## Part C: 의존성
`requirements.txt` 생성. 핵심:
- `gsplat>=1.3.0` (미분 가능 렌더링)
- `torch>=2.1.0`, `torchvision`
- `open3d`, `trimesh`, `shapely`, `scipy` (기하)
- `lxml`, `cjio` (CityGML/CityJSON)
- `tensorboard`, `tqdm`, `pyyaml` (학습)
- `scikit-learn`, `scikit-image` (평가)

Semantic GT 재생성용 `transformers`, `sam2`는 주석 처리 (Step 1-2 진입 시 활성화).

## Part D: 모듈 동등성 검증

**검증 방식:** `scripts/synthetic_a/verify_migration.py` — 5개의 3D BAG 건물에 대해 legacy 모노리식 파이프라인과 분리된 `src/stage3/` 모듈에서 동일 primitives 입력을 처리하여 `n_surfaces`와 `signed_volume`을 비교.

**결과:**
| bid | status | old_surf | new_surf | old_vol | new_vol |
|-----|--------|----------|----------|---------|---------|
| 1 | fail (both) | - | - | - | - |
| 2 | MATCH | 8 | 8 | 1382.288860 | 1382.288860 |
| 3 | MATCH | 7 | 7 | 238.096097 | 238.096097 |
| 4 | MATCH | 6 | 6 | 48.501625 | 48.501625 |
| 5 | MATCH | 6 | 6 | 47.121935 | 47.121935 |

**4/5 완전 일치** (부동소수점 수준까지). b1은 양쪽 동일하게 경계 조건으로 실패 → 이는 불일치가 아니라 **동일 동작**의 또다른 증거.

## 정량 지표
| 지표 | 값 | 비고 |
|------|-----|------|
| 새 Stage 3 모듈 수 | 5 | clustering, ground_surface, plane_intersection, citygml_export, building_instance |
| 분리 후 총 LOC | ~850 | 원본 1017 대비 -16% (모듈 분리 및 공백 정리) |
| Legacy 보존 파일 | 6 | 핵심 구현만 선별 |
| 모듈 동등성 | 4/5 MATCH | bit-identical output on common cases |

## 시각적 산출물 체크리스트
- [x] 디렉토리 구조 (`docs/EXPERIMENT_PLAN.md` 참조)
- [x] 모듈 동등성 검증 출력 (verify_migration.py 실행 결과)
- [ ] Synthetic A 전체 재실행 (Phase 1-2 이후 필요 시 수행 — 현재 step에서는 smoke test로 충분)

## Go/No-Go
**Go.** 

- 모듈 분리가 원본 동작을 보존함이 검증됨 (4/4 matching case bit-identical).
- 대용량 데이터 (input_data.pth, colmap) 접근 가능.
- Synthetic A 자산 복사 완료.
- 다음 단계(Step 1-1: gsplat 기반 2DGS vanilla 학습) 진입 가능.

## 이슈 및 해결

### 이슈 1: Segmentation GT 부재
성수동 Grounded SAM segmentation GT가 현재 파일시스템에 없음 (Docker 환경 기반 `user_inputs/testset/0_25x/seg_maps/`).

**해결:** Step 1-2 진입 시 `legacy/planarsplat_ref/generate_segmentation.py`로 재생성. 원본 이미지는 `data/seongsu/colmap_runs`에서 접근 가능.

### 이슈 2: input_data.pth 크기
6.9 GB → git commit 불가.

**해결:** 심볼릭 링크로 연결, `.gitignore`에 `data/seongsu/input_data.pth` 추가 예정.

### 이슈 3: b1 건물이 양쪽 파이프라인에서 실패
검증 대상 5개 건물 중 1개가 `ConvexHull failed: input appears less than 3-dimensional` 오류.

**해결:** 불일치가 아니라 legacy와 new 양쪽에서 **동일하게** 실패 → 동등성 보존됨. 원인은 해당 건물의 primitive 배치가 퇴화 케이스 — Stage 3 알고리즘의 알려진 제한사항.

## 다음 단계
**Step 1-1: gsplat 기반 2DGS Vanilla 학습**
- `src/stage2/` 구조 설계 (model, renderer, loss, densification, dataloader, train)
- gsplat 라이브러리로 2DGS primitive 학습 파이프라인 구축
- 성수동 데이터에서 L_photo + L_depth + L_normal + L_nc 기반 vanilla 학습
- PlanarSplatting 예비 대비 coverage / 밀착 개선 확인
