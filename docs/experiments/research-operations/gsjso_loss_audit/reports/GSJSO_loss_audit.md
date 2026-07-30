# GS-JSO 손실 구현 ↔ 설계(스케치) 대조 audit

> **분석 일자:** 2026-06-17 · **branch:** `feature/p2-gsjso`
> **성격:** 읽기 전용 (코드 무변경). **판정은 사람이 한다** — 본 문서는 코드 사실 확인·대조·근거 제시까지.
> **대조 기준:** 스케치 docx는 repo에 없음. CLAUDE.md / 태스크에 임베드된 설계 스케치(L_joint = L_2DGS-base + λ_sem·L_sem + λ_gs·L_geom-sem + λ_abs·L_surface-abs)가 **유일한 기준**.
> **증거 규칙:** 모든 코드 주장은 `file:line`. 못 찾으면 "코드에 없음" 명시. 매직넘버는 config 또는 코드 상수 근거로만, 추정이면 "추정" 표기.

---

## 0. 요약 (핵심 결론)

1. **L_mutual의 정체 = 스케치 `L_geom-sem`의 `L_sem-normal`(Blaha-style roof/wall normal prior)의 부분 구현 + 스케치에 없는 항(terrain-normal, height prior, sem↔geom KL).** 1:1 대응 항이 아니다. wall `L_vert = (n·g)²`(`mutual.py:162`)은 스케치 ρ_wall(n)=(n·z)²와 동형이나, roof `L_slope = relu(τ − (n·g)²)²`(`mutual.py:164`)는 스케치 ρ_roof=max(0, τ−(n·z))²와 **형태가 다르다**(코드는 dot² 에 대한 hinge).
2. **스케치 `L_surface-abs`의 연산자 Ψ_sem(soft assignment q_ik = softmax(−D_ik) + 가중 공분산 최소고유벡터 plane-fit + descriptor contrastive + plane-sem entropy)는 코드에 전혀 없다.** 코드의 Mechanism 2는 **hard-argmax voxel-hash 그룹핑 + index_add 가중평균 normal + detached 대표평면에 대한 두 MSE**로 단순화되어 구현됐다(`structure.py:45-52`, `grouping.py:62-124`).
3. **무텍스처 지붕 복구의 메커니즘적 핵심 손실 = `L_sem-normal`(코드의 `L_vert`/`L_slope`, `mutual.py:162-164`)과 `L_normal_align`(`structure.py:45-48`).** photo/depth 신호가 약한 무텍스처 면에서 normal을 **의미(roof/wall)로 고정**하고 그룹 대표 normal로 정렬하는 것이 텍스처-비의존 복구 경로다.
4. **semantic 라벨은 학습형 2D 분할기 산물이 아니다.** ablation이 쓰는 라벨은 합성 GT(3D BAG CityGML 면 의미 → Blender pass_index → PNG, `compose_scene.py:26-27` → `postprocess_exr.py:117-127`). **실데이터(성수동)용 라벨 생성 코드는 레포 부재** — 실데이터 스파이크 전 라벨 소스를 먼저 마련해야 한다.
5. **최대 격차:** (a) `L_surface-abs` 전체(soft assign·가중 plane-fit·descriptor·plane-sem entropy) 결측, (b) `L_mv-sem`(multi-view semantic KL)·`L_boundary-img` 결측, (c) descriptor head 자체가 모델에 부재(`model.py:67-100`), (d) L_sem의 confidence/visibility 가중 w 결측(균일 CE).
6. **역방향 격차(코드에만 있고 스케치에 없음):** `L_distort`(2DGS distortion, `train.py:425-426`, 단 phase2 w=0), L_mutual의 terrain-normal·height prior, supervised depth-L1/normal-L1(`train.py:409,417`), 2-함수 grouping(G1 학습용 / G2 분석용), semcal KL teacher(`mutual.py:204-241`, 기본 off).
7. **활성 손실 요약(phase2 both, max_iter=30000):** 0–10k photo+depth+normal+nc+sem만, 10k–20k +L_mutual, 20k–30k +L_structure. mutual/structure 모두 **step-function 활성**(warmup 후 즉시 full weight). mutual은 `gravity_file` 없으면 영구 OFF(`train.py:456-457`).

