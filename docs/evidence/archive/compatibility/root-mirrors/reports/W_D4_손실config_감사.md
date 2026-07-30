# W_D4 손실/config 감사

> 범위: 읽기 전용 감사. 신규 학습 0, 신규 점군화/readout 실행 0, 신규 Roofer 재조립 0, 판정 0.
> 현재 브랜치/HEAD = `feat/p2-structure-learn` / `2dda6361b9a05125766fd96f0df32e338fd4f62c`.
> 감사 대상 학습 런 = `phases/p2-gsjso/runs/e5p_train_20260707_C001/`.

## 0. 시작 전 확인

| 항목 | 기록 |
|---|---|
| 현재 브랜치 | `feat/p2-structure-learn` |
| 현재 HEAD | `2dda6361b9a05125766fd96f0df32e338fd4f62c` (`e5-c001-gsdiag: diagnose GS input and tidy figures`) |
| C001 학습 지문 | `phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv` |
| C001 학습 준비 commit | `526d09b301e238ec43c155b01267c323f91f4c83` (`e5p-prep-report: collect A-stage materials`) |
| C001 versions | `phases/p2-gsjso/runs/e5p_train_20260707_C001/versions.txt` |
| 공식 2DGS upstream | `hbb1/2d-gaussian-splatting`, 조회 HEAD `335ad612f2e783a4e57b9cbc4d1e167bd599fc98` |
| 요청 문헌검증 문서 | `docs/W_문헌검증_GS기하_foundation·가중·평가_20260707.md`는 현 checkout에서 미발견 |

사전등록서 §3.1의 성분 문자열은 다음이다.

```text
GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01;warm15k]; gssem)
```

`train_fingerprints.csv`에 기록된 실제 C001 6런 config는 모두 현재 파일 SHA와 일치한다.

| run | config | sha256 | D4 대조 |
|---|---|---:|---|
| sparse r1 | `configs/tum_mob/e5_pilot/gs_e5_C001_sparse_r1.yaml` | `f6b1907c...b1a0ac87` | `gs_d4_sparse.yaml`에서 C001 data/seed/out_dir/replicate seed만 변경 |
| sparse r2 | `configs/tum_mob/e5_pilot/gs_e5_C001_sparse_r2.yaml` | `0bfea53e...6e6a79266` | 동일 |
| dense r1 | `configs/tum_mob/e5_pilot/gs_e5_C001_dense_r1.yaml` | `6a866d81...22572e93` | `gs_d4_dense.yaml`에서 C001 data/seed/out_dir/replicate seed만 변경 |
| dense r2 | `configs/tum_mob/e5_pilot/gs_e5_C001_dense_r2.yaml` | `526e899e...45704420d` | 동일 |
| acmp r1 | `configs/tum_mob/e5_pilot/gs_e5_C001_acmp_r1.yaml` | `c464c94e...9d134b` | `gs_d4_acmp.yaml`에서 C001 data/seed/out_dir/replicate seed만 변경 |
| acmp r2 | `configs/tum_mob/e5_pilot/gs_e5_C001_acmp_r2.yaml` | `e32e16a7...7c394203` | 동일 |

관찰: 사전등록 문자열과 실제 C001 학습 config의 손실·스케줄·densification 값은 일치한다. 정본은 실제 C001 config 그대로 D4 성분 문자열과 같은 것으로 본다.

## 1. 핵심 판별

**2DGS depth-distortion은 D4에서 코드 경로는 존재하지만 `w_distort=0.0`으로 비활성이다.**

**`dep0.03`은 depth-distortion이 아니라 별개의 MVS depth supervision이다.** 코드상 `dep`는 `L.l_depth(depth_pred, depth_gt, depth_mask)`이고, 수식은 유효 픽셀 마스크에 대한 `|d_pred - d_gt|` 평균 L1이다. 2DGS distortion은 별도 `loss_dist = distort.mean()` 및 `loss_total += w_distort * loss_dist` 경로다.

근거:
- depth supervision: `src/stage2/loss/data_fitting.py:48-50`, `src/stage2/train.py:661-666`.
- depth distortion: `src/stage2/renderer.py:66,91`, `src/stage2/train.py:682-683`.
- C001 config: `w_depth: 0.03`, `w_distort: 0.0`.

## 2. 항별 대조표

