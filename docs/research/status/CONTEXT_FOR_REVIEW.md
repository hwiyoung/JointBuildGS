# 프로젝트 현황 정리 (2026-04-16)

## 1. 연구 개요

도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화 박사 연구.

**핵심 아이디어**: 미분 가능 렌더링 기반 평면 프리미티브(2DGS) 위에 건물 도메인 지식(벽 법선 수직성, 지붕/지면 관계 등)과 면 단위 구조 인식을 통합하여, 건물의 재구성(기하)과 구조화(의미론)를 공동 최적화.

**파이프라인**:
```
이미지 → [Stage 1: SfM/MVS + Segmentation]
       → [Stage 2: 2DGS 공동 최적화]  ← 핵심 기여
       → [Stage 3: CityGML 변환]
```

**Stage 2 손실 함수**:
```
L = L_photo + L_depth + L_normal + L_nc + L_sem + L_mutual + L_structure

L_photo:     (1-λ)·L1 + λ·(1-SSIM)          렌더링 품질
L_depth:     L1(D_render, D_MVS)              깊이 감독
L_normal:    1 - cos(n_render, n_MVS)         법선 감독
L_nc:        1 - cos(n_render, n_depth)       법선-깊이 일관성
L_sem:       CrossEntropy(semantic)            의미론 감독
L_mutual:    intra-primitive 도메인 규칙       벽 수직, 지붕 경사 등 (메커니즘 1)
L_structure: inter-primitive 구조 정렬         그룹핑 + 평면 일관성 (메커니즘 2)
```

**기술 스택**: gsplat 1.4.0 (2DGS rasterization), PyTorch 2.4.1, Docker 기반 개발

---

## 2. 현재까지 수행한 작업 (Step 1-1)

### 2.1 구축 완료
- Docker 환경 (CUDA 12.1 + torch 2.4.1 + gsplat 1.4.0)
- src/stage2/ 전체 모듈: model.py, renderer.py, dataloader.py, loss/data_fitting.py, densification.py, train.py
- COLMAP PatchMatch MVS로 성수동 depth/normal 생성 (colmap/colmap:latest CUDA 이미지 사용)
- 평가/시각화 스크립트 (render_views.py, export_ply.py, coverage.py)

### 2.2 성수동 30k 학습 결과 — 실패
| 지표 | 우리 결과 | 기대치 |
|------|----------|--------|
| eval PSNR | **16.3 dB** | 20+ dB |
| N (가우시안) | **62k** (135k에서 prune만) | 수십만+ (grow 필요) |
| 렌더링 | 심한 블러, 고스팅 | 건물 구조 식별 가능 |
| 학습 시간 | 518분 (8.6시간) | 30분~1시간 |

### 2.3 발견한 버그들
1. **[치명적] Densification grow 미작동**: gsplat 2DGS는 gradient를 `gradient_2dgs` 키로 전달하지만, DefaultStrategy의 `key_for_gradient`는 `"means2d"` 기본값 → grow가 0회 실행 → 가우시안이 줄기만 함 → **수정 완료** (`key_for_gradient="gradient_2dgs"`)
2. **[중요] Distortion weight 과대**: w_distort=100이 total loss의 99% 지배 → 0으로 비활성화
3. **[중요] L_nc zeros**: gsplat의 render_normals_from_depth shape 불일치 → 자체 depth_to_normal 구현
4. **[중요] Densification params→model 동기화 누락**: gsplat strategy가 params dict를 교체해도 model에 미반영 → _sync_params_to_model() 추가
5. **[경미] scales shape**: (N,2)→(N,3) 수정 (gsplat 2DGS 요구)

### 2.4 데이터 관련 발견
- COLMAP sparse export (thin-recon)에서 135k 포인트 — sparse SfM으로서는 정상 범위, 문제는 densification이 grow하지 않은 것
- COLMAP PatchMatch depth 커버리지: **8.7%** (매우 보수적 필터링)
- Metashape depth 커버리지: **61.6%** (같은 이미지에서 7배 높음)
- 카메라 보정 해상도 불일치 (8270×5476 → 8192×5460 재스케일 필요했음)
- 이미지 파일명 불일치 (_N.jpg suffix)

---

## 3. 방향 전환: 벤치마크 우선 검증

### 3.1 이유
성수동 결과가 나빴는데, 코드 문제인지 데이터 문제인지 분리 불가.
→ 다른 논문에서 이미 잘 된 데이터로 우리 코드를 돌려서 비교.

### 3.2 데이터셋 조사 결과

조사한 논문: AGS (Wu 2024), ULSR-GS (Li 2025), CityGaussianV2 (Liu, ICLR 2025)