---

## 1. 구현 손실 인벤토리 표

backward에 더해지는 항만 학습됨(`train.py:568 loss_total.backward()`). 가중치 default는 `cfg.get(...)` 코드 상수(`train.py:306-372`), 실측값은 §6/D5 config.

| 항 | 계산내용 (수식 요지) | 지도신호 | 정의 file:line | 조립 file:line | 활성/휴면 (phase2) |
|----|------|------|------|------|------|
| **L_photo** | `(1−λ)·mean(\|rgb_pred−rgb_gt\|) + λ·(1−SSIM)`, λ=`photo_lam`=0.2 | **GT** RGB (`batch["rgb"]`) | `data_fitting.py:41-45` | `train.py:403-404` | **활성** (항상) |
| **L_depth** | 양수-depth 픽셀 마스크 L1 | **GT/pseudo** depth (`batch["depth"]`+mask) | `data_fitting.py:48-50` | `train.py:409-410` | **활성** (`"depth" in batch`, w=0.5) |
| **L_normal** | `1 − \|cos(n_render, n_GT)\|`, world frame, 마스크 평균 | **GT/MVS-유도** normal | `data_fitting.py:53-69` | `train.py:417-418` | **활성** (`"normal" in batch`, w=0.05) |
| **L_nc** | `1 − (n_render·n_surf)`, alpha-가중. n_surf=렌더 depth-유도 normal | **유도(self-sup)** — GT 없음, alpha detach | `data_fitting.py:84-97` | `train.py:422-423` | **활성** (항상, w=0.05) |
| **L_distort** | gsplat 반환 per-pixel distortion의 `.mean()` | **유도(self-sup)** geom 정규화 | gsplat 반환, `train.py:425` | `train.py:425-426` | **휴면** (phase2 `w_distort=0.0`) |
| **L_sem** | `CE(logits, label, ignore_index=0)`, per-pixel, 렌더 logits 기반 | **GT** semantic 라벨 (`batch["semantic"]`) | `data_fitting.py:72-81` | `train.py:433-434` | **활성** (`"semantic" in batch` & w_sem>0, w=0.1) |
| **L_mutual** | `Σ (p_class × geom_err).mean()`, 하위 5항 (아래) | **유도(도메인규칙)** + e_gravity + 학습 sem | `mutual.py:60-292` | `train.py:506` | **활성** (mutual/both, it≥10000) |
| **L_structure** | `λ_na·L_normal_align + λ_cp·L_coplanar` | **유도(inter-prim)** — 대표평면(detach) | `structure.py:20-60` | `train.py:547` | **활성** (struct/both, it≥20000) |

### 1-A. L_mutual 하위항 (메커니즘 1, `mutual.py`)

`p = softmax(sem_logits)`(`mutual.py:126`), `dot = (n·e_g)`(`mutual.py:159`). 모든 항이 `(p_class × geom_err).mean()` → p_c와 geom **양방향 gradient**.

| 하위항 | 계산 | gradient 대상 | file:line | 활성/휴면 |
|------|------|------|------|------|
| **L_vert** (wall) | `(p_wall · dot²).mean()`; `L_vert=dot²` (벽 normal 수평이면 0) | n_i, f_i | geom `mutual.py:162`, reduce `192` | 활성 (enable 기본 True) |
| **L_slope** (roof) | `(p_roof · relu(τ−dot²)²).mean()`, τ=0.15 (roof가 wall처럼 수평이면 penalty) | n_i, f_i | geom `mutual.py:164`, reduce `193` | 활성 |
| **L_horiz** (terrain) | `(p_terrain · gate · (1−\|dot\|)²).mean()` (terrain normal 수직이면 0) | n_i, f_i | geom `mutual.py:163`, reduce `194` | 활성 (gate 기본 1.0) |
| **L_height** (roof+terrain) | `(p_roof·relu(th−h)² + p_terrain·gate·relu(h−th)²).mean()`, h=gravity 최대축 성분 | **c_i**, f_i | geom `mutual.py:174,189`, reduce `197` | 활성 (legacy 경로) |
| **L_sem_geom_calib** | reliability·`KL(s_geom ‖ p_rw_norm)`. dot² teacher **detach** → f_i(roof/wall)만 교정 | f_i only | `mutual.py:204-241` | **휴면** (`semcal_weight_beta=0.0` 기본) |

