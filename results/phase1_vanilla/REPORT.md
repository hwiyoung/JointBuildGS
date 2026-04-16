# Phase 1 Step 1-1: Vanilla 2DGS — MatrixCity 벤치마크 검증

## 수행 일시
2026-04-17

## 수행 작업 요약
MatrixCity Small City Aerial에서 vanilla 2DGS (L_photo + L_nc) 30k iter 학습.
CityGSV2 baseline과 비교하여 파이프라인 정상 작동 확인.

## 정량 지표

### 레퍼런스 비교
| 지표 | 본 실험 | CityGSV2 baseline | 차이 | 출처 |
|------|---------|-------------------|------|------|
| eval PSNR | **21.31** | 21.12 | **+0.19** | CityGSV2 Table 1-2 |
| 8-view PSNR | 24.40 | — | — | — |
| N (primitives) | 3.5M | — | — | — |
| 학습 시간 | 103 min | — | — | RTX 3090 |

### Eval PSNR 추이
| step | eval PSNR |
|------|-----------|
| 10000 | 19.64 |
| 14000 | 20.37 |
| 18000 | 20.94 |
| 22000 | 21.28 |
| 24000 | 21.35 |
| 28000 | 21.26 |
| 30000 | **21.31** |

20k 이후 안정적으로 21+ 유지.

### Train 지표
| 지표 | 초기 | 최종 |
|------|------|------|
| train PSNR | 17.59 | 23.86 |
| loss/photo | 0.187 | 0.156 |
| loss/nc | 0.713 | 0.139 |
| N | 3,826,641 | 3,500,212 |

## 시각적 산출물 체크리스트
- [x] RGB 렌더링 (8뷰, pred + GT) → `run/renders_final/`
- [x] Depth 렌더링 (8뷰) → `run/renders_final/`
- [x] Normal 렌더링 (8뷰) → `run/renders_final/`
- [x] 프리미티브 PLY (3.5M pts, 91MB) → `run/primitives.ply`
- [x] TensorBoard 로그 → `run/tb/`
- [x] CityGSV2 비교 표 (위)

## 학습 설정
- Data: MatrixCity Small City Aerial (5,621 images, 1920×1080)
- Loss: L_photo (L1+SSIM, λ=0.2) + L_nc (w=0.05)
- Densification: grow_grad2d=5e-4, refine_stop=10000, reset_every=3000
- SH degree: 3, 30,000 iter
- GPU: RTX 3090 (GPU1)

## Go/No-Go
**Go.**
- eval PSNR 21.31 ≥ CityGSV2 baseline 21.12 → 레퍼런스 달성
- Densification 정상 작동 (grow + prune 균형, OOM 없음)
- 렌더링 품질 시각적으로 양호 (건물 구조, 도로 표시 식별 가능)

## 이슈 및 해결
### 이슈 1: OOM (1차 시도)
grow_grad2d=2e-4, refine_stop=15000 → N이 9.4M까지 성장, 8600 iter에서 OOM.
**해결:** grow_grad2d=5e-4, refine_stop=10000으로 조정. N이 3.5M에서 안정화.

### 이전 성수동 실패 원인 확정
gradient_2dgs 버그로 densification grow가 0회 → 135k→62k prune만. 수정 후 MatrixCity에서 정상 확인.

## 다음 단계
**Step 1-2: + Depth/Normal 감독**
MatrixCity GT depth/normal 다운로드 후 L_depth + L_normal 추가.
CityGSV2 with-depth baseline PSNR ~22.22 비교.