| 항 | D4 실제 가중/설정 | 2DGS 기본/평가 기준 | 배수 차이 | 적용 코드 경로 | 역할·예상 영향 |
|---|---:|---:|---:|---|---|
| Photo (`pho`) | `w_photo=1.0`, `photo_lam=0.2` | `lambda_dssim=0.2` | 동형 | `src/stage2/loss/data_fitting.py:41-45`, `src/stage2/train.py:658-659` | RGB 재현 기본항. D4의 기준 스칼라. |
| Depth distortion (`λ_d`) | `w_distort=0.0` | 공식 평가 recipe: DTU `--lambda_dist 1000`; TnT print recipe `100/10`. 현재 upstream arg default는 `0.0`. | 0x 대 1000/100 기준 | `src/stage2/train.py:491,682-683`; upstream `train.py:77-85` | 2DGS 표면 집중/플로터 억제 핵심항. D4에서는 비활성이라 이 축의 억제력은 없다. |
| `dep0.03` | `w_depth=0.03`, `depth_warmup=5000`, `depth_schedule=ramp`, `depth_ramp_steps=5000` | 원 2DGS에는 외부 MVS depth L1 없음 | N/A | `src/stage2/loss/data_fitting.py:48-50`, `src/stage2/train.py:661-666` | MVS depth map에 rendered depth를 약하게 고정. distortion이 아니라 noisy MVS supervision. |
| External normal (`nrm-off`) | `w_normal=0.0`, normal map은 load | 원 2DGS 외부 normal map supervision 없음 | N/A | `src/stage2/loss/data_fitting.py:53-69`, `src/stage2/train.py:670-675` | MVS normal prior는 실제 gradient 0. 로그상 normal maps 428/428 존재하지만 weight 0. |
| Normal consistency (`nc`) | `w_nc=0.05` | `lambda_normal=0.05` | 1x | `src/stage2/loss/data_fitting.py:84-97`, `src/stage2/train.py:679-680` | rendered normal vs depth-derived normal. D4는 2DGS 값 유지, 단 2DGS는 iter>7000 게이트이고 D4 코드는 상수 적용. |
| Semantic CE (`sem`) | `w_sem=0.1`, `sem_detach_geometry=false` | 원 2DGS 없음 | added | `src/stage2/loss/data_fitting.py:72-81`, `src/stage2/renderer.py:97-151`, `src/stage2/train.py:723-729` | GS semantic logits와 기하가 결합됨. 20k-30k weighted share 약 1.9-2.3%. |
| Structure normal-align (`na`) | `w_structure=1.0`, `w_structure_na=0.08`, hard gate `it>=15000` | 원 2DGS 없음 | added | `src/stage2/loss/structure.py:45-54`, `src/stage2/train.py:803-839` | 그룹 대표 법선 정렬. 20k-30k weighted share 약 0.10-0.14%로 사실상 미소. |
| Structure co-planarity (`cp`) | `w_structure=1.0`, `w_structure_cp=0.01`, hard gate `it>=15000` | 원 2DGS 없음 | added | `src/stage2/loss/structure.py:50-54`, `src/stage2/train.py:803-839` | 그룹 평면으로 중심을 당김. 20k-30k weighted share 약 7.4-22.2%, seed/replicate별 변동 큼. |
| Mutual | `w_mutual=0.0` | 원 2DGS 없음 | off | `src/stage2/loss/mutual.py`, `src/stage2/train.py:734-801` | D4/C001에서는 비활성. |
| SH | `sh_degree=3`, `sh_up_every=1000` | `sh_degree=3`, 1000 iter마다 상승 | 동형 | `src/stage2/model.py:63-65,149-152`, `src/stage2/train.py:611-612,874-876` | 시점 의존 색이 남아 있어 appearance 오차 흡수 여지는 존재. |
| Densification/prune | `grow_grad2d=0.001`, `refine_stop_iter=20000`, `refine_every=200`, `prune_opa=0.005`, `reset_every=3000`, `seed_protect=true` | upstream: `densify_grad_threshold=0.0002`, `densify_until_iter=15000`, `densification_interval=100`, `opacity_cull=0.05`, reset 3000, `percent_dense=0.01` | grow threshold 5x 높음; prune opacity 0.1x; stop 1.33x 늦음; interval 2x | `src/stage2/densification.py:61-84,87-124`, `src/stage2/train.py:446-463` | 성장은 더 보수적이나 더 오래 지속, opacity prune 문턱은 낮고 seed는 prune 보호. 플로터/잔점 양상에 직접 영향 가능. |
| Readout | `readout(gssem; semantic-TSDF[minobs3, voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)` | 원 2DGS mesh: bounded Open3D TSDF, DTU script `voxel_size=0.004`, `sdf_trunc=0.016`, `depth_trunc=3.0`; unbounded는 mesh_res 1024 + adaptive truncation | 직접 배수 비교 부적절 | `phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py:25-43,111-180`, `_mob_prep_las_gssem.py:54-166`; upstream `render.py`, `utils/mesh_utils.py` | D4는 mesh가 아니라 semantic point cloud + Roofer. voxel은 5 cm로 원 2DGS bounded mesh보다 거칠지만, minobs3/alpha/SOR/semantic/Roofer가 추가 필터와 분할을 만든다. |

