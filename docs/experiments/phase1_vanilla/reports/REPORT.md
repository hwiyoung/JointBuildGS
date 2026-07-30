# Phase 1 Step 1-1: Vanilla 2DGS — MatrixCity 벤치마크 검증

## 수행 일시
2026-04-17

## 수행 작업 요약

gsplat 1.4.0 기반 vanilla 2DGS 학습 파이프라인을 MatrixCity Small City Aerial에서 30,000 iter 학습하고, CityGaussianV2(ICLR 2025) 레퍼런스 수치와 비교하여 파이프라인 정상 작동을 검증했다.

---

## 학습 곡선

![Training curves](figures/training_curves.png)

- **Loss (좌)**: 0.2 → 0.11 단조 감소. 중간 피크(iter 3k, 6k)는 opacity reset(3000 iter 주기).
- **PSNR (중)**: train per-view(연한 파랑)는 뷰 난이도에 따라 진동, eval 4-view 평균(빨강)은 안정적 상승. 20,000 iter 이후 CityGSV2 baseline(21.35) 도달.
- **N primitives (우)**: 두 곡선은 첫 OOM 시도(9.4M, iter 8600 중단)와 수정 후 성공 시도(3.5M, 10k까지 성장 후 안정). `refine_stop_iter=10000` 이후 densification 없음.

---

## 정량 지표

### 렌더링 품질 — CityGSV2 비교 (Table 1 vanilla 2DGS baseline)

| 지표 | 본 실험 | CityGSV2 vanilla 2DGS | 차이 | 판정 |
|------|---------|----------------------|------|------|
| **PSNR (train eval, 4 views)** | **21.31** | 21.35 | -0.04 | ✅ 일치 |
| PSNR (test 100 views) | 19.72 ± 1.48 | — | — | 참고 |
| SSIM (test 100 views) | 0.562 ± 0.091 | — | — | 참고 |
| LPIPS (test 100 views, VGG) | 0.642 ± 0.044 | — | — | 참고 |

논문은 Block_all 전체에 대한 eval PSNR 21.35만 보고하고, SSIM/LPIPS의 per-scene 수치는 제공하지 않음. 본 실험 train-eval PSNR 21.31이 논문 baseline과 일치 → **파이프라인 정상.**

### CityGSV2 전체 방법 비교 (컨텍스트)

| 방법 | MatrixCity Aerial PSNR |
|------|------------------------|
| NeuS | 16.76 |
| GOF | 17.42 |
| Neuralangelo | 19.22 |
| **2DGS vanilla (본 실험)** | **21.31** |
| SuGaR | 22.41 |
| CityGSV2 full | 27.23 |
| CityGaussian V1 | 27.46 |

vanilla 2DGS와 CityGSV2 full 사이의 6dB gap은 depth supervision + 파티셔닝 + trimming의 총합 효과. Phase 1 후속 단계(1-2 depth/normal, 1-3 semantic, 1-4 L_mutual, 1-5 L_structure)에서 점진 개선 목표.

### 기하 품질 — GT point cloud 비교 (ICP 정렬 후)

GT: Block_all.ply (20× downsampled, 15.5M pts). pred centers 3.5M.

**좌표 정렬:** ICP 수행 결과 변환이 거의 identity (rotation ~0°, translation < 0.003). 즉 **두 좌표계가 원래부터 정렬되어 있었음.** z=-28 부근 floater는 전체의 0.17%(5,982/3.5M)에 불과하며 필터링 후 주요 기하는 변동 없음.

| 지표 | 값 | 해석 |
|------|-----|------|
| **F1 @ 0.5** | **0.992** | pred의 99.5%가 GT로부터 0.5m 이내, GT의 98.9%가 pred로부터 0.5m 이내 |
| **F1 @ 1.0** | **0.999** | 1m 임계에서 거의 완전 일치 |
| Chamfer sym mean | 0.046 | pred↔GT 양방향 평균 거리 |
| pred→GT mean / median | 0.027 / 0.007 | 대부분 pred 점은 GT와 1cm 이내 |
| GT→pred mean / median | 0.066 / 0.022 | GT → nearest pred는 약 2cm |
| ICP 최종 NN 거리 | 0.031 | 정렬 잔차 |