**gradient mode**(`mutual_mode`, phase2=`full`): `none`→0(`mutual.py:101`), `sem2geo`→p_* detach(`145-149`), `geo2sem`→n,c detach(`155-157`). phase2는 `full`이라 f_i↔n_i 양방향.

### 1-B. L_structure 하위항 (메커니즘 2, `structure.py`)

grouped primitive만(`mask=group_ids>=0`, `structure.py:37`). 대표평면 `(n_k,d_k)` **detach**(`structure.py:42-43`) → primitive→plane 단방향.

| 하위항 | 계산 | gradient 대상 | file:line |
|------|------|------|------|
| **L_normal_align** | `((1−\|cos(n_i,n_k)\|)²).mean()`, n_k detach | **n_i only** | `structure.py:45-48` |
| **L_coplanar** | `((n_k·c_i + d_k)²).mean()`, n_k·d_k detach | **c_i only** | `structure.py:50-52` |

그룹핑 입력(`centers/normals/sem_logits/scales`) 전부 `.detach()`(`train.py:518-524`) → **f_i에 gradient 없음**(argmax 이산 연산, `structure.py:12`).

---

## 2. 스케치 ↔ 코드 매핑표

| 스케치 항 | 코드 대응 (file:line) | 상태 | 비고 |
|----|------|------|------|
| **L_2DGS-base = L_rgb** | `l_photo` `data_fitting.py:41-45`, `train.py:403` | **구현** | L1+SSIM 혼합 (λ=0.2) |
| L_2DGS-base = λ_dd·**L_depth-dist** | `loss_dist=distort.mean()` `train.py:425-426` | **부분** | 코드엔 있으나 phase2 `w_distort=0.0` → 실효 OFF |
| L_2DGS-base = λ_nc·**L_normal-cons** | `l_nc` `data_fitting.py:84-97`, `train.py:422` | **구현** | n_render ↔ depth-유도 n_surf, w_nc=0.05 |
| (base 외 추가) **supervised depth-L1** | `l_depth` `data_fitting.py:48-50`, `train.py:409` | **역방향 격차** | 스케치 base는 self-consistency만; 코드는 GT/MVS depth L1 추가 |
| (base 외 추가) **supervised normal-L1** | `l_normal` `data_fitting.py:53-69`, `train.py:417` | **역방향 격차** | 스케치 base에 없음; GT/MVS normal cosine |
| **L_sem = Σ w·CE(Y,S), w=conf/visibility** | `l_sem` `data_fitting.py:72-81`, `train.py:433` | **부분** | CE(ignore_index=0)는 구현. **w(conf/visibility) 가중 없음** — 균일 CE. 렌더는 geometry detach(`renderer.py:119-123`)로 sem_logits만 gradient |
| **L_geom-sem · L_sem-normal** (ρ_roof, ρ_wall) | `L_vert`/`L_slope` `mutual.py:162-164` | **부분** | **★L_mutual 정체의 핵심.** L_vert=dot²는 ρ_wall=(n·z)²와 동형. L_slope=relu(τ−dot²)²는 ρ_roof=max(0,τ−(n·z))²와 **형태 상이**. 스케치엔 없는 `p_c×geom` 양방향 곱 추가 |
| **L_geom-sem · L_mv-sem** (multi-view KL) | — | **결측** | KL/multi-view consensus 코드 hit 0. L_mutual은 렌더 없이 프리미티브 직접 작용(`train.py:439` "no rendering") — multi-view 아님 |
| **L_geom-sem · L_boundary-img** | — | **결측** | boundary grep hit 0. (스케치 자체도 eq.118에만 있고 본문 정의 결손 = 설계 결함) |
| **L_surface-abs · 연산자 Ψ_sem** (soft plane 추정) | `grouping.py:group_primitives` (hash) | **결측(대체)** | Ψ_sem의 soft·가중·refit 루프 없음. hard voxel-hash로 대체 |
| Ψ_sem · **soft assign q_ik=softmax(−D_ik)** | — | **결측** | `grouping.py:62,70,85` 전부 argmax/unique hash. softmax/q_ik hit 0 |
| Ψ_sem · **결합거리 D_ik** (α_d/α_n/α_s/α_h) | — | **결측** | 거리 가중합 없음; (class,voxel,dir_bin) 정수 hash `grouping.py:77-85` |
| Ψ_sem · **가중 공분산 최소고유벡터 plane-fit** | `grouping.py:118-124` (가중평균) | **결측(대체)** | rep_n=normalize(index_add(n·w)) 단순 가중평균. eigh/svd/covariance hit 0 |
| **L_plane-fit** = Σ q_ik·w_i·(n_k·μ_i+d_k)² | `L_coplanar` `structure.py:50-52` | **부분** | (n_k·c_i+d_k)² 형태는 일치. **q_ik·w_i 가중 없음** — grouped 멤버 단순 mean |
| **L_plane-normal** = Σ q_ik·w_i·(1−n_i·n_k) | `L_normal_align` `structure.py:45-48` | **부분** | (1−\|cos\|)**²**(스케치는 1차), \|cos\| 부호불변, **q_ik·w_i 가중 없음** |
| **L_plane-sem** = Σ_k H(p_k) (plane purity entropy) | — | **결측** | structure.py에 entropy 항 0. entropy grep은 mutual.py terrain-gate/semcal·train.py 진단용뿐 |
| **L_plane-desc** (descriptor contrastive) | — | **결측** | descriptor head 부재(↓), contrastive hit 0 |
| **descriptor head h_i** (모델 입력) | — | **결측** | `model.py:67-100` 학습 파라미터: means/quats/log_scales/opacities_raw/sh0/shN/sem_logits만. descriptor/embedding head 없음 |
| **L_coverage** (CLAUDE.md "후보") | — | **결측(후보 일치)** | structure.py에 coverage 항 없음. 설계상 후보 상태와 일치 |
| **스케줄** ①warmup→②sem→③geom-sem→④plane→⑤feedback→⑥joint | warmup gate `train.py:74-83,455,513` | **부분** | ①warmup·④plane(regroup 500)은 구현. **⑤surface-abs→Gaussian feedback 미존재**(rep detach). 가중 ×0.5/×1/×2 grid는 코드에 없음(config 수동값) |
| **역방향 격차: L_distort** | `train.py:425-426` | (코드 only) | 스케치 L_joint에 없음 (단 phase2 w=0) |
| **역방향 격차: L_horiz (terrain normal)** | `mutual.py:163` | (코드 only) | 스케치 어느 항에도 없음 |
| **역방향 격차: L_height (roof/terrain altitude)** | `mutual.py:174,189` | (코드 only) | c_i gradient. 스케치 L_geom-sem/L_surface 어디에도 height prior 없음 |
| **역방향 격차: sem_geom_calib (KL teacher)** | `mutual.py:204-241` | (코드 only, off) | sem↔geom self-distillation. 기본 off |

