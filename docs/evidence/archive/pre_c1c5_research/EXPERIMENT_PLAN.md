# 실험계획 (v7 — 벤치마크 우선 검증, 레퍼런스 수치 기반)

> **ARCHIVED HISTORICAL EVIDENCE / NOT EXECUTION AUTHORITY.** 이 문서는 기존 MatrixCity/3D BAG/
> GauU-Scene/성수동 및 4조건 loss-ablation 프로그램의 실행 기록이다. 2026-07-31
> `DEC-P1-008` 이후 새 작업은 [00_RESEARCH_CHARTER.md](../../../research/00_RESEARCH_CHARTER.md)부터
> [06_DECISION_LOG.md](../../../research/06_DECISION_LOG.md)까지의 C1–C5 정본과 승인된 exact Task
> Packet을 따른다. 이 파일 안의 “진행해줘” prompt는 명시적인 legacy reproduction
> task가 아니면 실행하지 않는다.

## 연구 계획의 논리

**벤치마크에서 방법론 검증 → 실데이터 시연** 순서.

Phase 1: MatrixCity Small City Aerial에서 Stage 2 각 단계가 기존 항공 2DGS 연구들의 수준을 달성하는지 확인. 레퍼런스 수치(CityGaussianV2, ULSR-GS, AGS)와 직접 비교.

Phase 2: 3D BAG 합성 렌더링에서 Stage 2+3 통합 검증. GT CityGML이 있으므로 val3dity, 면 IoU로 방법론의 최종 효과 검증. Ablation 4조건으로 메커니즘 1/2 개별 기여 분리.

Phase 3: Real UAV(GauU-Scene) + 순차 파이프라인 비교 + 실데이터 시연.

Phase 1은 "파이프라인이 레퍼런스 수준으로 작동하는가"의 검증, Phase 2가 방법론의 핵심 검증, Phase 3가 일반화/비교/실환경 시연.

## 현재 리포지터리 구조 (gsplat 의존)

```
JointBuildGS/
├── src/                    # 재사용 알고리즘·파이프라인·앱
├── configs/                # 재사용 가능한 설정
├── scripts/                # 기능별 재현 실행기와 저장소 점검
├── tests/                  # 재사용 코드·workstream 검증
├── docs/                   # research / experiments / evidence / figs
├── phases/                 # 진행 단계의 잠금·전용 절차·compact receipt
└── artifacts/manifests/    # 외부 payload와 quarantine resolver
```

대용량 raw/generated payload는 `JBGS_ARTIFACT_ROOT`가 가리키는 sibling artifact storage가
소유한다. 과거 `data/`, `results/`, `legacy/` 경로를 전제로 쓴 아래 단계별 프롬프트는 당시
실행 기록이며, 현재 실행 시에는 각각 external payload, `docs/experiments/`, quarantine manifest로
해석한다. 이 이동은 `artifacts/manifests/`와 `docs/research/repository/`에 기록되어 있다.

## 현재 상태

| 항목 | 상태 |
|------|------|
| Stage 1 (성수동 COLMAP + Grounded SAM) | 완료 |
| PlanarSplatting 예비 실험 | 완료, external quarantine + manifest |
| Synthetic A (Stage 3 단독) | 완료 |
| gsplat 기반 파이프라인 구축 시작 | 진행 중 (MatrixCity smoke test) |

## 데이터셋 용도 분리

**Stage 2 재구성 품질 검증:**
- MatrixCity Small City Aerial (메인) — CityGSV2 레퍼런스 비교
- GauU-Scene (서브, real UAV) — ULSR-GS 레퍼런스 비교

**Stage 3 CityGML 품질 검증:**
- 3D BAG 합성 렌더링 (Synthetic B) — GT CityGML 있음, val3dity로 end-to-end 평가

**실데이터 정성 시연:**
- 성수동 (Metashape depth 사용)

## Ablation 4조건

| 조건 | 손실 함수 | 검증 대상 |
|------|----------|---------|
| Baseline | L_photo + L_depth + L_normal + L_nc + L_sem | 두 메커니즘 모두 없음 |
| Mutual only | + L_mutual | 메커니즘 1 (intra) 단독 |
| Structure only | + L_structure | 메커니즘 2 (inter) 단독 |
| Both | + L_mutual + L_structure | 동시 작용 |

