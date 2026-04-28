# 도시 규모 건물 3D 복원 — Claude Web 브리핑 v4

> 새 세션에서 처음부터 맥락 잡고 G2 알고리즘 설계 + Stage 3 개선 작업 이어가기 위한 자료. v3 이후의 cycle 검증 결과 + G2 결정 + Stage 3 전체 개선 로드맵 반영.

## 0. v3 → v4 한 줄 변화

v3: "Track 1 (Stage 2 → Stage 3 인터페이스 정렬)" 이 핵심 권고였음.
v4: **그 implementation 시도 (Stage 2 group 그대로 사용) 가 *patch vs surface unit mismatch* 로 실패** 발견 + cycle 검증 (Track A/B/C) 으로 *현 G1 grouping 이 thesis 의도 미충족* 확정 → **G2 (surface-level grouping) 로 재학습 + Stage 3 전반 재설계** 결정.

---

## 1. 연구 배경 (압축)

박사 연구: **도시 규모 건물의 구조적 3D 복원 — 기하-의미론 공동 최적화**

- Base: 미분 가능 렌더링 (gsplat + 2DGS)
- 두 메커니즘 (RESEARCH_CONTEXT 표기):
  - **L_mutual** (메커니즘 1, intra-primitive): wall=수직, terrain=수평 도메인 규칙. p_c × 기하오차 → n_i, f_i 양방향 gradient
  - **L_structure** (메커니즘 2, inter-primitive): "**평면 인스턴스 그룹** G_k" 안의 normal/center 정렬. 매 T iter 재할당.
- Pipeline: Stage 1 (SfM/MVS+seg+gravity) → Stage 2 (joint opt) → **Stage 3 (CityGML 변환)**
- thesis main novelty: **"두 메커니즘 동시작용 + 주기적 재할당의 *순환* = 순차 파이프라인과의 근본적 차이"**

검증 단계:
- Phase 1 (MatrixCity): primitive 수준 검증, **6/6 통과** (완료)
- Phase 2 (3D BAG 합성): CityGML 평가, **재설계 진입** (현재)
- Phase 3 (real UAV + 성수동): 미착수

---

## 2. 현재 측정 데이터 (Phase 2, 신뢰 가능 부분만)

### Stage 2 — primitive 수준 (G1 grouping 으로 학습)

| 지표 | 정의 / 방향 | Baseline | Mutual | Structure | Both | Phase 1 비교 |
|---|---|---|---|---|---|---|
| Wall vert-frac | wall 중 \|n·g\|<0.15, ↑ | 28% | **79%** | 28% | **79%** | Phase 1 17→88% 와 같은 방향 |
| σ_normal_intra (deg) | 그룹 내, ↓ | 14.7 | 12.6 | **14.9** | 13.0 | **Phase 1 −45% vs Phase 2 +1%** |
| σ_coplanar (m) | 그룹 내, ↓ | 1.91 | 1.84 | **1.86** | 2.01 | Phase 1 −16% vs Phase 2 −2~−9% |

### Stage 3 — CityGML 출력 (post-fix, *상대 ranking 만 신뢰*)

| Cond | val3dity | face IoU | Sem acc | σ_normal 3D |
|---|---|---|---|---|
| Baseline | 52.7% | 0.214 | 21.6% | 9.09° |
| Mutual | 48.9% ↓ | **0.240** | 20.6% | **8.73**° |
| Structure | **55.0%** | 0.221 | **22.0%** | 9.18° |
| Both | 54.2% | 0.227 | 20.4% | 9.00° |

조건 ranking (val3dity): **Structure > Both > Baseline > Mutual**. 단 *상대 비교만 valid*, 절대 수치는 §3 의 측정 인프라 caveat 적용.

---

## 3. 발견된 모순 + 측정 인프라 문제

### C1: Mutual 의 Stage 3 회귀 (-3.8%p)

bbox 버그 정정 후 magnitude 절반 축소 (-8.4 → -3.8%p). 잔존 회귀의 메커니즘은 D' 가설 (단순 건물 과조정) 가 가장 그럴듯, **미확정**.

### C2: Stage 2 ↔ Stage 3 인터페이스 단절