### 2-A. L_mutual 정체 확정 (코드 근거)

- **L_mutual ≠ L_mv-sem**: L_mutual은 **렌더링 없이 프리미티브에 직접 작용**(`train.py:439` 주석 "no rendering"; `mutual.py`는 normals/centers/sem_logits만 입력 `train.py:459-461`). multi-view KL consensus 부재.
- **L_mutual ⊃(부분) L_sem-normal**: wall/roof normal prior `mutual.py:162-164`가 스케치 ρ_wall/ρ_roof와 친족. 단 `p_class × geom` **양방향 곱**(f_i↔n_i, `mutual.py:192-197`)은 스케치 L_sem-normal에 명시 안 됨.
- **L_mutual = L_sem-normal(부분) + 스케치에 없는 terrain-normal·height·sem↔geom KL.** 1:1 대응 항이 아니다 — 스케치 어느 단일 항으로도 매핑 불가.

---

## 3. semantic 라벨 출처

**출처 = 합성 GT (학습형 2D 분할기 산물 아님).** ablation이 실제 쓰는 라벨은 3D BAG CityGML 면 의미 → Blender material pass_index → PNG 결정론 생성(`compose_scene.py:26-27` `LABEL_TO_NAME={1:Roof,2:Wall,3:Ground}` → `postprocess_exr.py:117-127` `process_semantic`). MatrixCity 경로는 GT depth+normal 룰 분류(`generate_rule_semantic.py:41-88`, 임계 `H_TH=0.7/V_TH=0.3` 코드 상수). **결합 방식 = per-pixel 렌더+CE(투영 아님):** `render_semantic`(`renderer.py:97-138`)이 `model.sem_logits`를 alpha-compositing으로 (H,W,K) 렌더하되 기하 파라미터(means/quats/scales/opacities) **전부 detach**(`renderer.py:119-123`) → L_sem gradient는 `sem_logits`로만 흐른다. 라벨은 per-pixel GT(`dataloader.py:244-252`, uint8 0..3, BG=0 ignore)와 `CE(ignore_index=0)`(`data_fitting.py:72-81`)로 결합된다. `sem_logits`는 학습 가능 Adam 파라미터((N,4), `model.py:99-100`; optim `densification.py:55-56` lr_sem). **GT/pseudo/부재 판정: 합성셋은 GT(또는 GT-파생 hard label), 실데이터(성수동)는 부재** — 성수동/Metashape semantic 생성 코드가 레포에 없고(grep 0건), 어떤 학습형 분할기(SAM/Grounded SAM/mmseg/detectron2 등) import도 0건. PNG 부재 시 `dataloader.py:248`이 조용히 `semantic=None` → `train.py:429` 가드가 False → **L_sem=0으로 무음 비활성**(명시적 경고 없음).