핵심 비교와 해석 프레임:
- **Structure only vs Both:** 메커니즘 1 없이 메커니즘 2만 작동하면, 기하 정렬이 양방향 gradient를 통해 의미론에 피드백되지 않음. Both에서 better면 "메커니즘 1의 양방향 gradient가 메커니즘 2의 그룹핑 품질을 개선한다"는 순환 효과 입증.
- **Mutual only vs Both:** per-primitive 교정만 vs 면 단위 정렬 추가. Both에서 better면 구조 정렬의 추가 가치 입증.
- **Both vs Mutual + Structure 합:** 시너지(Both > 합) / 독립(≈) / 간섭(Both < 합).

---

## Phase 1: MatrixCity에서 Stage 2 검증

### Step 1-0: 리포지터리 셋업 + 마이그레이션 + MatrixCity 준비

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-0을 진행해줘.

=== Part A: 리포지터리 구조 ===
EXPERIMENT_PLAN.md 구조대로 디렉토리 생성.

=== Part B: 기존 자산 마이그레이션 ===
기존 리포지터리 경로: [사용자 제공]
1. Synthetic A 코드 → scripts/stage3_readout/synthetic_a/, 결과 → results/synthetic_a/
2. Stage 3 코드를 src/stage3/로 분리
3. PlanarSplatting 예비 실험을 legacy/
4. Stage 1 출력물을 data/seongsu/에 배치

=== Part C: MatrixCity 준비 ===
1. MatrixCity Small City Aerial 다운로드 (CityGSV2 Google Drive COLMAP sparse + HuggingFace GT)
2. data/matrixcity/small_city_aerial/에 배치
3. GT 구성 확인: 이미지, 카메라 포즈, COLMAP sparse, GT depth, GT normal, GT point cloud
4. 가능하면 semantic GT도 확인 (없으면 Step 1-3에서 Grounded SAM으로 생성)

=== Part D: 검증 ===
1. Synthetic A 재현 확인
2. MatrixCity 데이터 로딩 테스트

results/phase1_setup/REPORT.md 작성.
```

### Step 1-1: Vanilla 2DGS (photo only) — 파이프라인 정상성 검증

**목적:** gsplat 기반 2DGS 파이프라인이 레퍼런스 수준으로 작동하는지 확인. 구현 버그 식별.

**레퍼런스:** CityGaussianV2 Table 1-2, MatrixCity Small City Aerial에서 vanilla 2DGS PSNR 약 21.12 (depth 없이, photo only).

**Go 기준:**
- PSNR ≥ 20 (레퍼런스 -1 이내)
- SSIM, LPIPS도 CityGSV2 수치 대비 합리적 범위
- F1 (GT point cloud 대비, 임계값 0.5m/1.0m), Chamfer Distance도 CityGSV2/ULSR-GS 수준

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-1을 진행해줘.

목표: gsplat 기반 vanilla 2DGS 학습 파이프라인 구축 + MatrixCity에서 CityGSV2 수준 달성.

=== 파이프라인 구축 ===
src/stage2/:
- model.py: 2DGS 파라미터 (c, q → t_u/t_v, s, opacity, SH)
- renderer.py: gsplat rasterization_2dgs 호출 → RGB, depth, normal
- loss/data_fitting.py: L_photo (L1+SSIM), L_nc (렌더링 normal ≈ depth 유도 normal)
- densification.py: gsplat DefaultStrategy (key_for_gradient="gradient_2dgs" 주의)
- dataloader.py: MatrixCity COLMAP 로더
- train.py: 학습 루프 (30000 iter)

**구현 주의사항 (RESEARCH_CONTEXT.md §12 참조):**
- DefaultStrategy(key_for_gradient="gradient_2dgs") 필수 (기본값 "means2d"면 grow 미작동)
- scales shape (N,3), dim2 ≈ 0
- L_nc: depth_to_normal 자체 구현 권장 (gsplat render_normals_from_depth 불안정)
- Densification 후 _sync_params_to_model() 호출

=== 학습 ===
L = L_photo + λ_nc·L_nc (vanilla 2DGS)
MatrixCity Small City Aerial, 30000 iter.

=== 평가 ===
렌더링: PSNR, SSIM, LPIPS → CityGSV2 Table 1 비교
기하: F1 (0.5m, 1.0m 임계), Chamfer Distance → CityGSV2/ULSR-GS 비교
추가: 프리미티브 수 변화, 학습 시간, Coverage

=== Go/No-Go ===
Go: 5개 지표(PSNR/SSIM/LPIPS/F1/Chamfer) 모두 레퍼런스 대비 합리적 범위
No-Go: gsplat API 사용, densification 설정, depth/normal 렌더링 구현 재검토

=== 시각적 산출물 ===
1. RGB/Depth/Normal 렌더링 (4뷰)
2. 프리미티브 PLY
3. Coverage 히트맵
4. CityGSV2 수치 vs 본 실험 비교 표

results/phase1_vanilla/REPORT.md 작성.
```

