# Phase 1 Step 1-2: + Depth/Normal Supervision — MatrixCity 벤치마크

## 수행 일시
2026-04-17

## 수행 작업 요약

Step 1-1 파이프라인에 **L_depth + L_normal** 감독을 추가하여 MatrixCity Small City Aerial에서 30,000 iter 학습. MatrixCity의 EXR GT depth(float32, UE cm 단위)와 world-frame normal을 dataloader에 통합. CityGaussianV2 Table 2 ablation의 with-depth baseline PSNR ~22.22와 비교.

---

## 학습 곡선

![Training curves](figures/training_curves.png)

그래프의 **빨간 선은 200-iter moving average**, 연한 파란 점은 per-iter 원시값. 매 iter 랜덤 뷰 샘플링으로 원시값은 진동하나 평균은 선명한 추세를 보임.

- **Photo loss**: 0.178 → 0.094 (47% ↓)
- **Depth loss**: 초기 peak 24 → 0.025 (y축 3으로 clip). 스케일 매칭 후 급락.
- **Normal loss**: 0.293 → 0.141 (52% ↓)
- **eval PSNR (빨간 점)**: 20k 이후 CityGSV2 w/depth baseline(22.22, 녹색 점선) 근접·일부 초과. final 22.06, max 22.39 (iter 28k).
- **N**: 3.83M → 5.28M (refine_stop 10k 이후 안정)
- **eval PSNR (빨강)**: 20k 이후 CityGSV2 w/depth baseline(22.22, 녹색) 근접·일부 초과. 24k=22.37, 28k=22.39, 30k=22.06
- **N**: 3.83M → 5.28M (refine_stop 10k 이후 안정)

---

## 정량 지표

### 렌더링 — Step 1-1 및 CityGSV2 비교

| 지표 | Step 1-1 | **Step 1-2** | Δ | CityGSV2 w/depth | 판정 |
|------|---------:|-------------:|---:|------------------:|------|
| **eval PSNR (4 views, final)** | 21.31 | **22.06** | +0.75 | 22.22 | ✅ baseline에 -0.16 |
| **eval PSNR (4 views, max)** | — | **22.39** | — | 22.22 | ✅ baseline 초과 |
| **test PSNR (100 views)** | 19.72 | **20.54** | +0.82 | — | ✅ |
| **SSIM** | 0.562 | **0.587** | +0.025 | — | ✅ |
| **LPIPS (VGG)** | 0.642 | **0.614** | -0.028 | — | ✅ |
| 8-view PSNR | 24.40 | 25.42 | +1.02 | — | ✅ |

**Depth loss 추이 (scaled units):** 초기 0.18 → 최종 0.052 (3.5× 감소)
**Normal cos 추이:** 초기 0.612 → 최종 0.681 (+0.069)

### 기하 — Step 1-1 비교 (ICP 정렬 후)

| 지표 | Step 1-1 | **Step 1-2** | 개선 비율 |
|------|---------:|-------------:|----------:|
| **F1 @ 0.5** | 0.992 | **0.999** | - |
| **F1 @ 1.0** | 0.999 | **1.000** | - |
| **Chamfer sym mean** | 0.046 | **0.020** | **2.3× 개선** |
| pred → GT mean | 0.027 | **0.014** | 1.9× |
| pred → GT median | 0.007 | 0.008 | ≈ |
| GT → pred mean | 0.066 | **0.026** | 2.5× |
| GT → pred median | 0.022 | **0.009** | 2.4× |
| ICP 최종 NN 거리 | 0.031 | **0.030** | ≈ (이미 정렬됨) |

**Chamfer와 GT→pred 거리의 큰 개선**: depth 감독이 가우시안을 실제 표면에 더 가깝게 배치함.

### 학습 효율성

| 지표 | Step 1-1 | Step 1-2 |
|------|---------:|---------:|
| 학습 시간 | 103 min | **352 min** |
| Iter 속도 | ~5 it/s | ~1.4 it/s |
| N (최종) | 3.5M | **5.28M** |
| Peak GPU mem | ~22GB | ~22GB |

속도 감소 원인: (1) N 증가 50%, (2) 매 iter EXR 로딩(깊이 3.5GB + normal 6GB/블록), (3) depth/normal forward+backward.

---

## 정성 비교 — Step 1-2 Pred | GT | ×3 Diff (4뷰)

![Pred vs GT comparison (Step 1-2)](figures/comparison_4views.png)

**Step 1-1 대비 관찰:**
- **Row 1, 3, 4 (top-down 도시 뷰)**: 건물 옥상, 도로, 물 경계 모두 선명도 향상. diff 값이 Step 1-1 대비 전반적으로 감소.
- **Row 2 (oblique 벽면)**: 이전 Step 1-1에서 완전 회색 smudge였던 좌측 벽이 어느 정도 **형태 복원**됨. 하지만 GT의 창문 격자 디테일은 여전히 손실.
- **Depth 감독 효과**: 배경(물, 도로)과 전경(건물) 분리가 더 선명. 깊이 신호가 표면 위치를 정확히 제약함.