---

## 4. 결측·무거움 목록 + 무텍스처 지붕 복구에 메커니즘적으로 필요한 항

### 4-A. 결측 항과 추가 난이도

| 결측 항 | 코드 상태 | 추가 난이도 | 근거 |
|------|------|------|------|
| **L_sem confidence/visibility 가중 w** | 균일 CE | **가벼움** | `data_fitting.py:72-81`에 픽셀 가중 1줄 추가 가능. visibility는 alpha/depth-mask 재사용 |
| **L_plane-sem (entropy purity)** | 없음 | **가벼움** | 그룹별 평균 sem 분포 H(p_k). 그룹핑 산출(`grouping.py`) 위에 entropy 1항 |
| **q_ik soft assignment + w_i 가중** | hard hash | **무거움** | grouping을 softmax(−D_ik)로 교체 → 미분 가능 멤버십. D_ik 4항(α_d/α_n/α_s/α_h) 설계+튜닝 필요 |
| **가중 공분산 최소고유벡터 plane-fit** | 가중평균 | **무거움** | index_add 가중평균 → batched 가중 공분산 + `torch.linalg.eigh`. plane refit feedback(rep 미분) 재설계 |
| **descriptor head h_i + L_plane-desc** | 모델에 head 부재 | **무거움** | `model.py`에 per-Gaussian embedding 파라미터 신설 + densification 동기화(`train.py:38-46`) + contrastive 손실 + 렌더 경로 |
| **L_mv-sem (multi-view KL)** | 없음 | **무거움** | view-weight ω_iv 다시점 consensus Ŷ_i 집계 + KL. 다중 뷰 배칭/캐싱 필요 |
| **L_boundary-img** | 없음 (스케치도 정의 결손) | **불명** | 스케치 본문 정의 자체 부재 → 정의 확정이 선행. 정의 전 구현 불가 |

### 4-B. 무텍스처 지붕 복구에 메커니즘적으로 필요한 항 (논증)