### Step 1-2: + Depth/Normal 감독

**목적:** MVS depth/normal 감독이 기하 품질을 개선하는지 확인.

**레퍼런스:** CityGaussianV2 Table 2 ablation, MatrixCity with depth supervision PSNR 약 22.22.

**Go 기준:**
- PSNR, SSIM, LPIPS가 레퍼런스 with-depth 수치 대비 -0.7 이내
- F1, Chamfer가 Step 1-1 대비 개선
- Depth MAE, Normal cos가 Step 1-1 대비 유의미 개선

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-2를 진행해줘.

목표: L_depth + L_normal 추가, 기하 품질 개선 확인.

=== 학습 ===
L = L_photo + λ_nc·L_nc + L_depth + L_normal
- L_depth = L1(D_render, D_GT_MVS)
- L_normal = 1 - cos(n_render, n_GT_MVS)
- GT: MatrixCity 제공 GT depth/normal (HuggingFace)

=== 평가 ===
렌더링: PSNR, SSIM, LPIPS → CityGSV2 Table 2 (with depth) 비교
기하: F1, Chamfer → CityGSV2 with-depth 비교
추가: Depth MAE, Normal cos → Step 1-1 대비 개선

=== 시각적 산출물 ===
1. Step 1-1 vs 1-2 렌더링 비교 (4뷰)
2. Depth 오차 히트맵
3. CityGSV2 ablation 수치 vs 본 실험 표

results/phase1_depth_normal/REPORT.md 작성.
```

### Step 1-3: + Semantic Head + L_sem

**목적:** Semantic head 추가가 기하 품질을 해치지 않으면서 의미론을 학습하는지 확인.

**레퍼런스:** 직접 비교 가능 연구 적음. AlignGS, NeRBuilder 등 semantic 3DGS의 mIoU 수준 참고.

**Go 기준:**
- PSNR/SSIM/LPIPS가 Step 1-2 대비 -0.3 이내 유지 (레퍼런스 with-depth 수준 유지)
- F1, Chamfer가 Step 1-2 대비 유지
- mIoU ≥ 0.75
- Gradient 격리: L_sem이 f_i에만 gradient

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-3을 진행해줘.

=== Semantic Head ===
- 각 Gaussian에 f_i ∈ R^4 추가
- gsplat N-D feature 렌더링 (colors shape=[N,D]) 활용 → semantic map
- softmax 적용

=== GT Segmentation ===
MatrixCity에 semantic GT가 있으면 사용.
없으면 Grounded SAM 2로 생성 (roof/wall/terrain/BG, K=4).

=== 학습 ===
L = Step 1-2 + λ_s·L_sem (CrossEntropy, ignore_index=0)

=== 평가 ===
렌더링/기하: Step 1-2 대비 유지 확인 (레퍼런스 with-depth 수준 유지)
의미론: mIoU, per-class IoU
Gradient 격리 검증: L_sem만 f_i에 gradient, 기하 파라미터에 0

=== 시각적 산출물 ===
1. Semantic map 렌더링 (class별 색상, 4뷰)
2. 프리미티브 PLY (class 색상)
3. Gradient 격리 로그

results/phase1_semantic/REPORT.md 작성.
```

### Step 1-4: + L_mutual (메커니즘 1 단독)

**목적:** Intra-primitive 도메인 규칙이 법선과 의미론을 양방향 교정하는지 확인.

**레퍼런스:** PlanarSplatting 예비 실험 (legacy/) — wall normal 8.9° → 3.8°. 2DGS로 재검증.

**Go 기준:**
- PSNR/SSIM/LPIPS/F1/Chamfer가 Step 1-3 대비 유지
- Wall 법선 수직도(|n·e_g| < sin(10°) 비율)가 Step 1-3 대비 유의미 증가
- mIoU가 Step 1-3 대비 유지 또는 개선
- Gradient 양방향성 검증

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-4를 진행해줘.