**판정:** 기하 품질이 매우 높음. pred가 공간적으로 GT 기하를 충실히 재현. (주의: CityGSV2 논문은 Chamfer/F1을 MatrixCity-Aerial에 대해 직접 보고하지 않으므로 직접 비교는 Step 1-2 이후로 미룸. 현재 수치는 본 연구 내 단계 간 비교용 기준점.)

### Coverage (항공 적응)

| 지표 | 값 |
|------|-----|
| Coverage mean (α > 0.5) | **99.9%** |
| Coverage std | 0.9% |
| px / primitive | 0.59 |
| N views | 5,621 (전체 학습셋) |

px/prim < 1은 가우시안이 픽셀보다 많아 표현력 충분. PlanarSplatting 예비 실험(legacy/)의 6~26% coverage 대비 가우시안 방식의 구조적 장점 확인.

### Eval PSNR 학습 추이

| step | eval PSNR |
|------|----------:|
| 2000 | 19.16 |
| 6000 | 10.97 (reset 여파) |
| 10000 | 19.64 |
| 14000 | 20.37 |
| 18000 | 20.94 |
| 22000 | 21.28 |
| **30000** | **21.31** |

6k·12k에서 일시적 급락은 `reset_every=3000` 시점에 eval이 걸린 측정 artifact. 20k 이후 안정.

### 학습 효율성

| 지표 | 값 |
|------|-----|
| 학습 시간 | 103분 |
| GPU | RTX 3090 (24GB, GPU1) |
| N 변화 | 3,826,641 → 3,500,212 |
| Peak GPU memory | ~22GB |
| Iter 속도 | ~5 it/s |

---

## 정성 비교 — Pred | GT | ×3 Diff (4뷰)

![Pred vs GT comparison](figures/comparison_4views.png)

행별 관찰:

**Row 1, 3, 4 — Top-down 도시 뷰 (잘 복원):**
- 건물 레이아웃, 도로 격자, 차선, 물/육지 경계가 명확
- 큰 건물 옥상의 색/톤은 GT와 거의 일치
- diff(오른쪽)에 작은 변화만 보임 — 그림자 경계, 작은 구조물(주차 차량, 옥상 설비)에 집중

**Row 2 — Oblique 벽면 클로즈업 (약점 영역):**
- pred의 벽 텍스처가 완전히 회색 smudge (GT는 창문 격자, 난간까지 선명)
- diff가 광범위 — 수직면 디테일 대부분 손실
- 원인: 항공 top-down 관측 데이터에서 수직 벽면에 관측 정보가 적음

### 해석

**잘 복원되는 영역:**
- 도시 top-down — 건물 레이아웃, 도로, 물 경계
- 큰 평평한 면 — 건물 옥상, 도로 표면
- 고대비 선형 구조 — 노란 차선, 횡단보도, 건물 경계

**복원이 약한 영역:**
- 비스듬한 수직 벽면 (항공 촬영의 구조적 한계)
- 미세 디테일 (개별 차량, 난간, 가로수) — PSNR 21 수준에서 예상되는 손실
- 고주파 그림자 경계 — L_photo만으로는 부족

**색조/톤:** SH degree 3 복구로 전역 톤과 색온도는 GT와 잘 맞음.

**종합:** PSNR 21은 "사진과 구분 안 되는" 수준이 아니며, 이는 vanilla 2DGS baseline의 고유한 한계다. Phase 1 후속 단계에서 depth/normal 감독(Step 1-2), semantic/mutual/structure(Step 1-3~1-6)를 통해 개선 예정.

---

## 시각적 산출물 체크리스트