## 3. 실제 기여 share (기존 TB scalar, 20k-30k)

가중 share는 기존 TensorBoard scalar를 읽어 `w_i * raw_loss_i`로 재계산했다. 새 학습 없음.

| run | photo | depth | nc | sem | na | cp |
|---|---:|---:|---:|---:|---:|---:|
| sparse r1 | 44.52 | 37.96 | 2.65 | 2.06 | 0.14 | 12.68 |
| sparse r2 | 48.68 | 38.79 | 2.80 | 2.26 | 0.10 | 7.38 |
| dense r1 | 44.53 | 38.29 | 2.64 | 2.12 | 0.12 | 12.31 |
| dense r2 | 46.14 | 38.94 | 2.70 | 2.15 | 0.11 | 9.96 |
| acmp r1 | 39.17 | 34.29 | 2.39 | 1.86 | 0.13 | 22.16 |
| acmp r2 | 42.89 | 34.49 | 2.50 | 2.00 | 0.11 | 18.01 |

관찰:
- `na0.08`은 실제 활성은 되지만 share가 0.10-0.14%로 미소하다.
- `cp0.01`은 실제 활성이고 share 7.4-22.2%다. acmp에서 가장 크다.
- `depth0.03`은 ramp 이후 34.3-38.9%로 큰 축이다.
- `distortion`과 external normal은 config상 0이라 share 0이다.

## 4. 스케줄과 로그 확인

학습 로그 6개 모두 다음을 기록한다.

```text
[prior] depth maps on 428/428 frames, normal maps on 428/428 (w_depth=0.03 sched=ramp@5000+5000; w_normal=0.0 sched=ramp@5000+5000)
```

즉 depth map은 전 프레임에서 실제 로드됐고, depth는 5000부터 5000 step 선형 ramp로 켜졌다. normal map도 존재하지만 `w_normal=0.0`이라 gradient는 없다.

Structure는 코드상 `it >= structure_warmup`에서 hard gate로 켜지고, C001 config는 `structure_warmup=15000`, `structure_regroup_every=1000`, `structure_grouping=g2`, `voxel_size=2.0`, `merge_n_cos=0.92`, `merge_d_tol=0.5`, `min_group=30`이다. `warm15k(cp 게이트)`라는 표현은 구현상 cp만 별도 게이트가 아니라 `L_structure` 전체(na+cp) hard gate다.

## 5. 2DGS upstream 대비 diff 요약

비교 원본: official `hbb1/2d-gaussian-splatting` main `335ad612f2e783a4e57b9cbc4d1e167bd599fc98`. README는 regularization 인자로 `--lambda_normal`, `--lambda_distortion`, `--depth_ratio`를 안내하고, 코드 `arguments/__init__.py`는 현재 기본 `lambda_dist=0.0`, `lambda_normal=0.05`를 둔다. 공식 DTU 평가 스크립트는 `--lambda_dist 1000`과 bounded mesh `voxel_size=0.004`, `sdf_trunc=0.016`, `depth_trunc=3.0`을 사용한다.

우리 코드의 주요 변경/추가:

