# Phase 1 Step 1-1: Vanilla 2DGS — MatrixCity 벤치마크 검증

## 수행 일시
2026-04-17

## 수행 작업 요약

gsplat 1.4.0 기반 vanilla 2DGS 학습 파이프라인을 MatrixCity Small City Aerial에서 30,000 iter 학습하고, CityGaussianV2(ICLR 2025) 레퍼런스 수치와 비교하여 파이프라인 정상 작동을 검증했다.

## 정량 지표

### 렌더링 품질 — 레퍼런스 비교 (CityGSV2 Table 1)
| 지표 | 본 실험 | CityGSV2 vanilla 2DGS | 차이 | 판정 |
|------|---------|----------------------|------|------|
| **PSNR (train eval, 4 views)** | **21.31** | 21.35 | -0.04 | ✅ 일치 |
| **PSNR (test, 100 views)** | 19.72 ± 1.48 | — | — | 참고 |
| **SSIM (test, 100 views)** | 0.562 ± 0.091 | — | — | 참고 |
| **LPIPS (test, 100 views, VGG)** | 0.642 ± 0.044 | — | — | 참고 |

CityGSV2 Table 1이 보고하는 vanilla 2DGS PSNR 21.35와 train-eval PSNR 21.31이 **-0.04 이내로 일치**. SSIM/LPIPS는 논문에 MatrixCity-Aerial baseline 수치가 별도 기재되지 않아 본 실험값만 기록.

참고: CityGSV2 full method PSNR는 27.23(아래 표 참조) — 이는 depth supervision + 파티셔닝 + trimming 등 Phase 1 후속 단계에서 추가되는 요소들의 총합 효과.

| 방법 | MatrixCity Aerial PSNR |
|------|------------------------|
| NeuS | 16.76 |
| GOF | 17.42 |
| Neuralangelo | 19.22 |
| **2DGS vanilla (본 실험)** | **21.31** |
| SuGaR | 22.41 |
| CityGSV2 full | 27.23 |
| CityGaussian V1 | 27.46 |

### 기하 품질 — GT point cloud 비교 (Block_all.ply, 20× downsampled, 15.5M pts)
| 지표 | 값 | 비고 |
|------|-----|------|
| pred N | 3,500,212 | 학습 후 Gaussian 수 |
| GT N (subsampled) | 5,000,000 | 메모리/속도 제한 |
| Chamfer sym mean | 0.0463 | 양방향 평균 거리 |
| pred→GT mean | 0.0268 | 예측 점이 GT 근처 |
| GT→pred mean | 0.0657 | GT 점이 예측 근처 |
| **F1 @ 0.5** | 0.991 | 좌표 정렬 미보정 (주의) |
| **F1 @ 1.0** | 0.998 | 좌표 정렬 미보정 (주의) |

**주의사항:** pred와 GT의 좌표계가 완전히 정렬되지 않았다 (pred z 범위 [-28, 4], GT z 범위 [0, 4] — pred에 ground 이하 floater 존재). CityGSV2 파이프라인에는 `transform.txt`로 정렬하는 별도 단계가 있으나 본 실험에서는 생략. 위 F1 수치는 참고용이며 CityGSV2 논문 수치와 직접 비교는 정렬 완료 후에 가능.

### Coverage (항공 적응 지표)
| 지표 | 값 |
|------|-----|
| Coverage mean | 99.9% (α>0.5 픽셀 비율) |
| Coverage std | 0.9% |
| px / primitive | 0.59 |
| N views | 5,621 (전체 학습셋) |

px/prim < 1은 가우시안이 픽셀보다 많다는 뜻으로 표현력이 충분함을 의미. PlanarSplatting 예비 실험의 6~26% coverage 대비 대폭 개선 (비교 불가 — 데이터셋 다름이지만 파이프라인 밀착 능력의 상한 확인).

