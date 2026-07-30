# W_D — 손실 항 수식·정규화·스케줄 감사 (읽기 전용, 관찰만)

> 목적: D 손실의 가중 불균형(structure 원시 ~17 vs photo/normal ~0.27)이 **(a) 진짜 스케일 차이**인지
> **(b) 합산 대 평균 차이**인지 판별하고, 정규화를 어디에 둘지 결정하기 위한 사실 수집. 코드 변경·판정 없음.
> 브랜치 feature/p2-prior-full. 590-step 원시값 = Phase 2 사전점검(600-step smoke) step 590의 **비가중** 손실.

## 1) 손실 합성 위치 (file:line)

전부 `src/stage2/train.py` 학습 루프 안에서 `loss_total`에 **가중치를 곱해 더함** — 추가 정규화 없음:

| 항 | 가중 곱·합산 지점 | 손실 함수 호출 |
|---|---|---|
| photo | [train.py:586](src/stage2/train.py#L586) `loss_total = w_photo * loss_photo` | [train.py:585](src/stage2/train.py#L585) `L.l_photo` |
| depth | [train.py:593](src/stage2/train.py#L593) `+ w_depth_eff * loss_depth` | [train.py:591](src/stage2/train.py#L591) `L.l_depth` |
| normal | [train.py:602](src/stage2/train.py#L602) `+ w_normal_eff * loss_n` | [train.py:600](src/stage2/train.py#L600) `L.l_normal` |
| nc | [train.py:607](src/stage2/train.py#L607) `+ w_nc * loss_nc` | [train.py:606](src/stage2/train.py#L606) `L.l_nc` |
| distort | [train.py:610](src/stage2/train.py#L610) `+ w_distort * loss_dist` (w=0, off) | gsplat 2DGS distort |
| sem | [train.py:618](src/stage2/train.py#L618) `+ w_sem * loss_sem` | `L.l_sem` (render_semantic) |
| mutual | [train.py:690](src/stage2/train.py#L690) `+ (w_mutual * scale) * loss_mut` (w=0, off) | `l_mutual` |
| **structure** | [train.py:728](src/stage2/train.py#L728) `+ w_structure * loss_str_total` | [train.py:714](src/stage2/train.py#L714) `l_structure` |

가중 스칼라 읽기: [train.py:437-454](src/stage2/train.py#L437) (`w_depth/w_normal/w_nc/w_sem/w_structure …`).

## 2)+3)+4) 항별 정의 — 합/평균·정규화·단위

모든 항이 **내부적으로 mean(평균) 정규화**돼 있다 (합산 항 없음). 정의 출처 `src/stage2/loss/{data_fitting,structure}.py`.

| 항 | 수식 | 합·평균 | 무엇에 대해 | 정규화 | 단위 | 590 원시 |
|---|---|---|---|---|---|---|
| **L_photo** | (1−λ)·\|p−g\|₁ + λ·(1−SSIM), λ=0.2 | **mean** | 픽셀 | `.mean()` (전 픽셀) [data_fitting.py:41-45](src/stage2/loss/data_fitting.py#L41) | 무차원 [0,~1] | 0.271 |
| **L_depth** | \|d_pred − d_gt\|·m / Σm | **mean** | 유효 픽셀 | `sum/mask.sum` [data_fitting.py:8-13,48-50](src/stage2/loss/data_fitting.py#L48) | **미터(m)** | 4.47 |
| **L_normal** | (1 − \|cos(n_render, n_gt)\|)·m / Σm | **mean** | 유효 픽셀 | `sum/mask.sum` [data_fitting.py:53-69](src/stage2/loss/data_fitting.py#L53) | 무차원 [0,2] | 0.268 |
| **L_nc** | (1 − n_render·n_surf)·α / Σα | **mean(α-가중)** | 픽셀 | α-가중 mean [data_fitting.py:84-97](src/stage2/loss/data_fitting.py#L84) | 무차원 [0,2] | (≈0.x) |
| **L_sem** | CE(logits, label, ignore=0) | **mean** | 비-ignore 픽셀 | `F.cross_entropy` 기본 mean [data_fitting.py:72-81](src/stage2/loss/data_fitting.py#L72) | nats | 1.09 |
| **L_str = na+cp** | 아래 분리 | **mean** | 그룹된 프리미티브 M | `.mean()` (M개) | 혼합 | 17.31 |
| └ na (normal_align) | (1 − \|cos(nᵢ, n_k)\|)² | **mean(M)** | 그룹된 프리미티브 | `.mean()` [structure.py:47-48](src/stage2/loss/structure.py#L47) | **무차원 [0,1]** | ≤1 |
| └ cp (coplanar) | (n_k·cᵢ + d_k)² | **mean(M)** | 그룹된 프리미티브 | `.mean()` [structure.py:51-52](src/stage2/loss/structure.py#L51) | **미터²(m²)** | ≈16–17 |

마스킹: L_depth/L_normal = `mask = depth_gt>0` / `normal_mask` (유효 MVS 픽셀만); L_nc = α(alpha.detach()) 가중; L_sem = `ignore_index=0`(BG).

### 3) L_structure 정밀 (사용자 핵심 질문)
- **cp는 그룹별 점-평면 거리의 "합"이 아니라 "평균"** — `loss_coplanar = (sd**2).mean()`, sd = n_k·cᵢ+d_k = 점→대표평면 **부호거리(미터)** [structure.py:51-52](src/stage2/loss/structure.py#L51). 즉 **그룹된 전 프리미티브 M에 대한 제곱거리 평균 (m²)**. na도 동일하게 M 평균 [structure.py:48](src/stage2/loss/structure.py#L48).
- 그룹 통계(590-step smoke, dense N=3,257,571): n_groups=1735, grouped M ≈ 0.937·N ≈ **3.05M**, voxel/merge = `structure_voxel_size 2.0 · merge_n_cos 0.92 · merge_d_tol 0.5 · min_group 30` (G2).
- **단위당 값**: L_str는 **이미 M(≈3.05M)에 대한 평균**이다. 합으로 오해해 17.31/3.05M로 나누면 5.7e-6 (무의미) → **합이 아님이 확증**. 분해하면 na ≤ 1(무차원), 따라서 cp ≈ **16.3–17.3 m²** → **RMS 점-평면 거리 √17 ≈ 4.1 m**. 17이 큰 이유는 (정규화 부재가 아니라) **제곱미터(m²) 단위 × 초기 G2 그룹의 ~4m 잔차**.

### 4) L_depth 정밀
- 원시 4.47 = **유효 픽셀 평균 절대오차 ≈ 4.5 미터 (절대값)**. **씬 스케일·near/far·NDC 정규화 없음** — 카메라-Z 깊이를 GS-local 미터 그대로 L1 [data_fitting.py:48-50](src/stage2/loss/data_fitting.py#L48). depth_pred = 렌더 expected/median depth(GS-local m), depth_gt = MVS `.geometric.bin`(카메라-Z m, (H,W)로 resize), mask = depth_gt>0. `depth_scale=1.0`(GS-local=UTM 평행이동이라 미터 동일).

## 5) config 추출 + 스케줄 구현 (gs_prior_full_dense/acmp)

| 키 | 값 | 스케줄 구현 (file:line) |
|---|---|---|
| w_photo | 1.0 | 상수 |
| **w_depth** | 0.1 | **선형 ramp**: `_ramp_weight_scale(it, 5000, "ramp", 5000)` [train.py:111-126,592](src/stage2/train.py#L111) → 0(it<5000) → 선형 → 1.0(it≥10000) |
| **w_normal** | 0.15 | **선형 ramp**: warmup 5000 + ramp 5000 (동일 함수) [train.py:601](src/stage2/train.py#L601) |
| w_nc | 0.05 | 상수 [train.py:607](src/stage2/train.py#L607) |
| w_sem | 0.1 | 상수 [train.py:618](src/stage2/train.py#L618) |
| w_distort | 0.0 | off |
| w_mutual | 0.0 | off (ramp 헬퍼는 mutual 전용이었으나 D에선 depth/normal로 일반화) |
| **w_structure** | 0.08 | **하드 게이트(ramp 아님)**: `it ≥ structure_warmup` 이후 상수 [train.py:697,728](src/stage2/train.py#L697) |
| w_structure_na / _cp | 1.0 / 1.0 | l_structure 내부 곱 [structure.py:54](src/stage2/loss/structure.py#L54) |
| structure_grouping | g2 | — |
| structure_voxel_size | 2.0 | — |
| structure_warmup | 15000 | 게이트 시작 step |
| structure_regroup_every | 1000 | 재그룹 주기 |
| max_iter | 30000 | — |
| data_root | results/tum_transfer/data_geoidfix | depth/normal map = `stereo/{depth,normal}_maps` 심링크 |

스케줄 구현 형태 요약: **depth/normal = 선형 ramp**(0→목표, warmup 후 ramp_steps에 걸쳐) / **structure = step 게이트**(warmup 후 즉시 상수) / **나머지 = 상수**.

## 6) 한 줄 관찰 (판정 없음)

**모든 항은 이미 평균(mean) 정규화돼 있으므로 불균형은 (b) 합산 대 평균 차이가 아니라 (a) 진짜 단위·스케일 차이다** — L_coplanar는 **제곱미터(m²) 평균(~17 m², RMS ~4.1 m)**, L_depth는 **미터(m) 평균(~4.5 m)**으로 물리 단위·큰 크기를 갖는 반면 L_photo/L_normal/L_nc는 무차원 O(0.1–1), L_sem은 CE nats O(1)이다. 따라서 균형은 가중치만으로가 아니라 **계량 항을 길이 스케일로 정규화**(cp ÷ s², depth ÷ s; 예: s=구조 voxel 2 m 또는 씬 깊이)하면 단위가 무차원화돼 항 간 비교가 직접 가능해진다. (현재는 w_structure 0.08·w_depth 0.1로 가중 단에서만 보정.)