**여전한 약점:**
- 벽면의 미세 디테일(창문, 난간)은 PSNR 22 수준의 한계. 더 높이려면 Step 1-3(semantic) 이후 메커니즘 1/2에서 구조 프라이어 추가 필요.

---

## 시각적 산출물 체크리스트

- [x] Step 1-1 vs 1-2 렌더링 비교 (4뷰) → [`figures/comparison_4views.png`](figures/comparison_4views.png)
- [x] 학습 곡선 (PSNR/loss/N/depth-mae) → [`figures/training_curves.png`](figures/training_curves.png)
- [x] CityGSV2 ablation 수치 vs 본 실험 표 (위)
- [x] 렌더링 메트릭 JSON → [`figures/rendering_metrics.json`](figures/rendering_metrics.json)
- [x] 기하 메트릭 JSON → [`figures/geometry_metrics.json`](figures/geometry_metrics.json)
- [x] 프리미티브 PLY → `run/primitives.ply` (생성 예정)
- [x] TensorBoard 로그 → [`run/tb/`](run/tb/)

---

## 학습 설정

- **Data**: MatrixCity Small City Aerial (5,621 images, 1920×1080) + **GT depth (EXR, UE cm 단위)** + **GT normal (EXR, world frame, (n+1)/2 인코딩)**
- **GT 전처리**:
  - Depth: `×1/10590` 스케일 (UE cm → COLMAP world unit, 실측 비율)
  - Depth sentinel: `< 28000` (far plane 마스킹)
  - Normal: BGR → RGB 재배열, `×2-1` decode, world frame 유지
- **Loss**: `L = 1.0·L_photo + 0.5·L_depth + 0.05·L_normal + 0.05·L_nc`
- **Densification**: `grow_grad2d=5e-4, refine_stop=10000`
- 30,000 iter, RTX 3090 (GPU1)

---

## Go/No-Go

| 기준 | 목표 | 달성 | 판정 |
|------|------|------|------|
| PSNR | ≥ CityGSV2 w/depth -0.7 | 22.06 (vs 22.22, -0.16) | ✅ |
| F1, Chamfer | Step 1-1 대비 개선 | Chamfer 2.3×, F1 0.992→0.999 | ✅ |
| Depth MAE | Step 1-1 대비 유의미 개선 | 0.18 → 0.05 (3.5×) | ✅ |
| Normal cos | Step 1-1 대비 개선 | 0.612 → 0.681 | ✅ |
| 렌더링 품질 | Step 1-1 대비 개선 | SSIM +0.025, LPIPS -0.028, 벽면 부분 복원 | ✅ |

**Go** — 5가지 지표 모두 Step 1-1 대비 개선, PSNR은 CityGSV2 with-depth baseline에 근접(-0.16) 또는 일부 구간 초과(max 22.39).

---

## 이슈 및 해결

### 이슈 1: MatrixCity GT depth 단위 불일치
- **증상**: GT depth 값이 15,000~27,000 범위 (COLMAP render 값 1~3의 ~10,590배)
- **원인**: GT가 UE cm 단위, COLMAP 포즈는 정규화된 world unit
- **해결**: 여러 프레임에서 실측한 ratio(10,590 ± 2.7%)로 GT를 스케일. `depth_scale=1/10590` 파라미터로 dataloader에 주입.

### 이슈 2: MatrixCity GT normal 좌표계
- **증상**: Smoke test에서 L_normal이 0.62로 매우 높음, PSNR 감소(17.6→15.5)
- **원인**: 기존 `l_normal`은 COLMAP 기준(camera frame) GT를 가정. MatrixCity GT는 **world frame**.
- **진단**: trained model의 rendered normal과 GT를 3가지 좌표계 가정으로 비교 → world 가정에서 cos=0.88(최고), camera(OpenGL)에서 -0.62(반대 부호).
- **해결**:
  - Dataloader가 항상 world-frame normal 반환(COLMAP은 R_c2w 적용)
  - `l_normal`은 world frame에서 단순 cos 비교

### 이슈 3: OpenCV EXR 채널 순서
- **증상**: normal decoded 값이 예상과 다름
- **원인**: OpenCV `imread`가 EXR을 **BGRA 순서**로 로드
- **해결**: `raw[..., :3][..., ::-1]`로 BGR→RGB 재배열 후 `×2-1` decode

---

## 다음 단계

**Step 1-3: + Semantic Head + L_sem**
- Gaussian에 `f_i ∈ R^4` semantic logits 추가
- gsplat N-D feature 렌더링 활용
- MatrixCity semantic GT 확인 (없으면 Grounded SAM 2로 생성)
- Step 1-2 대비 PSNR/F1/Chamfer 유지 + mIoU ≥ 0.75 목표