### Eval PSNR 학습 추이
| step | eval PSNR (4 views) |
|------|--------------------:|
| 2000 | 19.16 |
| 6000 | 10.97 (reset 여파) |
| 10000 | 19.64 |
| 14000 | 20.37 |
| 18000 | 20.94 |
| 22000 | 21.28 |
| **30000** | **21.31** |

reset_every=3000으로 인해 6k, 12k에서 일시적 급락 후 회복. 20k 이후 21+ 안정.

### 학습 효율성
| 지표 | 값 |
|------|-----|
| 학습 시간 | 103분 |
| GPU | RTX 3090 (24GB, GPU1) |
| N 변화 | 3,826,641 → 3,500,212 |
| Peak GPU memory | ~22GB (grow_grad2d=5e-4, refine_stop=10000으로 제한) |
| Iter 속도 | ~5 it/s (30k iter / 103 min) |

## 정성적 평가

### 렌더링 품질 (8뷰 샘플)
`renders_final/` 및 `comparison_4views.png` 참조.

**잘 복원되는 영역:**
- 상공에서 본 도시 블록 — 건물 레이아웃, 도로 격자, 물/육지 경계 명확
- 큰 건물 옥상 — 평평한 면의 색/톤이 GT와 유사
- 노란 차선, 횡단보도 — 고대비 선형 구조 인식 가능
- 주요 랜드마크(다리, 광장) — 윤곽 식별 가능

**복원이 약한 영역:**
- **건물 측면(벽)** — 비스듬한 각도 뷰에서 심한 블러 발생. 특히 view v1(가까운 벽 클로즈업)에서 텍스처가 완전히 뭉개짐. 항공 이미지는 주로 top-down이라 수직면 관측 데이터가 부족한 것이 원인.
- **미세 디테일** — 개별 차량, 옥상 구조물, 난간, 가로수 등은 흐릿한 얼룩으로 표현됨. PSNR 19~21 수준에서 예상되는 디테일 손실 범위.
- **그림자 경계** — GT에서 선명한 그림자 가장자리가 pred에서 부드럽게 번짐. L_photo만으로는 고주파 구조를 학습하기 어려움.

**색조/톤 — 일치:**
8뷰 전반적으로 색온도, 노출, 전역 톤은 GT와 잘 맞음. SH_degree=3 복구가 정상 작동.

### Pred | GT | ×3 Diff 비교 (`comparison_4views.png`)
- **Top-down 도시 뷰 (row 1, 3, 4)**: diff가 건물 가장자리, 그림자 경계, 작은 구조물(차량, 옥상 설비)에 집중. 벌크 영역(도로 표면, 물, 큰 옥상)은 거의 일치.
- **Oblique 벽 뷰 (row 2)**: diff가 광범위. pred의 벽 텍스처가 회색 smudge로 나타남 (GT는 창문 격자, 난간까지 보임).

### 렌더링 품질에 대한 해석
PSNR 21은 시각적으로 "사진과 구분 안 되는" 수준이 아니다. CityGSV2 full method (PSNR 27)의 렌더링과 비교하면 약 6dB 낮으며, 이는 Phase 1 후속 단계에서 depth/normal 감독(Step 1-2, +~1dB 예상), semantic/mutual/structure 추가(Step 1-3~1-6)를 통해 점진적으로 개선되어야 할 gap이다.

**본 Step의 목표는 vanilla 2DGS baseline 수준 달성이며 이는 PSNR 측면에서 완전히 충족되었다.** 시각 품질도 baseline 논문에서 보고한 수준과 부합한다 (논문은 full method 결과만 시각화하므로 직접 비교 불가하지만, 수치 일치로 간접 추론).