무텍스처 면은 photo(`L_photo`)·depth(`L_depth`) 신호가 약하다(평탄·균질 → SSIM/L1 gradient 빈약, MVS depth 부정확). 텍스처-비의존 복구 경로는 **의미와 기하의 결합**이다.

1. **L_sem-normal (코드 `L_vert`/`L_slope`, `mutual.py:162-164`) — 1차 핵심.** roof로 분류된(`p_roof` 높은) Gaussian의 normal을 "수평이 아님(상향)"으로, wall을 "수직축 직교(수평)"로 **의미가 normal을 고정**한다. photo 신호가 없어도 `p_roof × relu(τ−dot²)²`가 roof normal을 wall-like 방향에서 밀어낸다 → **무텍스처 지붕 면의 normal을 의미로 복구**. `p_c×geom` 양방향 곱이라 normal↔라벨 상호 교정.
2. **L_normal_align (코드 `structure.py:45-48`) — 2차 핵심.** 같은 그룹(같은 roof 면)의 normal을 대표 normal로 정렬 → 무텍스처로 인한 개별 noise를 그룹 합의로 평활. 평탄 지붕의 일관 평면 형성.
3. **L_coplanar (코드 `structure.py:50-52`) — 보조.** 중심을 대표 평면에 끌어당김 → 무텍스처 면의 두께/부풀음 억제.
4. **(설계만, 결측) L_plane-fit + 가중 공분산 plane-fit.** soft·가중이면 무텍스처 면 추정이 더 robust하나 현 코드는 hard·단순평균이라 효과 제한적.

따라서 무텍스처 복구의 **메커니즘적 최소 조합 = L_sem-normal(L_vert/L_slope) + L_normal_align**, 전제는 **신뢰 가능한 semantic 라벨**(§3 — 실데이터엔 부재). 라벨이 약하면 1·2가 동작 안 하므로 기하 항(depth/normal·coplanar)으로 비중 이동 또는 라벨 준비 선행.

---

## 5. 스파이크-최소 학습 권고 (주산출)

### (a) 켤 손실 부분집합 + 학습 순서/스케줄 + 가중치 출발점

근거는 phase2 config 실측값(D5) 또는 `train.py` `cfg.get` 코드 default. 추정은 명시.

| 단계 | iter 구간 | 켜는 손실 | 가중치 출발점 (근거) |
|------|------|------|------|
| ① warm-up (geometry only) | 0 – ~10k | L_photo + L_depth + L_normal + L_nc | `w_photo=1.0`, `w_depth=0.5`, `w_normal=0.05`, `w_nc=0.05` (`phase2_*.yaml:18-21`) |
| ② semantic head | (라벨 있으면) ① 동시 | + L_sem | `w_sem=0.1` (`phase2_baseline.yaml:23`); 라벨 없으면 **생략** |
| ③ intra-prim geom-sem | 10k – | + L_mutual | `w_mutual=0.1`, `mutual_warmup=10000`, `mutual_tau=0.15`, `mutual_height_th=0.15`, `mutual_mode=full` (`phase2_mutual.yaml:25-29`). **`gravity_file` 필수**(`train.py:456-457`) |
| ④ inter-prim structure | 20k – | + L_structure (regroup 500) | `w_structure=0.1`, `w_structure_na=w_structure_cp=1.0`, `structure_warmup=20000`, `structure_regroup_every=500` (`phase2_structure.yaml:27-31`) |

- L_distort는 phase2 default `w_distort=0.0`(`phase2_*.yaml:22`)이라 **꺼둠** 권장(켜려면 코드 default 100.0 주의, `train.py:310`).
- mutual/structure는 step-function(warmup 후 즉시 full). 부드러운 도입이 필요하면 `mutual_schedule="ramp"` + `mutual_ramp_steps>0`(`train.py:79-82`) 사용 가능 — phase2는 `constant`.

### (b) 각 항 → 무텍스처 복구 메커니즘 (1줄)