```
Stage 2 (src/stage2/grouping.py): voxel hash 5cm + 12 dir bin (G1, patch 단위)
Stage 3 (src/stage3/clustering.py): hierarchical clustering cos>0.92 (별도 algorithm)
→ Stage 2 group 정보 통째로 버려짐
```

**v4 정정**: 이 mismatch 는 *버그* 가 아니라 **unit mismatch** — Stage 2 group (patch) 와 Stage 3 surface 가 다른 단위. 단순 인터페이스 정렬 (Track 1, Stage 2 group 직접 전달) 은 *patch 154 개를 surface 로 오인* 해서 실패함.

### C3: L_normal_align 의 Phase 2 약효 (확정)

3 components 로 분해:
- **C3a (photo redundancy, 측정 입증)**: PSNR 40+ photo loss 가 normal 정렬 → L_normal_align 활성화 시점 (step 20k) 에 이미 변수 분산 매우 작음. L_structure_na max = 0.000222 (L_mutual_vert max 0.0326 의 **1/135**).
- **C3b (patch unit, 사용자 통찰)**: G1 의 5cm patch 가 *원래* 동질적 → L_normal_align 이 "intra-patch smoothing" 에 그침. across-patch / surface 단위 정합 (예: corner tilt) 못 잡음.
- **C3c (cycle 작동 부재)**: §4 참조.

### Bug 1 (정정 완료): bbox_margin

`src/stage3/plane_intersection.py` 의 bbox_margin 1줄 자동화 → v3 측정값 (Baseline 40.5%) → v4 (52.7%) +12%p. C1 magnitude 절반이 이 버그였음.

### Bug 2 (정정 미완): GT_convex systematic 축소

`gt_stage3_test.py` 의 GT mesh → polytope 변환 결과가 GT 의 **약 절반 높이** (88% 건물에서). v4 의 "Stage 3 천장 96.2%" 는 잘못된 reference. **진짜 천장 미정.** 다음 작업에서 정정 필요.

---

## 4. Cycle 검증 결과 (Track A/B/C, 2026-04-27)

스케치한 cycle:
```
[고리 1] L_structure → n_i 정렬
[고리 2] L_mutual 이 정렬된 n_i 보고 f_i 교정
[고리 3] 교정된 f_i → 다음 T iter 그룹 재할당
[고리 4] 새 group → L_structure 에 반영
```

| 고리 | 검증 방법 | 결과 |
|---|---|---|
| 1 | Loss magnitude 측정 | L_structure : L_mutual = **1 : 135** → 약함 |
| 2 | L_mutual 수식 분석 | (n·g)² 작아질수록 ∂L_mut/∂f_i 작아짐 → **인과 방향 정반대** (정렬되면 비활성화) |
| 3 | f_i argmax change (intermediate ckpt) | step 25k→30k Structure 0.45%, Both 0.29% → **trigger 없음** |
| 4 | Group churning (tensorboard) | n_groups CV **2.01%**, consecutive change 1.17/16,773 → **거의 정적** |

**결론**: G1 구현 위에서 thesis 의 *동시작용 cycle* 이 4 고리 모두 약함. cycle claim 미입증.

---

## 5. G2 결정 — 왜 surface-level grouping 인가

### 연구 의도와의 정합성 4 가지 근거

1. **thesis novelty**: "순차 파이프라인과의 차이" 가 surface 단위에서만 성립. Patch 단위는 일반 normal smoothing regularization 과 차별화 안 됨.
2. **용어 일관성**: "**평면 인스턴스 그룹**", "**대표 평면**", "**inter**-primitive" 모두 surface 명시. Patch 였다면 "neighborhood smoothing" 등 다른 용어 썼을 것.
3. **Cycle 의미**: G2 에서만 f_i 변경 → 다른 surface 그룹으로 *진짜 재할당*. G1 에선 voxel 위치로 그룹 결정되어 cycle 의미 없음.
4. **Stage 2-3 인터페이스**: G2 = Stage 3 surface 와 같은 단위 → 자연스러운 통합. G1 에선 어차피 Stage 3 에서 별도 surface clustering 필요.

### 현 G1 구현은 implementation choice