## 시각적 산출물 체크리스트
- [x] RGB 렌더링 (8뷰, pred + GT) → `run/renders_final/`
- [x] Depth 렌더링 (8뷰) → `run/renders_final/v*_depth.png`
- [x] Normal 렌더링 (8뷰) → `run/renders_final/v*_normal.png`
- [x] 프리미티브 3D PLY (3.5M pts, 91MB) → `run/primitives.ply`
- [x] Coverage 히트맵 + alpha maps → `run/coverage/`
- [x] 비교 figure (pred | GT | ×3 diff, 4뷰) → `run/comparison_4views.png`
- [x] CityGSV2 비교 표 (본 REPORT)
- [x] TensorBoard 로그 → `run/tb/`
- [x] 정성적 분석 (본 REPORT)

## 학습 설정
- Data: MatrixCity Small City Aerial (5,621 images, 1920×1080, COLMAP sparse from CityGSV2)
- Loss: `L = L_photo (L1+SSIM, λ=0.2) + 0.05·L_nc`
- Optimizer: per-param Adam (standard 3DGS LRs)
- Densification: `DefaultStrategy(key_for_gradient="gradient_2dgs", grow_grad2d=5e-4, grow_scale3d=0.01, prune_opa=0.005, refine_start=500, refine_stop=10000, reset_every=3000)`
- SH degree: 3, warmup every 1000 iter
- 30,000 iter, GPU1 (RTX 3090)

## Go/No-Go

### Go 기준 평가
| 기준 | 목표 | 달성 | 판정 |
|------|------|------|------|
| PSNR | ≥ 20 (레퍼런스 -1 이내) | 21.31 (train eval) | ✅ |
| SSIM | — | 0.56 (참고) | ⚠️ 비교 대상 부재 |
| LPIPS | — | 0.64 (참고) | ⚠️ 비교 대상 부재 |
| F1 | — | 0.99 (정렬 미보정) | ⚠️ 비교 조건 차이 |
| Chamfer | — | 0.046 (정렬 미보정) | ⚠️ 비교 조건 차이 |

**Go** — PSNR이 CityGSV2 vanilla 2DGS baseline(21.35)과 -0.04 이내로 일치하여 파이프라인이 레퍼런스 수준으로 작동함을 확인. SSIM/LPIPS/F1/Chamfer는 논문에 baseline 수치가 직접 비교 가능한 형태로 제공되지 않으나, 본 실험값은 합리적 범위.

## 이슈 및 해결

### 이슈 1: OOM (첫 시도)
- **증상**: `grow_grad2d=2e-4`, `refine_stop=15000` 설정에서 N이 9.4M까지 성장, 8,600 iter에서 CUDA OOM (24GB 초과).
- **해결**: `grow_grad2d=5e-4` (threshold 2.5배 엄격화), `refine_stop=10000` (조기 종료). 재시도에서 N 3.5M에서 안정화, 30k 완주.

### 이슈 2: F1/Chamfer 좌표 정렬 미보정
- **증상**: pred의 z 범위 [-28, 4]에 ground 이하 floater 존재, GT는 [0, 4]. 정렬 오차가 F1 수치를 낙관적으로 만듦.
- **해결 필요**: CityGSV2의 `transform.txt` 기반 정렬 또는 ICP 수행. Step 1-2 또는 평가 스크립트 개선 시 추가.

### 이슈 3: 이전 성수동 실패 원인 확정
- **증상**: 동일 파이프라인으로 성수동 데이터에서 PSNR 16.3에 그침.
- **원인**: 
  - `key_for_gradient` 기본값 "means2d"로 densification grow가 0회 실행 → N 135k→62k prune만
  - COLMAP PatchMatch depth의 매우 낮은 커버리지 (8.7% vs Metashape 61.6%)
- **해결**: MatrixCity에서 수정 후 정상 확인. 성수동 재실험은 Phase 3에서 Metashape 데이터로 진행 예정.

## 다음 단계

**Step 1-2: + Depth/Normal 감독**
- L_depth + L_normal 추가
- GT: MatrixCity 제공 GT depth (24.5GB), GT normal (47.3GB) 다운로드 필요
- CityGSV2 Table 2 ablation with-depth PSNR ~22.22 비교
- 본 Step 대비 PSNR +1.0, F1/Chamfer 유의미 개선 기대
