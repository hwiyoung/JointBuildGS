# Phase 1 Step 1-0: 리포지터리 셋업 + 마이그레이션 + MatrixCity 준비

## 수행 일시
2026-04-14 (초기), 2026-04-16 (v7 업데이트)

## 수행 작업 요약

JointBuildGS 리포지터리의 구조 구축, PlanarSplatting 자산 마이그레이션, MatrixCity 벤치마크 데이터 준비, Docker 환경 구축을 수행했다.

## Part A: 리포지터리 구조

EXPERIMENT_PLAN.md v7 구조대로 생성:
```
JointBuildGS/
├── src/stage2/ (model, renderer, dataloader, loss/, densification, train, colmap_io)
├── src/stage3/ (clustering, ground_surface, plane_intersection, citygml_export, building_instance)
├── configs/ (matrixcity_smoke.yaml, matrixcity_vanilla.yaml)
├── scripts/stage2/ (render_views, export_ply, coverage, rescale_cameras, run_colmap_dense)
├── data/matrixcity/ (images, sparse/0/)
├── data/seongsu/ (legacy, Phase 2+에서 사용)
├── results/ (v7 기준 14개 디렉토리)
├── legacy/planarsplat_ref/
├── Dockerfile, docker-compose.yml
└── docs/
```

## Part B: 기존 자산 마이그레이션

| 항목 | 원본 경로 | 대상 | 상태 |
|------|----------|------|------|
| Synthetic A 코드 | PlanarSplatting/scripts/stage3_synthetic/ | scripts/synthetic_a/ | ✅ |
| Synthetic A 결과 | PlanarSplatting/results/stage3_synthetic_a/ | results/synthetic_a/ | ✅ |
| Stage 3 모듈 | PlanarSplatting/building_to_citygml_v4.py | src/stage3/ (5모듈) | ✅ 동등성 검증 |
| PlanarSplatting legacy | PlanarSplatting/ 핵심 6파일 | legacy/planarsplat_ref/ | ✅ |
| Stage 1 출력물 | PlanarSplatting/planarSplat_ExpRes/ | data/seongsu/ (링크) | ✅ |
| 3D BAG 데이터 | PlanarSplatting/results/synthetic_a/3dbag_raw/ | (Phase 2에서 사용) | 경로 확인됨 |
| Segmentation GT | 미생성 상태 | Phase 2 성수동에서 생성 | ⬜ |

기존 리포지터리: `/media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting/`

Stage 3 모듈 동등성 검증: 5개 건물 중 4/4 matching (bit-identical), 1개 양쪽 동일 실패.

## Part C: MatrixCity 준비

### C-1: 데이터 다운로드
| 항목 | 소스 | 크기 | 상태 |
|------|------|------|------|
| 학습 이미지 (10 blocks) | HuggingFace BoDai/MatrixCity | ~28GB | ✅ |
| COLMAP sparse | CityGSV2 Google Drive | ~1.9GB | ✅ |
| GT depth | HuggingFace small_city_depth_float32/ | ~24.5GB | ⬜ (Step 1-2에서) |
| GT normal | HuggingFace small_city_normal/ | ~47.3GB | ⬜ (Step 1-2에서) |
| GT point cloud | HuggingFace small_city_pointcloud/ | 미확인 | ⬜ (평가 시) |

### C-2: 데이터 구조
```
data/matrixcity/
├── images/      # 5,621 PNG (1920×1080, RGBA→RGB)
└── sparse/0/    # COLMAP binary
    ├── cameras.bin   (1 cam, PINHOLE 1920×1080, f=2318)
    ├── images.bin    (5,621 images)
    └── points3D.bin  (3,826,641 points)
```

이미지 글로벌 재명명: 각 block의 로컬 인덱스를 CityGSV2의 `transforms_train.json` 매핑에 따라 `0000.png~5620.png`으로 변환.

### C-3: GT 구성 확인
| GT 항목 | 존재 | Step 1-1 필요 | 비고 |
|---------|:----:|:------------:|------|
| 이미지 | ✅ | ✅ | 5,621장 |
| 카메라 포즈 | ✅ | ✅ | COLMAP sparse |
| COLMAP sparse PCD | ✅ | ✅ | 3.8M points |
| GT depth | ✅ (미다운) | ❌ | Step 1-2 |
| GT normal | ✅ (미다운) | ❌ | Step 1-2 |
| Semantic GT | 미확인 | ❌ | Step 1-3 |

## Part D: Docker 환경

| 항목 | 값 |
|------|-----|
| Base image | nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 |
| Python | 3.11 (miniconda) |
| PyTorch | 2.4.1+cu121 |
| gsplat | 1.4.0 |
| GPU | RTX 3090 (GPU1, NVIDIA_VISIBLE_DEVICES=1) |
| COLMAP (MVS용) | colmap/colmap:latest (4.0.3 with CUDA, 별도 컨테이너) |

## Part E: 검증

### E-1: Synthetic A 재현
Stage 3 모듈 동등성 검증으로 대체 (4/4 bit-identical). 전체 재실행은 스킵.

### E-2: MatrixCity 데이터 로딩 테스트
```python
ColmapDataset('/workspace/JointBuildGS/data/matrixcity', downscale=1.0)
# frames=5621, pts=3826641
# rgb: (1080, 1920, 3), w2c: (4,4), K: (3,3) — OK
```

### E-3: Smoke test (Step 1-1 사전 검증)
3k iter, photo only → train PSNR 20.60, N: 3.8M→7.9M (densification grow 정상).
CityGSV2 baseline(21.35, 30k)에 3k만에 근접.

## gsplat 2DGS 구현 주의사항 (발견)

| 번호 | 이슈 | 수정 |
|------|------|------|
| 1 | DefaultStrategy key_for_gradient 기본값 "means2d" → 2DGS grow 미작동 | `key_for_gradient="gradient_2dgs"` 명시 |
| 2 | scales shape (N,2) → rasterization_2dgs 오류 | (N,3), dim2 ≈ log(1e-6) |
| 3 | render_normals_from_depth shape 불안정 | 자체 depth_to_normal 구현 |
| 4 | strategy가 params dict 교체 시 model 미반영 | _sync_params_to_model() 추가 |
| 5 | distortion weight 과대 (100) → loss 지배 | 0으로 비활성화 |

## Go/No-Go
**Go.**
- 리포지터리 구조 v7 정렬 완료
- MatrixCity 5,621장 + COLMAP sparse 준비 완료
- 파이프라인 동작 확인 (smoke 3k, PSNR 20.60, densification 정상)
- Docker 환경 검증 완료

## 다음 단계
**Step 1-1: Vanilla 2DGS 30k 학습** — `configs/matrixcity_vanilla.yaml`, CityGSV2 baseline PSNR ~21 비교.