추측: 학습 안정성 + 계산 효율 + 단순함 trade-off. 단 thesis 표현 (RESEARCH_CONTEXT) 은 G2 의도 그대로.

### G2 알고리즘 후보 (새 세션 첫 작업)

| 후보 | 알고리즘 | 장점 | 단점 |
|---|---|---|---|
| **A. Voxel + spatial** | (class, large voxel ~1m, dir bin) + post-merge by (n, plane_d) | voxel hash 효율 유지 | 같은 wall 의 cell split 문제 |
| **B. Region growing** | (class, n similarity, plane_d similarity, spatial connectivity) | surface 단위 직접 표현 | 효율 (매 T iter 호출) |
| **C. Hybrid** | (class, dir bin) + plane_d clustering 후 connected component | 두 단계 — 단순 + 정확 | 구현 복잡도 |

**검토 시 고려할 trade-off**:
- 학습 매 T=500 iter 호출 → 988K primitive 에 대해 1 분 미만이어야 함
- 학습 초기 noisy primitive 에서 잘못된 grouping 위험 → warmup 강화 필요할 수 있음
- 같은 surface 의 멀리 있는 두 부분 (예: 창문 사이 panel) 을 합칠지 분리할지 결정

---

## 6. Stage 3 개선 — 전체 그림

G2 결정 + 측정 인프라 정정 + 알고리즘 선택을 통합해서 Stage 3 전체를 재설계.

### 6.1 측정 인프라 정정

| # | 문제 | 상태 | 해야 할 것 |
|---|---|---|---|
| 1 | bbox_margin 자동화 | ✓ 정정 | (없음) |
| 2 | GT_convex height 절반 축소 | ✗ 미완 | gt_stage3_test 의 grouping cos_thresh 검토, 또는 GT direct 93.9% lower bound 채택 |
| 3 | eval metric 가혹성 (face count mismatch → sem 21%, IoU 0.16) | △ 진단됨 | Multi-to-one matching 또는 area-weighted metric 도입, 또는 metric 재정의 |
| 4 | Stage 3 천장 미정 | ✗ | (2 와 같이) cos_thresh sweep 또는 GT direct 활용 |

### 6.2 Stage 3 알고리즘 선택

직접 검증으로 알게 된 것: building 1 PRED Stage 3 출력이 **GT 와 비슷한 크기 (16.41m vs 16.61m)** → convex polytope 알고리즘 자체는 문제 아님.

**유지**: convex polytope (`src/stage3/plane_intersection.py`)
- GT direct 93.9% 로 알고리즘 capability 충분
- 우리 best 55% / 93.9% = 격차 39%p — 이게 *Stage 2 quality + 인터페이스 정합* 의 몫
- PolyFit 등 알고리즘 교체는 우선순위 ↓ (격차 줄인 후 재검토)

### 6.3 Stage 2 → Stage 3 인터페이스 (G2 위에서)

```
Stage 2 (G2 grouping):
  매 T iter G2 호출 → group_id (surface 단위)
  L_structure 가 group 별 rep_n, rep_d 향해 primitive 정렬
  학습 끝에 ckpt 에 G2 group_id 저장

Stage 3 (G2 사용):
  ckpt 의 G2 group_id 그대로 받음
  Stage 3 자체 clustering 제거 또는 thin wrapper
  group → 대표 평면 → 평면 교차 → polygon → CityJSON
```

**Baseline / Mutual 처리** (이들은 grouping 학습 안 함):
- Stage 2 ckpt 에 G2 group 정보 없음
- Stage 3 입구에서 *post-hoc* G2 grouping 호출 (학습 정렬 없이 grouping 만)
- 4 조건이 모두 같은 grouping 으로 평가 — fair comparison

### 6.4 4 조건 ablation 의 통합 의미

| Cond | Stage 2 학습 grouping | Stage 3 입력 grouping | 측정하는 것 |
|---|---|---|---|
| Baseline | 없음 | post-hoc G2 | grouping 만의 효과 (control) |
| Mutual | 없음 | post-hoc G2 | + L_mutual 효과 |
| Structure | G2 (학습 중) | trained + ckpt 의 G2 | + L_structure 의 *학습 시 효과* |
| Both | G2 (학습 중) | trained + ckpt 의 G2 | + 두 메커니즘 효과 (시너지 포함) |