- **L_depth/L_normal:** MVS 기하로 초기 면 위치·방향 고정 (텍스처 무관, 단 무텍스처면 MVS 부정확).
- **L_nc:** 렌더 normal ↔ depth-유도 normal 일관 → 평면성 자기지도(텍스처 불요).
- **L_sem:** roof/wall/terrain 라벨을 Gaussian에 부여 → 아래 의미-기하 결합의 전제.
- **L_mutual (L_vert/L_slope):** 무텍스처 지붕 normal을 의미로 고정(상향), wall은 수평 normal로 — **텍스처-비의존 복구의 1차 메커니즘**.
- **L_structure (L_normal_align/L_coplanar):** 같은 면 그룹의 normal·중심을 대표 평면으로 정렬 → 무텍스처 noise를 합의로 평활.

### (c) 라벨 가용성 반영

- **라벨 있음(합성셋):** 위 ①→④ 전체 권장. L_sem·L_mutual·L_structure 모두 의미 의존이므로 정상 동작.
- **라벨 약함/부재(실데이터 성수동):** §3대로 라벨 생성 코드 부재. 두 경로:
  - **(권장) 라벨 준비 선행** — 실데이터용 per-image semantic(roof/wall/terrain) 생성기 마련(현 미구현). 이후 ①→④.
  - **(라벨 없이)** 의미 의존 항(L_sem·L_mutual·L_structure) **비중↓ 또는 OFF**, 기하 항(L_photo+L_depth+L_normal+L_nc) 위주. 단 이 경우 무텍스처 복구의 1차 메커니즘(L_sem-normal)이 동작 안 함 → 복구 품질 제한. `load_semantic` 없으면 L_sem이 무음 0(`train.py:429`)이고 L_mutual은 `e_gravity`/sem 없으면 OFF.

### (d) 풀 방법 로드맵은 부록 5A.

### 부록 5A. 풀 방법 로드맵 (스케치 전 손실 단계적)

현 코드(L_sem-normal 부분 + L_plane-fit/normal 부분) → 스케치 full로 가는 단계:
1. **가벼움 먼저:** L_sem에 confidence/visibility 가중 w 추가(`data_fitting.py:72`); L_plane-sem entropy 항 추가(그룹별 H(p_k)).
2. **중간:** L_plane-fit/normal에 q_ik·w_i 가중 도입(현 단순 mean → 가중 mean), L_slope를 스케치 ρ_roof 형태(max(0,τ−(n·z))²)로 정렬.
3. **무거움:** grouping을 hard hash → soft q_ik=softmax(−D_ik)로 교체(D_ik 4항), 가중 공분산 최소고유벡터 plane-fit + rep 미분 feedback 루프(⑤ surface-abs→Gaussian).
4. **무거움:** descriptor head h_i 모델 신설 + L_plane-desc contrastive; L_mv-sem multi-view KL(view-weight ω_iv); L_boundary-img(스케치 정의 확정 선행).

---

## 6. 다음 단계 핸드오프 (배선·실행이 받을 facts)

### ① 학습 진입점

- **단일 조건:** `python -m src.stage2.train --config configs/mutual_loss/core_ablation/phase2_baseline.yaml` (argparse는 `--config` 단 하나, required; `train.py:233-236`). CLI 손실 토글 없음 — 전부 YAML.
- **4조건 순차:** `bash scripts/phase2_synthesis/run_ablation.sh` (`for cond in baseline mutual structure both`, `run_ablation.sh:21,26-28`, 단일 GPU 직렬, cwd `/workspace/JointBuildGS`).
- backward `train.py:568`, step `train.py:575-576`. config 경로: `configs/phase2_{baseline,mutual,structure,both}.yaml`, vanilla `configs/input_and_alignment/matrixcity_vanilla.yaml`, fc_s6 `configs/mutual_loss/fc_screening/fc_s6/{A0_baseline_w0,A1_original_mutual}.yaml`.

### ② P0 데이터 적재 (그대로 먹나 / 어댑터 필요)