=== Gravity 추정 ===
Grounded SAM terrain 영역의 MVS 법선 평균 = UP → e_g = -UP (학습 전 1회 계산).
MatrixCity는 합성이므로 GT gravity도 알고 있음 → 추정값 검증 가능.

=== L_mutual 구현 ===
legacy/ 참고. n_i = normalize(t_u × t_v) (2DGS tangent).
L_mutual = Σ_i [p_wall·(n·e_g)² + p_roof·relu(τ-(n·e_g)²)² + p_terrain·(1-|n·e_g|)² + L_height]

=== 학습 ===
L = Step 1-3 + λ_m·L_mutual (warmup 10000 iter부터)

=== 평가 ===
렌더링/기하: Step 1-3 대비 유지
Wall 법선 수직도 히스토그램, 증가 비율
mIoU 유지/개선
Gradient 양방향성: (1) p_wall 증가 → n_i 수평 방향 gradient, (2) n_i 수평 → p_wall 증가 방향 gradient

=== 조건부 실험 ===
Mutual < Baseline(Step 1-3)이면 Joint-GTOnly, Joint-Weak 추가.

=== 시각적 산출물 ===
1. Wall 법선 히스토그램 (Step 1-3 vs 1-4)
2. p_wall 분포 변화
3. Gradient 양방향성 로그
4. PlanarSplatting 예비 결과 vs 2DGS 본 실험 비교 표

results/phase1_mutual/REPORT.md 작성.
```

### Step 1-5: + L_structure (메커니즘 2 단독) — ablation용

**목적:** Inter-primitive 구조 정렬 단독 효과 확인 (Structure only 조건).

**Go 기준:**
- 렌더링/기하 지표가 Step 1-3 대비 유지
- σ_normal_intra(그룹 내 법선 분산)가 의미있게 감소
- σ_coplanar(그룹 내 coplanarity 오차) 감소

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-5를 진행해줘.

=== 그룹핑 구현 ===
src/stage2/grouping.py:
- 조건: 동일 class(argmax(f_i)) + 법선 cos>0.95 + 공간 근접
- 대표 평면: 가중 평균 (s_i 기반)
- 매 T=500 iter 재계산
- Density control 연동

=== L_structure 구현 ===
- L_normal_align = Σ_k Σ_{i∈G_k} (1-n_i·n_k)² — n_i gradient, n_k detach
- L_coplanar = Σ_k Σ_{i∈G_k} (n_k·c_i+d_k)² — c_i gradient, n_k/d_k detach
- L_structure = λ_na·L_normal_align + λ_cp·L_coplanar
- L_coverage: 후보

=== 학습 (Structure only, 메커니즘 2 단독) ===
L = Step 1-3 + λ_str·L_structure (warmup 15000부터)
이것은 ablation의 "Structure only" 조건.

=== 평가 ===
렌더링/기하: Step 1-3 대비 유지
σ_normal_intra, σ_coplanar: Step 1-3 대비 감소
그룹핑 통계: 그룹 수, 평균 크기

=== Gradient 검증 ===
∂L_na/∂n_i ≠ 0, ∂L_cp/∂c_i ≠ 0, ∂L_str/∂f_i = 0

=== 시각적 산출물 ===
1. 그룹핑 PLY (그룹별 색상)
2. σ_normal_intra 히스토그램
3. 그룹 통계 표

results/phase1_structure/REPORT.md 작성.
```

### Step 1-6: Both (메커니즘 1 + 2 결합)

**목적:** 두 메커니즘 결합 시 각각의 개선이 유지되고 상호작용이 있는지 확인.

**Go 기준:**
- Wall 수직도: Mutual only 조건과 비슷하거나 개선
- σ_normal_intra: Structure only 조건과 비슷하거나 개선
- 렌더링/기하 지표 유지

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-6을 진행해줘.

=== 학습 (Both) ===
L = Step 1-3 + λ_m·L_mutual + λ_str·L_structure
- L_mutual warmup: 10000부터
- L_structure warmup: 20000부터 (L_mutual보다 늦게, f_i/n_i 수렴 후 그룹 정의)

=== 평가 ===
렌더링/기하: Step 1-3 대비 유지
Wall 수직도 (L_mutual 효과), σ_normal_intra (L_structure 효과) 모두 개선 확인