→ **차이가 학습 중 grouping 의 작동 여부에서만 발생** = 메커니즘 1, 2 의 ablation 의 진짜 의미.

### 6.5 Cycle 재검증 (G2 위에서)

G2 위에서 §4 의 Track A/B/C 재실행:
- Loss magnitude 비교 (gradient norm)
- Group churning (G2 에선 변동 더 클 것 — surface 합쳐지고 갈라짐)
- f_i 동역학

**핵심 측정**: Both > Structure (시너지) 가 발생하는가?

---

## 7. 옵션 A 로드맵 (1-2 주)

### Step 1 (1-2 일): G2 algorithm 설계 + 구현

- 후보 A/B/C 비교, 선택
- `src/stage2/grouping.py` 의 새 함수 또는 기존 함수 옵션화
- Sanity test: 학습 시 1 iter 만에 surface-like 그룹 생성 확인

### Step 2 (1 일): G2 grouping post-hoc test

- 학습 *전에* baseline ckpt 위에 G2 호출 → group 수 / surface 단위 매치 확인
- Stage 3 에 통과시켜 building 1 등 확인 (height 16m, surface 6-9 개)
- 만약 OK 면 다음 단계, 아니면 G2 알고리즘 재조정

### Step 3 (1-2 일): Phase 2 재학습

- Structure with G2 (5-7h)
- Both with G2 (5-7h)
- (Baseline/Mutual 은 재학습 불필요 — G2 영향 없음)

### Step 4 (반일): 4 조건 Stage 3 통합 재실행

- Baseline/Mutual: post-hoc G2
- Structure/Both: trained ckpt 의 G2
- val3dity, face IoU, sem acc, σ_normal_intra 측정

### Step 5 (반일): Cycle 재검증

- Track A/B/C 재실행
- Both > Structure 시너지 발생 여부

### Step 6 (반일): GT 천장 재측정

- gt_stage3_test 의 GT_convex 축소 디버그 + 정정
- 또는 GT direct 93.9% 채택

### Step 7 (반일): 문서 v6 작성

- REPORT v6 (Phase 2 with G2)
- REPORT_FOR_ADVISOR v2
- 옵션 A 결과에 따른 thesis claim 정리

### 분기 (Step 5 결과 후)

| Phase 2 G2 결과 | 후속 |
|---|---|
| 시너지 입증 (Both > Structure 명확) | thesis main claim 강력 입증, Phase 3 진입 |
| Structure ≥ Both 여전 | "메커니즘 2 작동, 시너지는 환경 의존" claim, Phase 3 가 결정적 |
| L_structure 효과 여전 약함 | photo redundancy 가 진짜 dominant — supervision 강도 conditional thesis, Phase 3 (PSNR 25-30) 가 thesis 의 main 입증 |

---

## 8. 새 세션 시작 시 첫 작업

### 컨텍스트 자료 (모두 존재)

```
docs/
├── REPORT_FOR_ADVISOR.md        # 박사 thesis 전체 맥락
├── CLAUDE_WEB_BRIEF_v4.md       # 본 문서 (기술 논의)
├── RESEARCH_CONTEXT.md          # §15 (Track 1) + §16 (C3 진단)
└── CODEX_PROMPT_FIG_MECH1.md    # (참고)

results/phase2_ablation_citygml/
├── REPORT.md                    # v4 측정 데이터
├── _gt_*/                       # GT ceiling 측정 결과
├── _diag/                       # D1-D4 진단 + cycle gradient (예정)
└── {baseline,mutual,structure,both}/
    ├── ckpt/                    # 학습된 모델 (G1)
    ├── tb/                      # tensorboard 로그
    ├── eval_fixed/              # post-bbox-fix eval
    └── stage3_fixed/            # post-bbox-fix Stage 3
```

### 첫 작업 prompt 예시