| P0 자산 | 그대로? | 근거 |
|------|------|------|
| COLMAP 포즈 **`.bin`** (`cameras/images/points3D.bin`) | **예** | `colmap_io.py:96-133`, `dataloader.py:107-109` |
| COLMAP 포즈 **`.txt`** | **아니오 → .bin 변환 어댑터** | 텍스트 파서 코드 없음 (struct 바이너리만) |
| **undistort 영상** | **예** (이미 undistort 전제) | `K()`가 왜곡계수 무시 `colmap_io.py:56-57`, undistort 호출 없음 |
| **distorted 영상** | **아니오 → 사전 undistort 어댑터** | `dataloader.py:231-234`에 cv2.undistort 없음 |
| **EPSG:25832 CRS** | **무시됨**(보존 안 됨) | stage2 전체 epsg/crs/utm/proj grep 0건; 로컬 미터 그대로 |
| depth/normal GT | COLMAP `stereo/*.bin` 또는 EXR이면 예 | `dataloader.py:135-157` |
| semantic 라벨 | `semantic/<stem>.png` 있으면 예; 없으면 무음 None | `dataloader.py:244-252` (실데이터 생성기 부재, §3) |

레이아웃: `root/images/`, `root/sparse/0/{cameras,images,points3D}.bin`(없으면 `sparse/` 폴백 `dataloader.py:103-105`), `[depth/ normal/ semantic/]`.

### ③ GS 산출물 형태 + 점군 export 경로

- **1차 산출물:** `<out_dir>/ckpt/final.pt` (`train.py:668`). 내용: `state_dict`(Gaussian raw — means/quats/log_scales/opacities_raw/sh0/shN/sem_logits, `model.py:48-100`) + `stage2_group_ids`/`stage2_rep_normals`/`stage2_rep_d`(최종 1회 재그룹, `train.py:649-664`).
- **렌더 depth/normal/semantic:** 손실 계산용으로만 생성, **디스크 미저장**. eval은 **RGB PNG만**(`<out_dir>/renders/`, `train.py:704-707`).
- **메시 추출:** Stage 2에 **없음** (marching cubes/TSDF/mesh export 없음).
- **평면후보:** `final.pt`의 `stage2_rep_normals`/`stage2_rep_d`(그룹 대표평면, `grouping.py:122-124`)가 유일.
- **점군 export(classified LAZ 등):** Stage 2에 **없음** — `src/stage2` 전체 ply/laz/las/pdal/laspy grep 0건; 레포 전체 LAZ/LAS 0건. Stage 3는 `final.pt`를 직접 torch.load → in-memory numpy → `primitives.npz`(`run_stage3.py:_load_model:63-104`). **Roofer 입력용 classified LAZ + EPSG 부여 어댑터는 미구현**(신규 필요).

### ④ 실행 config 두 벌 (그대로 실행)

| 용도 | config 경로 | prior 상태 (핵심 플래그) |
|------|------|------|
| **vanilla (prior OFF)** | `configs/mutual_loss/core_ablation/phase2_baseline.yaml` | `w_mutual:0.0`(`:26`), `w_structure:0.0`(`:27`), `w_sem:0.1`+`load_semantic:true`. 활성: photo+depth+normal+nc+sem. (순수 photo-only 비교는 `configs/input_and_alignment/matrixcity_vanilla.yaml` — w_depth/normal/sem 전부 0/부재 → photo+nc만) |
| **GS-JSO (prior ON)** | `configs/mutual_loss/core_ablation/phase2_both.yaml` | `w_mutual:0.1`(`:25`), `w_structure:0.1`(`:32`), `gravity_file` 지정(`:30`), `mutual_warmup:10000`, `structure_warmup:20000`. 활성: 전체 + L_mutual + L_structure |

**주의:** config의 `data_root`/`out_dir`/`gravity_file`은 컨테이너 절대경로(`/workspace/JointBuildGS/...`, `phase2_both.yaml:5-7,30`)로, 호스트 경로(`/media/innopam/...`)와 다름 → 컨테이너 안에서 실행하거나 경로 치환 필요. mutual ON은 가중치만으로 부족 — `gravity_file`이 존재해 `e_gravity` 로드돼야 활성(`train.py:366-371,456-457`).