=== Ablation 정리 (Phase 1 종합) ===
4조건 비교표 작성:
- Baseline (Step 1-3: L_photo + L_depth + L_normal + L_nc + L_sem)
- Mutual only (Step 1-4)
- Structure only (Step 1-5)
- Both (Step 1-6)

각 지표(PSNR, SSIM, LPIPS, F1, Chamfer, mIoU, Wall 수직도, σ_normal_intra)의 4조건 비교.

상호작용 분석:
- Both > Mutual + Structure: 시너지 — 동시 작용에 의한 순환 효과 확인
- Both ≈ Mutual + Structure: 독립 기여
- Both < Mutual + Structure: 간섭 → warmup 순서 바꿔 재실험

핵심 해석 프레임:
- Structure only vs Both: Structure only에서는 메커니즘 1이 없으므로 기하 정렬이 의미론에 피드백되지 않음(순차에 가까운 조건). Both에서 better면 "메커니즘 1의 양방향 gradient가 메커니즘 2의 그룹핑 품질을 개선"하는 순환 입증.
- Mutual only vs Both: per-primitive만으로는 면 단위 일관성 부재. Both에서 better면 구조 정렬의 추가 가치 입증.

=== 시각적 산출물 ===
1. 4조건 비교 표 (모든 지표)
2. 4조건 렌더링 비교 (동일 뷰)
3. 4조건 프리미티브 PLY
4. 기여도 분해 그래프

results/phase1_ablation/REPORT.md 작성.
```

---

## Phase 2: Stage 3 검증 (3D BAG 합성 렌더링)

### Step 2-1: 3D BAG 합성 렌더링 파이프라인 (UAV/Pix4D-standard)

**Reference mission: DJI Phantom 4 RTK + Pix4D 기본 설정 UAV mapping**

**설계 근거**:
- **플랫폼**: UAV (§RESEARCH_CONTEXT.md §8.1 성수동 = DJI 70m, §10 레퍼런스 = AGS/ULSR-GS/CityGSV2)
- **Scene**: 3D BAG Amsterdam Jordaan 에서 실제 200×200m 블록 (자연 분포 ~100 건물). 인위적 grid 배치 아님.
- **해상도**: 원본 5472×3648 (DJI P4 RTK) → 학습용 **2048×1536** downsample (2.67×)
- **FOV**: 74° horizontal (DJI spec)
- **Altitude**: **80m AGL** (Pix4D 기본 권장)
- **Overlap**: 80% forward / 70% side (Pix4D default)
- **Oblique**: 45° tilt × 4 cardinal directions (N/E/S/W) — Pix4D 표준
- **Orbit 제외**: LOD2 mapping 표준 아님
- **GSD**: 원본 1 cm / 학습용 2.7 cm (LOD2 상단 정밀)
- **Train/test split**: interleave `i % 10 == 9` (biased split 방지)
- **Procedural texture**: material 별 Perlin noise (3D, `TexCoord.Generated` 기반, view-consistent). flat-color scene 의 RGB ≈ semantic trivial 대응을 깨뜨려 L_mutual 의 의미론↔기하 양방향 gradient 가 정상 측정되게 함. Brightness range material 별 0.35-1.00 × base.

**Scene 선정 절차**:
1. 3D BAG Amsterdam Jordaan 4 타일 (2888 건물) 전체 building centroid 의 world XZ 위치 스캔
2. 200×200m sliding window 로 80-150 건물 포함 영역 후보 추출
3. Roof type 다양성 기준으로 가장 균형 잡힌 블록 선정 (flat/gable/hip/tri-slope/complex 최소 각 5 개)
4. 해당 building 들을 **world position 유지** 로 scene.obj 작성 (per-building centering 아님)
5. ground plane 추가, Roof/Wall/Ground/Terrain material tag 보존

**프롬프트**:
```
docs/EXPERIMENT_PLAN.md의 Step 2-1을 진행해줘.

목표: UAV Pix4D-standard mission 으로 3D BAG Jordaan 실제 블록 렌더링.