> "RESEARCH_CONTEXT.md, CLAUDE_WEB_BRIEF_v4.md 읽고 G2 (surface-level grouping) 알고리즘 설계 시작. 후보 A (voxel+spatial) / B (region growing) / C (hybrid) 비교, 학습 매 T iter 호출 효율 + 학습 안정성 + 정확도 trade-off 분석 후 추천 + 구현 계획."

### 우선순위 순서

1. G2 알고리즘 설계 결정
2. `src/stage2/grouping.py` 에 새 함수 구현
3. Sanity test (1 ckpt 위에 적용 → surface 단위 group 생성 확인)
4. 위 OK 면 Phase 2 재학습 진입

---

## 9. 논의/결정이 필요한 핵심 질문

1. **G2 알고리즘 후보 (A/B/C) 중 어느 것?** — 효율 vs 정확도 vs 안정성
2. **G2 의 hyperparameter**: voxel size (1m? 5m?), normal cos thresh, plane_d tolerance, spatial connectivity radius
3. **Baseline/Mutual 의 Stage 3 입력**: post-hoc G2 vs legacy clustering — 둘 중 어느 것이 *fair comparison*?
4. **GT 천장 재측정 방식**: cos_thresh sweep vs GT direct 채택 vs 별도 ground truth polytope 정의
5. **Eval metric 재정의**: face IoU 의 face count mismatch 문제 — multi-to-one matching 도입할지?
6. **시너지 부재 시 thesis 재정의** 의 정도: "Phase 2 환경 (강한 supervision) 한계" vs "메커니즘 2 자체 약화"

---

## 10. v3 → v4 변화 요약표

| 항목 | v3 | v4 |
|---|---|---|
| Track 1 (인터페이스 정렬) 평가 | 첫 우선순위 | **Patch unit mismatch 로 단순 적용 실패 — G2 재학습 필요** |
| Cycle claim | 미입증, 진단 필요 | **4 고리 모두 약함 입증 (Track A/B/C 측정)** |
| C3 framing | photo redundancy 가설 | C3a (photo redundancy) + C3b (patch unit) + C3c (cycle dead) — 3 components |
| Grouping 정의 | 검토 안 함 | **G2 (surface-level) 결정** + 알고리즘 후보 3 개 |
| Stage 3 개선 범위 | 인터페이스 정렬만 | **인프라 정정 + 알고리즘 검증 + 인터페이스 + metric — 통합 재설계** |
| Phase 2 결과 신뢰도 | 상대 ranking | (변경 없음) 상대 ranking 만 |
| 다음 단계 | Step 1 (인터페이스 정렬) | **옵션 A (G2 + 재학습 + 통합 재설계)** |
| 박사 thesis 함의 | 약화 가능성 | G2 결과에 따라 강화/약화 결정 |

---

## 11. 코드 위치 reference

```
src/stage2/
├── grouping.py:35-119           # group_primitives() (G1, voxel hash 5cm) ← G2 후보 추가 위치
├── loss/structure.py:20-58      # l_structure (na + cp)
├── loss/mutual.py:34-110        # l_mutual (4 components)
└── train.py                     # 학습 entry, 마지막에 G2 export 추가됨 (line ~590)

src/stage3/
├── clustering.py                # cluster_primitives (legacy) + groups_from_stage2_grouping (Track 1, 현재 patch unit issue 로 미사용)
├── plane_intersection.py:25     # bbox_margin 자동화 (정정됨)
├── building_instance.py:21      # process_building (use_stage2_groups 옵션 추가됨)
└── citygml_export.py            # CityJSON 출력

scripts/phase2_synthesis/
├── run_stage3.py:42-95          # _load_model + Stage 2 group 호출 (Track 1 implementation, 변경됨)
├── eval_citygml.py:38-60        # CityJSON parser + GT_convex loader (Step 2)
├── gt_stage3_test.py            # GT → polytope (cos_thresh argument 추가됨)
└── diag_cycle_gradient.py       # Track A 스크립트 (GPU 이슈로 미실행)
```

---

이 문서로 새 세션에서 동일 깊이의 기술 논의 + G2 구현 작업 가능합니다. 특정 부분 (코드 스니펫, 데이터, 수식) 더 필요하면 §11 의 파일들을 reference 로 들어 질문하세요.