| 축 | 2DGS 원본 | D4/C001 코드 |
|---|---|---|
| renderer | official diff-surfel-rasterization wrapper | `gsplat.rasterization_2dgs` wrapper (`src/stage2/renderer.py`) |
| photometric | L1 + DSSIM | 동일 구조, config `photo_lam=0.2` |
| depth distortion | `lambda_dist * rend_dist.mean()`, 평가 recipe에서 nonzero | 동일한 dist map 경로는 있으나 `w_distort=0.0` |
| normal consistency | `lambda_normal=0.05`, iter>7000 | `w_nc=0.05`, 상수 |
| external depth/normal | 없음 | MVS depth L1 추가(`w_depth=0.03`), MVS normal 항은 존재하나 D4 off |
| semantic | 없음 | CE + semantic rasterization, `sem_detach_geometry=false` |
| structure | 없음 | g2 grouping + `na/cp` 구조항 |
| densification | official GaussianModel `densify_and_prune` | gsplat `DefaultStrategy`, seed-protect override |
| readout | Open3D TSDF mesh / unbounded marching cubes | median-depth voxel consensus point cloud + GS semantic LAS + Roofer |

## 6. Readout 파라미터 대조

D4/C001 readout은 `readout_fingerprints.csv` 기준으로 6런 모두 동일하다.

| 항 | D4/C001 | 2DGS 원본 |
|---|---|---|
| surface extraction | rendered median depth backprojection, alpha > 0.5, `med < 500` | rendered depth TSDF mesh integration |
| fusion unit | voxel key consensus, `voxel=0.05 m` | bounded mesh default/script `voxel_size=0.004-0.006 m`; unbounded `mesh_res=1024` |
| observation filter | `min_obs=3` voxel views + SOR | Open3D TSDF weights; explicit min-observation gate 없음 |
| truncation | 점군 consensus라 TSDF truncation 없음 | bounded `sdf_trunc=5*voxel` default 또는 DTU `0.016`; unbounded adaptive truncation |
| semantic | GS logits majority vote per voxel, `BG/Roof/Wall/Terrain` | 없음 |
| building handoff | Roof/Wall -> LAS class 6, Terrain/synth ground -> class 2, Roofer | mesh output 직접 |

관찰: D4 readout은 원 2DGS mesh보다 해상도는 거칠고, minobs/alpha/SOR 때문에 관측 필터는 더 엄격하다. 대신 semantic LAS + Roofer라는 별도 구조화 단계가 추가되어, 원 2DGS mesh extraction과 동일한 readout이 아니다.

## 7. 라우팅 관찰

데이터가 말하는 핵심은 다음이다.

1. **D4에서 2DGS depth-distortion은 비활성(`w_distort=0`)이다.** 따라서 플로터/표면집중 문제의 1순위 후보로 `w_distort` 복원 또는 scene-scale 정규화된 distortion 재도입을 ②에서 정량 확인할 가치가 있다.
2. **`dep0.03`은 distortion 대체물이 아니라 MVS depth L1 supervision이다.** 이 항은 20k-30k 구간 share가 34.3-38.9%로 커서, 깊이 타깃 노이즈/평판화와의 연결을 별도 축으로 봐야 한다.
3. **`nc0.05`는 유지됐지만 2DGS의 hard warmup과 달리 상수 적용이다.** 값은 같지만 스케줄은 다르다.
4. **`na`는 거의 무력, `cp`는 실제 발화한다.** `na` share는 0.1%대, `cp`는 7-22%다.
5. **SH degree 3, seed-protect, 느슨한 opacity prune, 긴 densification stop, semantic readout**은 모두 플로터/평판/readout 문제의 후보로 ②에 넘긴다.

판정은 하지 않는다. 관찰상 distortion은 "유지"가 아니라 "부재/비활성"이므로, 복원/정규화는 후보이고 확증은 플로터 정량 ②에서 해야 한다.

## 8. 근거

- 사전등록서 §3.1: `사전등록서_본비교실험E5·기준레시피_v1_20260706.md`.
- C001 학습 지문: `phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv`, `readout_fingerprints.csv`, `versions.txt`.
- D4 config: `configs/tum_mob/gs_d4_{sparse,dense,acmp}.yaml`; C001 config: `configs/tum_mob/e5_pilot/gs_e5_C001_*.yaml`.
- 손실 코드: `src/stage2/train.py`, `src/stage2/loss/data_fitting.py`, `src/stage2/loss/structure.py`, `src/stage2/renderer.py`.
- D4 이전 감사: `docs/experiments/w_d_loss_audit/reports/W_D_loss_audit.md`, `docs/experiments/w_d4/reports/W_D4_precheck.md`, `docs/experiments/w_d4/reports/W_D4.md`, `docs/recipe_registry.md`.
- 2DGS: arXiv 2403.17888, official repo `https://github.com/hbb1/2d-gaussian-splatting`.