=== 작업 ===
1. select_block.py: 3D BAG Jordaan 에서 200×200m 자연 블록 선정 (80-150 건물, roof type 균형)
2. compose_scene.py: 선정 건물들을 world position 유지하여 scene.obj 생성
3. render_scene.py: 80m altitude, 2048×1536, 74° FOV, 80/70% overlap, 4 cardinal oblique (no orbit)
4. postprocess_exr.py: depth/normal frame 변환 (기존 유지)
5. export_colmap.py: COLMAP sparse 생성 (기존 유지)

=== 검증 ===
- FC-2 (500 iter benchmark): 실제 it/s 측정, 30k 총 시간 정확 추정
- FC-3 (5k iter smoke): eval PSNR >= 20 시 full training 진행

results/phase2_synthesis/REPORT.md 작성.
```

**v1/v2 실패 교훈 (본 Step 재시도에서 수정):**
1. **Frame bug**: render_scene.py 의 `camera_pose_dict` 이 Blender world 에 저장 → OBJ world 로 일관 (수정 완료)
2. **View 부족**: 73 views → Pix4D 표준 overlap 에 기반한 ~360 views
3. **Biased split**: last 10% (orbit 몰림) → `i % 10 == 9` interleave (수정 예정)
4. **인위적 grid scene**: spacing 18m 로 건물 띄워놓음 → 실제 Jordaan 블록 자연 배치

### Step 2-2: Phase 1 4조건 Ablation → Stage 3 CityGML (UAV Pix4D 데이터에서)

**전제**: Step 2-1 (UAV Pix4D-standard) 데이터셋 사용. Step 2-1 의 FC-2/FC-3 검증으로 수렴 확인 후 진행.

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-2를 진행해줘.

목표: Phase 1의 4조건(Baseline/Mutual/Structure/Both)을 Step 2-1 UAV Pix4D 데이터에서 학습 → Stage 3 → CityGML → val3dity.

=== 4조건 학습 ===
각 조건: 3D BAG 합성 렌더링 입력 + 해당 손실 함수 조합 + 30000 iter

=== Stage 3 실행 ===
6단계 (클러스터링 → 평면 교차 → 건물 분리 → GroundSurface → CityGML).
각 조건의 출력을 val3dity 검증.

=== 평가 ===
- val3dity 통과율 (4조건 비교)
- val3dity 오류 유형 분포
- 면 단위 IoU (생성 vs GT CityGML)
- Hausdorff distance
- 의미론 accuracy (면 class vs GT)

=== Synthetic A와의 연결 ===
각 조건의 σ_normal을 Synthetic A 법선 노이즈 그래프에 매핑.
예측 val3dity vs 실제 val3dity 비교.

=== 기여도 분해 ===
- 기여 1 (메커니즘 1+2 결합): Both vs Baseline의 val3dity 차이
- 기여 1a (메커니즘 1 intra): Mutual only vs Baseline
- 기여 1b (메커니즘 2 inter): Structure only vs Baseline
- 순환 효과: Structure only vs Both — 메커니즘 1의 양방향 gradient가 CityGML 품질에 미치는 영향
- 구조 정렬 추가 가치: Mutual only vs Both — 면 단위 정렬이 CityGML 품질에 미치는 영향

=== 시각적 산출물 ===
1. 4조건 CityGML 3D 비교
2. 4조건 val3dity 막대그래프
3. 오류 유형 분포 heatmap
4. Synthetic A 그래프에 4조건 위치 표시
5. 대표 건물의 4조건 비교

results/phase2_ablation_citygml/REPORT.md 작성.
```

### Step 2-3: Synthetic B 확장 (노이즈/카메라 변수)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-3을 진행해줘.

목표: 최선 조건(Phase 2-2의 결과)에서 입력 노이즈/카메라 배치 민감도 파악.

=== 변수 ===
기본: 이상적 카메라 + clean 감독 신호
노이즈 (이상적 카메라): depth σ=2.0m, segmentation 15% 오분류
카메라 (clean 감독 신호): 이상적 / oblique only / nadir only / 뷰 50% / 뷰 25%

각 조건: Stage 2 (Both) 학습 + Stage 3 → GT 비교.

=== 평가 ===
val3dity, 면 IoU, Hausdorff, 의미론 accuracy.
Stage 2가 노이즈를 얼마나 흡수하는가 (Synthetic A의 Stage 3 단독 대비).

=== 시각적 산출물 ===
1. 조건별 CityGML 비교
2. val3dity 그래프 (노이즈 축, 카메라 축)
3. 실데이터 촬영 계획 가이드라인