**선정 데이터셋: MatrixCity (aerial, small_city)**
- 합성 도시 데이터 (Unreal Engine)
- 5,621 학습 이미지 (1920×1080), 10개 블록
- COLMAP sparse 제공 (CityGSV2 팀이 Google Drive 배포)
- GT depth, normal, point cloud 등 전부 존재 (HuggingFace)
- CityGSV2 baseline: vanilla 2DGS **PSNR ~21** (depth 없이, photo only)

**비교 기준 (직접 확인)**:
| 논문 | MatrixCity vanilla 2DGS PSNR | depth 사용 여부 |
|------|------------------------------|----------------|
| CityGSV2 Table 1 | ~21.35 | 없음 (photo only) |
| CityGSV2 Table 2 ablation | 21.12 (without depth), 22.22 (with depth) | — |
| ULSR-GS | PSNR 미보고 (F1만) | 외부 depth 없음 |

### 3.3 현재 진행 상태
- MatrixCity 5,621장 + COLMAP sparse 다운로드 완료
- gradient_2dgs 버그 수정 적용
- 3k smoke test 완료 (photo only, vanilla 2DGS baseline 조건)
- **결과: train PSNR 20.60, N: 3.8M → 7.9M (densification grow 정상 작동 확인)**
- gradient_2dgs 버그 수정이 핵심이었음. CityGSV2 baseline 21.35에 3k만에 근접.
- 30k 본 학습 시 baseline 도달/초과 기대

---

## 4. 재구성된 실험 계획 (안)

기존 계획은 성수동 데이터에서 단계적으로 구축하는 구조였으나, **벤치마크에서 전체 파이프라인을 먼저 검증한 뒤 실데이터에 적용**하는 구조로 변경 제안.

```
Phase 1: 벤치마크에서 전체 파이프라인 검증 (MatrixCity / GauU-Scene)
  Step 1: Vanilla 2DGS                              ← 현재 진행 중
  Step 2: + Semantic head + L_sem
  Step 3: + L_mutual + depth/normal 감독
  Step 4: + L_structure (그룹핑, inter-primitive)
  Step 5: 통합 + ablation (baseline / joint / joint+structure)
  Step 6: Stage 3 CityGML → val3dity 검증
  Step 7: 조건별 비교 (ablation → CityGML 품질 차이)

Phase 2: 실데이터 적용 (성수동)
  Step 1: 데이터 준비 (Metashape depth, gravity, segmentation)
  Step 2: 전체 파이프라인 학습
  Step 3: Stage 3 CityGML
  Step 4: 평가 + 비교

Phase 3: 최종 비교 + 논문 산출물
  Step 1: Synthetic B (3D BAG → 노이즈/뷰 민감도)
  Step 2: City3D 등 기존 방법 비교
  Step 3: 종합 (논문 표/그래프/결과)
```

### 논의 포인트
1. **Depth/normal 감독 시점**: Step 1-2까지는 photo only, Step 1-3부터 depth/normal 포함 제안. 이유: L_mutual이 법선을 교정하는 loss이므로 normal 감독과 함께 효과 비교가 의미 있음.
2. **벤치마크 데이터셋 선택**: MatrixCity는 합성이라 real data 특성(노이즈, 반사, 비균일 조명)이 없음. GauU-Scene(real UAV)이 더 적합하나 접근 신청 필요(수일).
3. **Vanilla 2DGS baseline**: 원논문의 2DGS는 외부 depth 없이 L_photo + L_nc만 사용. CityGSV2도 baseline 측정 시 동일 조건.
4. **성수동 데이터**: Metashape depth(61.6% coverage)가 COLMAP PatchMatch(8.7%)보다 훨씬 좋음. 성수동 적용 시 Metashape 데이터 활용 예정.

---

## 5. 기술적 세부사항

### 프리미티브 파라미터 (CLAUDE.md)
| 변수 | 차원 | 의미 |
|------|------|------|
| c_i | (N,3) | 중심 |
| q_i | (N,4) | 쿼터니언 → R(q) = [t_u, t_v, n] |
| s_i | (N,3) | 스케일 (dim2 ≈ 0, 평면) |
| opacity | (N,1) | 불투명도 |
| f_i | (N,4) | 의미론 (BG/Roof/Wall/Terrain) |
| SH | (N,K,3) | 색상 (구면조화) |

### gsplat 2DGS 주의사항 (발견한 것)
- `rasterization_2dgs`는 scales (N,3) 요구, dim2 ≈ 0
- Densification gradient: `means2d`가 아닌 `gradient_2dgs` 키 사용
- `render_normals`는 이미 world-frame으로 변환되어 반환
- `render_normals_from_depth`는 shape이 불안정 → 자체 구현 권장

### 환경
- GPU: RTX 3090 ×2 (GPU1 사용)
- Docker: jointbuildgs:dev (CUDA 12.1.1 + torch 2.4.1 + gsplat 1.4.0)
- COLMAP: colmap/colmap:latest (4.0.3 with CUDA) — 별도 컨테이너
- 데이터: /media/innopam/InnoPAM-8TB/
