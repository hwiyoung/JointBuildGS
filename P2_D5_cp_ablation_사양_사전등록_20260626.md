# P2-D5 cp 절제(ablation) 사양서 · 사전등록 (pre-registration) — cp가 진짜 품질 레버인가

> **2026-06-26 · branch `feature/p2-prior-full` · 판정=사람(김휘영) · 골대이동 금지.**
> 이 문서는 **본런 전에 잠그는 사전등록**이다. §5 판정기준은 결과를 보기 전에 확정한다(LOCKED).
> 작성=에이전트(관찰·산출까지). §5 **확정·판정=김휘영**. 결과는 본 문서가 아니라 `docs/experiments/joint-optimization/w_d5/reports/W_D5.md`에 쓰고 §5에 대입한다.
> 학습 ~4h/arm · 학습 **승인=김휘영**. 관찰만, 판정 금지. 기반: [[W_D4]](docs/experiments/joint-optimization/w_d4/reports/W_D4.md) · [[W_D4_precheck]](docs/experiments/joint-optimization/w_d4/reports/W_D4_precheck.md).

## §0 한 줄
D4(정확도 win: 평지붕 RMS→LiDAR 수렴·곡면 19→13면)는 **cp(평면화)만 바꾼 게 아니라 de-noise(depth↓·normal=0)도 동시에** 바꿨다.
W_D4 §1은 "펴짐 동력은 cp 압력이 아니라 depth-denoise"라고 관찰했다 — 그러나 **갈렸다**. D5는 **de-noise를 D4로 고정**하고 **cp만 변주**(끔/공정/세게/일찍)해
D4 win이 **cp 때문인지 de-noise 때문인지** 가른다. **품질을 GS 방법으로**(Roofer 튜닝 아님).

## §1 가설
- **H1 (cp=레버)**: cp 평면화 압력이 지붕 펴짐의 (적어도 부분) 동력이다. 그렇다면 cp를 **끄면(D5a)** D4보다 나빠지고,
  **세게/일찍(D5b/D5c)** 하면 복합동(다지붕) 과분할이 더 줄되 곡면은 과-평탄화되지 않는다.
- **H2 (de-noise=전부)**: D4 win은 **전적으로** depth-denoise+normal제거가 노이즈 MVS 핀을 푼 결과이고 cp는 거의 무관하다.
  그렇다면 cp를 **꺼도(D5a) D4와 같고**, 세게/일찍 해도 **추가 이득이 없거나(무효) 곡면만 망가뜨린다(과-평탄)**.
- **반증(곡면 위험, D4에서 이미 식별)**: cp는 큰 곡면을 한 평면으로 과병합할 수 있다(4906969 gid1828 15,008점 RMS 4.13 m,
  [[W_D4_precheck]] §1라). cp를 **세게(D5b)** 하면 곡면 4906969가 **파국적 과-평탄**(RMS→ref 급증·면수 붕괴)될 수 있다 → 정량+정성 분리 관찰.

## §2 변경 = config-only cp 변주 (엔진 무변경; de-noise·나머지 = D4 고정)
> D5는 **D4의 손실 균형을 그대로 두고**(photo 1.0·depth 0.03·normal 0·nc 0.05·sem 0.1·na 0.08) **cp 한 항만** 변주한다.
> cp 유효 스칼라 = `w_structure`(=1.0) × `w_structure_cp`. D5c만 게이트(`structure_warmup`)를 앞당긴다. 그 외 전부 MUST-EQ=D4.

| arm | 의미 | `w_structure_cp` | `structure_warmup` | cp share(예측, §3①) | config |
|---|---|---:|---:|---:|---|
| **D5a** | cp **끔** | **0.0** | 15000 | **0%** (photo 45%) | `gs_d5a_{dense,acmp}` |
| **D4** (=공정, **재사용**) | cp 공정 | 0.01 | 15000 | 31% | `gs_d4_{dense,acmp}` (재학습 X) |
| **D5c** | cp **일찍** | 0.01 | **5000** | 31% (크기=D4, 게이트만 조기) | `gs_d5c_{dense,acmp}` |
| **D5b** | cp **세게** | **0.03** | 15000 | **~58%** | `gs_d5b_{dense,acmp}` |