results/phase2_synthetic_b/REPORT.md 작성.
```

---

## Phase 3: 비교 + Real UAV + 실데이터

### Step 3-1: GauU-Scene (Real UAV 검증)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-1을 진행해줘.

목표: MatrixCity에서 검증된 파이프라인이 real UAV에서도 작동하는지 확인.

=== 데이터 ===
GauU-Scene (접근 신청 필요, 병렬로 진행).
ULSR-GS, CityGaussianV2가 사용.

=== 학습 + 평가 ===
Phase 1 4조건 모두 실행 (시간 허용 시, 또는 Both만).
PSNR, SSIM, LPIPS, F1, Chamfer → ULSR-GS, CityGSV2 레퍼런스와 비교.

=== Go 기준 ===
레퍼런스(ULSR-GS GauU-Scene F1, CityGSV2 GauU-Scene PSNR) 대비 합리적 범위.

results/phase3_gauu/REPORT.md 작성.
```

### Step 3-2: 순차 파이프라인 비교 (City3D)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-2를 진행해줘.

목표: 순차 vs 공동최적화 비교.

=== 4조건 ===
(a) City3D + 풋프린트 (best practice)
(b) City3D - 풋프린트 (벽면 사후 가정)
(c) 제안 방법 (Phase 2 Both)
(d) 3D BAG LiDAR 기반 결과 (upper bound)

모두 3D BAG 합성 또는 GauU-Scene에서 실행. val3dity 검증.

=== 핵심 비교 ===
(b) vs (c): 방법론 순수 비교 (둘 다 footprint 없음)
(a) vs (c): best practice 대비
(c) vs (d): upper bound 접근도

=== 시각적 산출물 ===
1. 4조건 CityGML 비교
2. val3dity 막대그래프
3. 면 IoU/Hausdorff 비교
4. 처리 시간 비교

results/phase3_comparison/REPORT.md 작성.
```

### Step 3-3: 성수동 실데이터 시연

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-3을 진행해줘.

목표: 실환경 정성 시연 (논문 figure용).

=== 데이터 준비 ===
Metashape depth (coverage 61.6%) 사용.
Grounded SAM GT + gravity 추정.

=== 학습 + Stage 3 ===
Phase 2의 Both 설정으로 학습 → CityGML → val3dity.

=== 평가 ===
val3dity 통과율, 건물별 품질.
GT CityGML이 없으므로 정량 비교는 제한적. 정성 평가 중심.

=== 시각적 산출물 ===
1. 입력 이미지 → 프리미티브 → CityGML 3단계 시각화
2. 건물별 CityGML (대표 6-8개)
3. 도시 전체 overview
4. Phase 2 합성과의 비교 (같은 방법이 실데이터에서도 작동)

results/phase3_seongsu/REPORT.md 작성.
```

### Step 3-4: 종합 + 논문 산출물

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-4를 진행해줘.

목표: 전체 결과 종합 + 논문용 최종 표/그래프.

=== 기여별 증거 정리 ===
- 기여 1 (공동 최적화): Phase 1 4조건 ablation + Phase 2 CityGML ablation
- 기여 2 (지배 요인 + 순차 대비): Synthetic A + Phase 3-2 비교
- 기여 3 (외부 데이터 불필요): Phase 3-2 (b) vs (c)

=== 논문용 최종 산출물 ===
1. 최종 정량 비교 표 (Phase 1 + Phase 2 + Phase 3)
2. Phase 1 ablation 막대그래프 (MatrixCity 수준 검증)
3. Phase 2 CityGML ablation 그래프
4. Synthetic A 노이즈-품질 그래프 (Phase 2 실측 표시)
5. 파이프라인 비교 다이어그램
6. 대표 CityGML 결과 (합성 + 성수동)
7. 실패 사례 분석

results/final/REPORT.md 작성.
```

---

## REPORT.md 템플릿

```markdown
# [Phase/Step] 결과 보고

## 수행 일시

## 수행 작업 요약

## 정량 지표
### 레퍼런스 비교 (해당 시)
| 지표 | 본 실험 | 레퍼런스 | 차이 | 레퍼런스 출처 |

### Step 간 비교
| 지표 | 이전 | 현재 | 변화 |

## 시각적 산출물 체크리스트

## Go/No-Go 판단
- [ ] Go / [ ] Retry / [ ] Switch

## 이슈 및 해결

## 다음 단계
```