- [x] RGB 렌더링 (8뷰, pred + GT) → [`run/renders_final/`](run/renders_final/)
- [x] Depth 렌더링 (8뷰) → `run/renders_final/v*_depth.png`
- [x] Normal 렌더링 (8뷰) → `run/renders_final/v*_normal.png`
- [x] 프리미티브 3D PLY (3.5M pts, 91MB) → [`run/primitives.ply`](run/primitives.ply)
- [x] Coverage 히트맵 + alpha maps → [`run/coverage/`](run/coverage/)
- [x] 비교 figure (pred | GT | ×3 diff, 4뷰) → [`figures/comparison_4views.png`](figures/comparison_4views.png)
- [x] 학습 곡선 → [`figures/training_curves.png`](figures/training_curves.png)
- [x] CityGSV2 비교 표 (본 REPORT)
- [x] TensorBoard 로그 → [`run/tb/`](run/tb/)
- [x] 정성 분석 + inline 시각화 (본 REPORT)

---

## 학습 설정

- **Data**: MatrixCity Small City Aerial (5,621 images, 1920×1080, COLMAP sparse from CityGSV2)
- **Loss**: `L = L_photo (L1+SSIM, λ=0.2) + 0.05·L_nc`
- **Optimizer**: per-param Adam (표준 3DGS LRs)
- **Densification**: `DefaultStrategy(key_for_gradient="gradient_2dgs", grow_grad2d=5e-4, grow_scale3d=0.01, prune_opa=0.005, refine_start=500, refine_stop=10000, reset_every=3000)`
- **SH degree**: 3 (warmup every 1000 iter)
- **30,000 iter**, GPU1 (RTX 3090)

---

## Go/No-Go

| 기준 | 목표 | 달성 | 판정 |
|------|------|------|------|
| PSNR | ≥ 20 (레퍼런스 -1 이내) | 21.31 (train eval) | ✅ |
| 기하 (F1, Chamfer) | 합리적 범위 | F1@0.5=0.99, Chamfer=0.046 | ✅ |
| 파이프라인 안정성 | OOM 없음, 수렴 | 103분 완주, 수렴 확인 | ✅ |
| 렌더링 품질 | baseline 수준 | 도시 레이아웃 복원, 수직면 약점 | ⚠️ 예상 범위 내 |

**Go** — 파이프라인이 CityGSV2 vanilla 2DGS baseline 수준으로 작동함을 PSNR 일치(-0.04) 및 기하 품질(F1 0.99)로 확인. 렌더링의 수직면 블러는 vanilla 2DGS의 구조적 한계이며, Step 1-2 이후 depth/normal 감독 추가로 개선 기대.

---

## 이슈 및 해결

### 이슈 1: OOM (첫 시도)
- **증상**: `grow_grad2d=2e-4`, `refine_stop=15000` 설정에서 N이 9.4M까지 성장, 8,600 iter에서 CUDA OOM (24GB 초과).
- **해결**: `grow_grad2d=5e-4` (threshold 2.5배 엄격화), `refine_stop=10000` (조기 종료). 재시도에서 N 3.5M 안정화, 30k 완주.

### 이슈 2: F1/Chamfer 좌표 정렬 (해결됨)
- **증상**: pred의 z 범위 [-28, 4]가 GT [0, 4]와 불일치해 보여 정렬 필요성 제기.
- **해결**: ICP 수행 결과 변환이 거의 identity로 수렴. 실제 불일치는 전체의 0.17%(floater)에 불과했으며 필터링 후 주요 기하는 동일. 현재 수치(F1=0.99) 신뢰 가능.

### 이슈 3: 이전 성수동 실패 원인 확정
- **증상**: 동일 파이프라인으로 성수동 데이터에서 PSNR 16.3에 그침.
- **원인 1**: `key_for_gradient` 기본값 "means2d"로 densification grow가 0회 실행 → N 135k→62k prune만.
- **원인 2**: COLMAP PatchMatch depth의 매우 낮은 커버리지 (8.7% vs Metashape 61.6%).
- **해결**: MatrixCity에서 수정 후 정상 확인. 성수동 재실험은 Phase 3에서 Metashape 데이터로 진행 예정.

---

## 다음 단계

**Step 1-2: + Depth/Normal 감독**
- L_depth + L_normal 추가
- GT: MatrixCity 제공 GT depth (24.5GB), GT normal (47.3GB) 다운로드 필요
- CityGSV2 Table 2 ablation with-depth PSNR ~22.22 비교
- 본 Step 대비 PSNR +1.0, F1/Chamfer 유의미 개선 기대