- **신규 학습 = 6 arm**(D5a/b/c × dense·acmp). **D4(공정 0.01·15000)는 재사용**(미재학습) — 기존 `gs_d4_*` ckpt/eval 그대로.
- **MUST-EQ(D4와 동일)**: `data_root=data_geoidfix` · `init_pointcloud`(dense=seed_dense, acmp=seed_acmp) · `seed_protect` ·
  `sem_detach_geometry=false` · `w_photo 1.0`·`w_depth 0.03`·`w_normal 0`·`w_nc 0.05`·`w_sem 0.1`·`w_structure 1.0`·`w_structure_na 0.08` ·
  depth ramp@5000+5000 · `structure_grouping g2`·`structure_voxel_size 2.0`·`merge_n_cos 0.92`·`merge_d_tol 0.5`·`min_group 30`·`regroup 1000` ·
  densification(D dense) · `max_iter 30000` · read-out=gssem · Roofer 고정(epsilon 0.3·min-points 15·complexity 0.888, 건물별 튜닝 금지).
- **D4 대비 diff 검증**(완료): 각 D5 config는 D4 베이스 대비 **오직** `w_structure_cp`(a/b) 또는 `structure_warmup`(c) + `out_dir`만 다름(line-diff 확인).
- **delta 기록**: `results/tum_transfer/mob/gs_d5{a,b,c}_{dense,acmp}/versions.txt`(run_d5.sh 스탬프).

## §3 사전점검 (본런 전 — 표 먼저)
### ① 미는 힘 균형 — **분석적(완료)**. cp share가 의도대로(끔 0%·공정 31%·세게 ~57%)인가.
유효 스칼라 × D-run raw-mean[20-30k]([[W_D4_precheck]] §3 LOCKED) → 가중 기여 share(`d5_share_table.py`):

|       arm |  photo | depth | normal |   nc |  sem |   cp |  na | maxterm |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| D5a (cp OFF)  | 44.8 | 24.3 | 0.0 | 3.1 | 27.7 | **0.0** | 0.1 | photo 45% |
| D4/D5c (FAIR) | 30.7 | 16.6 | 0.0 | 2.1 | 19.0 | **31.5** | 0.0 | cp 31% |
| D5b (cp HARD) | 18.9 | 10.2 | 0.0 | 1.3 | 11.7 | **57.9** | 0.0 | cp 58% |

→ cp share **0% → 31% → 58%**, 의도대로. D5a는 cp 그래디언트 0(photo가 자연스레 최상위 45% = 비정상 감독지배 아님; na 0.08은 게이트 후 유지).
D5c는 cp 크기=D4(31%), 게이트만 조기(5000). D5b는 cp 58%(3×) = 최강 평면화 → 곡면 과-평탄 watch. **사전점검 ① 충족**.

### ②③ — **경험적(소수 step, GPU)**. ⚠ **게이트 주의**.
- **D5a / D5b** (`structure_warmup=15000`): 게이트 전(<15000) loss는 cp 가중과 무관하게 **D4와 바이트 동일**(structure 블록 미실행). →
  D4의 기존 사전점검(`gs_d4_dense_precheck`, 6000 step 안정·photo 무열화·PSNR 17.6@5k)이 **D5a/b 게이트 전 안정을 그대로 커버**. cp 발화는 게이트 후(15k) = **본런 모니터**(D4와 동형).
- **D5c** (`structure_warmup=5000`): cp가 **5000에서 발화**(유일하게 sub-15k 신규 거동). `gs_d5c_dense_precheck`(7000 step)로 직접 관찰:
  - **② 안정/photo** — 조기 cp(아직 말랑한 기하 위, depth 램프 시작과 동시)가 NaN/발산 없이 photo 무열화인가(D4 precheck 대비).
  - **③ cp 원시 추이** — `loss/structure_cp`가 5000 게이트 직후 떨어지기 시작(cp 조기 발화)하나.
  - (세게=D5b의 cp 원시 깊이는 게이트 15k 이후 = 본런에서만 관찰, D4와 동일 게이트.)
- **판단**: 표 보고 막히면 멈추고 보고. 이상 없으면(승인=김휘영) 본런.

## §4 학습·평가 (백그라운드, 2-GPU 3쌍) — `run_d5.sh`
6 arm = 3 순차쌍(dense host-GPU1 | acmp host-GPU0): D5a → D5b → D5c, 각 ~4h, 총 ~13h 벽시계.
→ semantic TSDF(min-obs 3·voxel 0.05) → GS-의미 분류(gssem) → Roofer(고정) → val3dity → facet/RMS/solid.
idempotent(완료 산출 skip → resume 안전). **모니터**: cp 압력이 후반 약해지나·발산 조짐 기록.

## §5 판정 기준 (사전등록 — **🔒 LOCKED 2026-06-26, 결과 보기 전 확정**, 판정=김휘영)
> **LOCKED**: 본 §5는 본런 결과를 보기 전 잠갔다. 이후 수정 금지(골대이동 금지). 판정만 김휘영.
> 측정(§6) = **target-only 면수** 기준. 비교축 = D5a/b/c **vs D4 vs v6 vs LiDAR vs ref**(동일 하니스, 기존값 재사용).
> baseline(공정 cp) = D4: 평지붕 4906972 면 3=ref·RMS→LiDAR 수렴(2.41=2.41)·곡면 4906969 13면(RMS 0.76)·생성 7/8·valid-solid dense 2/acmp 3.

**핵심 측정**: 복합동(다지붕) **42364663·42364659 과분할** · 곡면 **4906969**(목표 LiDAR 5) · **RMS→ref**(과-평탄 watch) · **valid-solid** · **생성 7/8**.

- **cp = (품질) 레버** — 아래 **전부**:
  1. **세게/일찍 과분할↓**: D5b(세게)·D5c(일찍)에서 복합동 과분할(42364663·42364659)이 **D4보다↓**(cp가 면을 더 정리).
  2. **과-평탄 아님**: 그 과분할↓가 곡면 4906969을 **파국적 과-평탄**(RMS→ref 급증·면수 붕괴)시키지 않음 — 곡선 보존.
  3. **끔 < D4**: D5a(cp 끔)이 **D4보다 나쁨**(과분할↑ 또는 RMS 악화) — 즉 cp 제거가 품질을 잃음.
- **de-noise = 전부 (cp 무관)** — 아래:
  1. **끔 ≈ D4**: D5a(cp 끔)이 D4와 **사실상 동일**(과분할·RMS 노이즈 폭 내) — cp가 한 일이 없음.
  2. **세게/일찍 무효 또는 과-평탄**: D5b/D5c가 D4 대비 **추가 이득 없음(무효)** 이거나 곡면 **과-평탄**(곡선 뭉갬).
- **혼합/부분**: 위 두 패턴이 갈리면(예 cp가 평지붕엔 무관하나 복합동 과분할만 줄임, 또는 일찍은 도움/세게는 과-평탄) →
  **cp는 조건부 레버** → 결과를 §5 표에 그대로 적고 김휘영이 경계 판정.

## §6 평가 (target-only 면수 + RMS + 정성)
하니스 = `tum_mob_eval --classifier gssem`(→`eval_d5_gssem.json`) · `tum_mob_ref_rms --arms gs_d5{a,b,c}_{dense,acmp}`(→`ref_rms_d5.csv`).
면수 = **target-only**(per-building Roofer cityjson roof facet 수; eval 합산 메트릭은 클립-이웃 오염 = [[W_D4]] §7 주의).
- **A 과분할(주)**: 복합동 {42364663,42364659}·곡면 {4906969}·평지붕 {4906972,4907182}·제어 {4908023} 면수 → ref/LiDAR 대비.
- **B RMS→ref**(m): arm별 meanRMS + 곡면/평지붕 per-building. **과-평탄 watch**: D5b 곡면 RMS 급증 여부.
- **C valid-solid**: 회복 8동 + 정본 11동 위상 유효 solid (D4 dense 2/acmp 3 대비).
- **D 생성**: assembled/8 · 회복동 밀도 (D4 7/8 유지 여부).
- **E 정성**: 곡면 4906969·복합동 42364663 · 평지붕 4906972에 [D5a|D5c|D4|D5b|LiDAR|ref] × [점군|조립모델 면별색] —
  cp 강도 사다리(끔→공정→일찍→세게)로 **실제 펴짐 vs 과-평탄**을 눈으로 분리.
- 비교 baseline 재사용: `eval_d4_gssem.json`(D4)·`eval_prior_full_gssem.json`(D)·`eval_v6_protect.json`(v6)·`eval_v6_raw.json`(raw/LiDAR)·`baselines.json`(ref)·`ref_rms_{d4,D,v6,raw}.csv`.

## §7 미결·주의 (open items — 김휘영 확인)
- **D5a 게이트 후 ≠ D4**: D5a는 게이트(15k) 후 structure가 **na만**(cp=0) 돌아 D4(na+0.01cp)와 미세히 다름. 게이트 **전**(<15k)은 D4와 동일. = 의도(cp 끔).
- **D5c 게이트·depth 램프 동시(5000)**: cp 조기발화가 depth 램프 시작과 겹침 — "cp 일찍"의 의도된 조건. ② precheck로 안정 확인.
- **세게(D5b) cp 원시 깊이**: 게이트 15k → short precheck 직접관찰 불가(D4와 동일 게이트). 본런 모니터로 이관.
- **메트릭 주의**: eval 합산 over-seg = 클립-이웃 오염 → **target-only** 사용([[W_D4]] §7). D 보고 합산 수치와 직접 비교 시 유의.
- **산출물**: `docs/experiments/joint-optimization/w_d5/reports/W_D5.md`(과분할/RMS/solid/생성 표 + 정성 그림 + 본 §5 대입). 한 커밋 "D5". results/ data는 gitignore(재생성).
