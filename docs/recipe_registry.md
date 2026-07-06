# recipe_registry - 레시피 대장 감사

> 작업: `recipe-audit`, branch `feat/p2-structure-learn`.
> 범위: 읽기와 대조만 수행. GPU 사용 0, 재구성/재학습 없음, 판정 및 canonical 채택 없음.
> 좌표계 표기: 지오 산출물 EPSG:25832, OPF/카메라 경로 EPSG:32632.
> 정본 별명: 이 문서에서는 부여하지 않는다. "사실상 정본"은 아래 §4의 검증 가설명일 뿐 채택 문장이 아니다.

## 0. 읽은 근거와 누락

요청 파일 중 현재 checkout에서 직접 확인된 파일은 `CLAUDE.md`이다. 다음 요청 원문 파일명은 `rg --files`와 `find . -maxdepth 3`에서 발견되지 않았다.

| 요청 파일 | 현재 상태 | 대체로 읽은 근거 |
|---|---|---|
| `세션핸드오프_모집단잠금·기준문서_20260702.md` §1·§2 | 없음 | `docs/SESSION_HANDOFF.md`, `docs/population_verify.md`, `docs/W_report_evidence.md` |
| `P2_실험기록_20260629.md` | 없음 | `docs/W_phaseB_structure.md`, `docs/W_observability_inventory.md`, `docs/W_observability_test.md`, `docs/W_D12_metric_final.md` |
| `원격발주_투영fix·LS정합·재게이트·재계산체인_레시피감사_20260702.md` Task B | 없음 | `docs/projection_geoid_rootcause.md`, `docs/projection_datum_fix.md`, `configs/projection_datum.json`, `runs/20260702_*`, `runs/20260703_*` |

실제 대조에 사용한 주 근거는 다음이다.

| 묶음 | 파일 |
|---|---|
| repo 규칙 | `CLAUDE.md` |
| D/D4/D5 사전등록 | `P2_D4_사양서_사전등록_20260625.md`, `P2_D5_cp_ablation_사양_사전등록_20260626.md` |
| 실험 기록 | `docs/W_generation_8way.md`, `docs/W_opacity_diag.md`, `docs/W_D_prior_full.md`, `docs/W_D4.md`, `docs/W_D5.md`, `docs/W_D6_prior_provenance.md`, `docs/W_D6_overseg_diag.md`, `docs/W_observability_inventory.md`, `docs/W_observability_test.md`, `docs/W_D12_metric_final.md`, `docs/W_results_consolidation.md`, `docs/W_report_evidence.md`, `docs/SESSION_HANDOFF.md` |
| config | `configs/tum_mob/*.yaml`, `configs/projection_datum.json` |
| versions | `results/tum_transfer/mob/*/versions.txt`, `runs/20260702_*/*`, `runs/20260703_*/*` |
| 코드 위치 | `src/stage2/*`, `phases/p2-gsjso/scripts/*`, `scripts/stage2/*` |

## 1. 레시피 대장

성분 문자열은 `GS(...)` 안에 학습 손실과 주요 read-out/seed 차이를 압축해 적었다. `pho`, `sem`, `dep`, `nrm`, `nc`, `str`, `cp`, `mvc`는 아래 §1.1의 코드 위치 표와 대응한다.

| 레시피 | 성분 문자열 | 손실 항·가중·설정 | 코드 위치 | 도입 근거 | 사용 런·versions 증거 | 상태 |
|---|---|---|---|---|---|---|
| raw DIM/ACMP/LiDAR | `RAW(dim/acmp/lidar; no-GS; smrf; ellip-unified)` | GS 학습 없음. raw arm은 ELLIPSOIDAL UTM로 통일, acmp/lidar는 `+48 geoid` 이력. | `phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py`, `tum_mob_eval.py`, `tum_mob_ref_rms.py` | v6 8-way 및 LiDAR/ref 대조 | `results/tum_transfer/mob/raw/versions.txt`, `analysis_pack_v6/versions.txt` | 활성 대조 |
| v6 seed sparse | `GS(v6-seed-sparse; pho1·sem0.1·nc0.05·str0.1[g1-default;na1;cp1]; dep/nrm-off; smrf)` | `w_depth=0`, `w_normal=0`, `w_nc=0.05`, `w_sem=0.1`, `sem_detach_geometry=false`, `w_structure=0.1`, config에 `structure_grouping` 없음 - code default `g1`. | `configs/tum_mob/gs_seed_sparse.yaml`; `src/stage2/train.py:main`; `src/stage2/loss/structure.py:l_structure` | P2 make-or-break v6, sparse arm | `results/tum_transfer/mob/gs_seed_sparse/versions.txt` | 활성 기록 대조 |
| v6 seed dense/acmp | `GS(v6-seed-{dense,acmp}; seed=dim/acmp; pho1·sem0.1·nc0.05·str0.1[g1-default;na1;cp1]; dep/nrm-off; smrf)` | sparse와 같고 `init_pointcloud=seed_dense.ply` 또는 `seed_acmp.ply`. dense seed는 `-604`, acmp seed는 `-556` 이력. | `configs/tum_mob/gs_seed_dense.yaml`, `gs_seed_acmp.yaml`; `tum_mob_seed_prep.sh`; `seed_prep_dense.json`, `seed_prep_acmp.json` | v6 8-way의 GS seed arm | `results/tum_transfer/mob/gs_seed_{dense,acmp}/versions.txt`, `docs/W_generation_8way.md` | 활성 기록 대조 |
| C seed-protect | `GS(C-protect; v6-seed-{dense,acmp}+seed_protect; pho1·sem0.1·nc0.05·str0.1[g1-default;na1;cp1]; dep/nrm-off; smrf)` | v6 dense/acmp와 byte-동일 계열에 `seed_protect=true`만 추가. densification은 v6 dense 유지. | `configs/tum_mob/gs_seed_{dense,acmp}_protect.yaml`; seed 보호 엔진은 `src/stage2/train.py:main`의 `seed_protect` 경로 | v6 prune confound 제거 | `results/tum_transfer/mob/gs_seed_{dense,acmp}_protect/versions.txt`, `docs/W_opacity_diag.md` | 활성 기록 대조 |
| C2 opacity 진단 | `C2(C-protect ckpt; alpha-gate bypass; no-train)` | 새 학습 레시피가 아니라 C ckpt의 Gaussian 위치를 opacity 무시로 추출. | `phases/p2-gsjso/scripts/c2_dump_means.py`; `tum_mob_eval.py`; `tum_mob_ref_rms.py` | in-scope 0점 원인이 opacity인지 확인 | `docs/W_opacity_diag.md` | 진단 전용, 레시피 라벨 폐기 권장 |
| depth_release_range | `GS(depth-release-range; seed_sem_band=ground-1..ground+30; pho1·sem0.1·nc0.05; sem_detach=false; dep/nrm-off; str-off)` | `seed_semantic=true`, `w_structure=0`, `w_mutual=0`, `w_depth=0`, `w_normal=0`, `seed_cfg.bands_file=seed_bands_range.json`. | `configs/tum_mob/depth_release_range.yaml`; `src/stage2/semantic_seed.py:build_semantic_seeds`; `src/stage2/renderer.py:render_semantic` | P2 impl 2 "깊이 연결" honest-range | `results/tum_transfer/mob/depth_release_range/versions.txt` | 과거 실험 arm |
| depth_release_oracle | `GS(depth-release-oracle; seed_sem_band=roof-1..roof+1; pho1·sem0.1·nc0.05; sem_detach=false; dep/nrm-off; str-off)` | range와 같고 band만 oracle ceiling. | `configs/tum_mob/depth_release_oracle.yaml`; `src/stage2/semantic_seed.py:build_semantic_seeds` | P2 impl 2의 ceiling 대조 | `results/tum_transfer/mob/depth_release_oracle/versions.txt` | 과거 실험 arm |
| D prior_full | `GS(D; seed-protect; pho1·sem0.1·nc0.05·dep0.1·nrm0.15·str0.08[g2;na1;cp1]; gssem)` | `w_depth=0.1`, `w_normal=0.15`, depth/normal warmup+ramp, `structure_grouping=g2`, `w_structure=0.08`, read-out는 `gssem`. | `configs/tum_mob/gs_prior_full_{dense,acmp}.yaml`; `src/stage2/train.py:main`; `src/stage2/loss/data_fitting.py:l_depth/l_normal/l_sem/l_nc`; `src/stage2/loss/structure.py:l_structure` | 3 레버 ON: depth/normal + G2 + GS-의미 read-out | `results/tum_transfer/mob/gs_prior_full_{dense,acmp}/versions.txt`, `docs/W_D_prior_full.md` | 비교기준, D4 이전 |
| D4 corrected | `GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01;warm15k]; gssem)` | `w_depth=0.03`, `w_normal=0`, `w_structure=1.0`, `w_structure_na=0.08`, `w_structure_cp=0.01`, `structure_warmup=15000`, `structure_grouping=g2`. | `configs/tum_mob/gs_d4_{dense,acmp}.yaml`; `run_d4.sh`; `src/stage2/train.py:main`; `tum_mob_tsdf_extract.py`; `_mob_prep_las_gssem.py` | D의 normal 과가중/깊이 noisy pinning 완화, cp 공정값 | `results/tum_transfer/mob/gs_d4_{dense,acmp}/versions.txt`, `docs/W_D4.md`, `P2_D4_사양서_사전등록_20260625.md` | 후속 평가 기반. 정본 별명 미부여 |
| D5a | `GS(D5a; D4 except cp0; warm15k; gssem)` | D4와 동일, `w_structure_cp=0.0`. | `configs/tum_mob/gs_d5a_{dense,acmp}.yaml`; `run_d5.sh` | cp ablation off | `results/tum_transfer/mob/gs_d5a_{dense,acmp}/versions.txt`, `docs/W_D5.md` | ablation 완료 |
| D5b | `GS(D5b; D4 except cp0.03; warm15k; gssem)` | D4와 동일, `w_structure_cp=0.03`. | `configs/tum_mob/gs_d5b_{dense,acmp}.yaml`; `run_d5.sh` | cp ablation hard | `results/tum_transfer/mob/gs_d5b_{dense,acmp}/versions.txt`, `docs/W_D5.md` | ablation 완료 |
| D5c | `GS(D5c; D4 except cp0.01; warm5k; gssem)` | D4와 동일, `w_structure_cp=0.01`, `structure_warmup=5000`. | `configs/tum_mob/gs_d5c_{dense,acmp}.yaml`; `run_d5.sh` | cp ablation early | `results/tum_transfer/mob/gs_d5c_{dense,acmp}/versions.txt`, `docs/W_D5.md` | ablation 완료 |
| B1 / D10 | `GS(B1; D4 + mvc0.5[nrm0.5;k2;angle40;baseline2;warm7k+ramp5k]; gssem)` | D4와 동일하고 `w_mvc=0.5`, `mvc_warmup=7000`, `mvc_ramp_steps=5000`, `mvc_neighbor_k=2`, `mvc_max_angle_deg=40`, `mvc_min_baseline=2`, `mvc_w_normal=0.5`. | `configs/tum_mob/gs_b1_{dense,acmp}.yaml`; `src/stage2/loss/multiview.py:l_multiview_consistency`; `src/stage2/train.py:_build_mvc_neighbors/main`; `run_b1.sh` | Phase B `L_mvc` 추가 실험 | `results/tum_transfer/mob/gs_b1_{dense,acmp}/versions.txt`, `docs/W_phaseB_structure.md`, `docs/W_observability_test.md` | Phase B 실험 완료. 판정 문구는 본 대장에서 채택하지 않음 |
| gssem read-out | `readout(gssem; semantic-TSDF[minobs3,voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)` | 학습 레시피가 아니라 GS 의미 logits를 TSDF/점군 class로 변환한 read-out. D/D4/D5/B1 기록에서 기준 분류로 사용. | `phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py`; `_mob_prep_las_gssem.py`; `tum_mob_eval.py --classifier gssem` | SMRF가 지붕을 ground로 먹는 문제를 분리/대체 | `P2_D4_사양서_사전등록_20260625.md`, `P2_D5_cp_ablation_사양_사전등록_20260626.md`, `docs/W_gssem_requal.md` | read-out 이름. 학습 레시피 별명 아님 |

### 1.1 손실 항 코드 위치

| 약어 | 항 | 코드 위치(file:function) | 주 사용 레시피 |
|---|---|---|---|
| `pho` | RGB photometric loss, `(1-lam)L1 + lam(1-SSIM)`, `photo_lam=0.2` | `src/stage2/loss/data_fitting.py:l_photo`, `src/stage2/loss/data_fitting.py:ssim`, `src/stage2/train.py:main` | 전 GS 레시피 |
| `sem` | per-pixel semantic CE, `ignore_index=0` | `src/stage2/loss/data_fitting.py:l_sem`, `src/stage2/renderer.py:render_semantic`, `src/stage2/train.py:main` | v6/C/D/D4/D5/B1, depth_release |
| `dep` | MVS depth masked L1 | `src/stage2/loss/data_fitting.py:l_depth`, `src/stage2/train.py:main` | D, D4, D5, B1 |
| `nrm` | MVS normal sign-invariant cosine loss | `src/stage2/loss/data_fitting.py:l_normal`, `src/stage2/train.py:main` | D only on; D4/D5/B1 off |
| `nc` | render normal vs depth-derived normal consistency | `src/stage2/loss/data_fitting.py:l_nc`, `src/stage2/train.py:main` | v6/C/D/D4/D5/B1 |
| `mutual` | intra-primitive semantic/geometry domain rule | `src/stage2/loss/mutual.py:l_mutual`, `src/stage2/train.py:main` | 현재 대장 대상 런은 대부분 `w_mutual=0` |
| `str.na/cp` | inter-primitive normal-align/coplanar | `src/stage2/loss/structure.py:l_structure`, `src/stage2/train.py:main` | v6/C/D/D4/D5/B1 |
| `mvc` | multi-view depth/normal consistency | `src/stage2/loss/multiview.py:l_multiview_consistency`, `src/stage2/train.py:_build_mvc_neighbors`, `src/stage2/train.py:main` | B1/D10 |
| seed semantic | semantic voxel carving | `src/stage2/semantic_seed.py:build_semantic_seeds`, `src/stage2/train.py:main` | depth_release_range/oracle |

## 2. 옛 이름 매핑

| 옛 이름 | 현재 성분 문자열 매핑 | 라벨 폐기·주의 이력 |
|---|---|---|
| `v5` | 현재 checkout에 `v5` config/run 이름은 없다. `docs/W_generation_8way.md`와 `analysis_pack_v6/versions.txt` 기준으로는 `v6`부터 추적 가능. | 매핑 불가 라벨. 숫자 인용 시 config/run명을 직접 써야 한다. |
| `v6` | `GS(v6-seed-{sparse,dense,acmp}; pho1·sem0.1·nc0.05·str0.1[g1-default]; dep/nrm-off; smrf)` 및 raw 8-way. | `W_D6_overseg_diag.md`가 v6 과분할 진단의 분류가 `gssem`이 아니라 `smrf`였음을 정정. v6 라벨만으로 read-out을 생략하면 안 된다. |
| `C` | `GS(C-protect; v6-seed-{dense,acmp}+seed_protect; ...)` | seed opacity prune confound 제거용. 새 densification이 아니라 v6 dense 설정 유지. |
| `C2` | `C2(C-protect ckpt; alpha-gate bypass; no-train)` | 진단명. 학습 레시피로 취급하지 않는다. |
| `D` | `GS(D; seed-protect; pho1·sem0.1·nc0.05·dep0.1·nrm0.15·str0.08[g2;na1;cp1]; gssem)` | D4 이전 비교기준. 기록상 `D-gssem`과 `D-smrf` read-out을 구분해야 한다. |
| `D4` | `GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01]; gssem)` | 후속 평가의 기반으로 반복 사용됨. 이 문서에서는 정본 별명 미부여. |
| `D5` | `D5a/D5b/D5c` cp ablation 3 arm + D4 fair 재사용. | `D5` 단독은 ablation 묶음명이다. `a/b/c` 또는 D4 fair를 같이 적어야 한다. |
| `D6` | provenance/shape/overseg/textureless audit 묶음. 대체로 `gs_d4_dense`, `raw_lidar`, `raw_dense` 등 기존 산출 재사용. | 새 학습 레시피 아님. `W_D6_prior_provenance.md`는 LoD2 z 직접 유입 없음과 `sem_detach_geometry=false`의 기하 결합을 정정. |
| `D7` | 현 checkout의 `docs/*.md`와 versions에서 독립 학습 레시피 라벨로 확인되지 않음. | 미확인 라벨. canonical 사전등록서에서 이름 회수 또는 근거 파일 지정 필요. |
| `D8` | 현 checkout의 `docs/*.md`와 versions에서 독립 학습 레시피 라벨로 확인되지 않음. | 미확인 라벨. canonical 사전등록서에서 이름 회수 또는 근거 파일 지정 필요. |
| `D9` | `docs/W_observability_inventory.md` 기준 `overseg-faithfulness`. D4/D5 output과 기존 점군을 분석. | 새 ckpt 없음. `face_support()` 분석 자산명으로만 유지. |
| `D10` | `B1`, 즉 `GS(B1; D4 + mvc0.5; gssem)` | 새 학습 arm. `run_b1.sh`가 `gssem -> smrf` 순차 실행으로 디스크 덮어쓰기 이슈를 만들 수 있어 requal 이력을 같이 적어야 한다. |
| `D11` | `complexity-survey`. D4/B1 및 기존 분석 산출을 사용. | 새 학습 레시피 아님. 관측가능성/복잡도 분석 숫자 출처로만 유지. |
| `D12` | `observability-test` 및 `metric-final`. 기존 `gs_d4`/`gs_b1` ckpt를 footprint box로 확장 추출해 `gssem -> Roofer` 평가. | 새 학습 없음. D4/B1 기반 평가 숫자이며, 기록의 판정 문구는 본 대장에서 채택하지 않는다. |
| `gssem` | `readout(gssem; semantic-TSDF -> GS-의미 분류 -> Roofer)` | 학습 레시피가 아니라 read-out/분류 채널. `gssem 정본`이라는 기록 표현은 있으나 이 문서는 정본 채택을 하지 않는다. |

## 3. 기록과 코드·versions 불일치 목록

| 항목 | 기록 쪽 | 코드/versions 쪽 | 감사 메모 |
|---|---|---|---|
| 요청 원문 파일 | 세 파일명을 직접 읽으라는 지시 | 현재 checkout에 없음 | 이 문서는 disk에 남은 `SESSION_HANDOFF.md`, `W_*`, config, versions로만 대조했다. |
| D4 초기 가중치 | `P2_D4_사양서`에 초기 D4가 photo 5.6/nc 2.1/sem 0.92로 과정규화됐다고 기록 | corrected D4 versions/config는 `w_photo=1`, `w_nc=0.05`, `w_sem=0.1`, `w_depth=0.03`, `w_normal=0`, `w_structure=1`, `na=0.08`, `cp=0.01` | 문서가 자체적으로 철회/정정한 항목. 숫자 인용 시 corrected D4만 D4 성분 문자열로 사용. |
| D prior structure 수치 | 일부 기록 맥락에서 D를 `w_structure=0.3` 또는 cp share 86%로 언급한 흔적 | `gs_prior_full_*` config/versions는 `w_structure=0.08`, `w_structure_na=1`, `w_structure_cp=1` | `P2_D4_사양서` §7도 D reported run을 `w_structure=0.08`로 정정. |
| v6 structure grouping | v6 기록은 `L_structure`를 켰다고만 적는 경우가 많음 | `gs_seed_*` config에는 `structure_grouping` 키가 없고 `src/stage2/train.py:main` default는 `g1` | D/D4의 `g2`와 다르다. v6 성분 문자열에 `g1-default`를 명시해야 한다. |
| v6 과분할 read-out | 초기 `W3_overseg_diagnosis.md`는 v6 overseg 진단을 일반 v6 결과처럼 사용 | `W_D6_overseg_diag.md`가 코드/mtime 근거로 v6 진단 입력이 `smrf`였다고 정정 | v6의 `gssem` 기준 과분할 숫자로 재사용 금지. |
| D/D4 read-out 덮어쓰기 | D-수트 eval은 한 arm에서 `gssem`과 `smrf`를 순차 실행 | `W_results_consolidation.md`는 per-building LAS/cityjson/val3dity가 마지막 `smrf`로 덮일 수 있음을 기록 | `eval_*_gssem.json`과 현 디스크 cityjson/las의 read-out 기준을 분리해야 한다. |
| D6 LoD2 prior provenance | 과거 shape-audit 맥락에서 LoD2 band/seed prior가 들어갔다는 가정 | `W_D6_prior_provenance.md`와 code는 D/D4에 `seed_semantic`이 없고 LoD2 z/면 직접 유입이 없음을 확인 | 단 `sem_detach_geometry=false`로 LoD2 raycast class projection의 기하 결합은 있음. |
| D12/B1 판정 문구 | `SESSION_HANDOFF.md`와 `W_observability_test.md`에 B1에 대한 강한 판정 표현 존재 | 본 작업 지시는 판정 금지 | 이 대장은 B1의 성분, ckpt, 사용 숫자 출처만 기록한다. |
| 숫자 출처 혼재 | `W_report_evidence.md`가 generation 8-way, accuracy, overseg/formal metric의 GS 설정이 서로 다르다고 경고 | 디스크상 v6 seed, D4 dense, raw arms, D12 eval이 각각 다른 versions/config를 가짐 | "어느 숫자냐" 질문에는 반드시 레시피와 read-out을 같이 답해야 한다. |
| geoid 값 전환 | A0/A1/A2는 48.0 또는 LS 48.125535를 사용한 흔적 | A3a/A3b와 현재 `configs/projection_datum.json` 기본은 45.700 | projection 숫자와 population aux 숫자는 run 날짜별 geoid flag가 필요하다. |
| datum_tie_overlay config context | `runs/20260703_datum_tie_overlay/versions.txt`는 config context 48.125535를 남김 | overlay script는 좌/우 명시값 `45.7`/`48.126`을 렌더 | context와 패널별 explicit zeta를 구분해야 한다. |
| numeric grep false positive | `45.7`, `48.0`, `604`가 CSV/OBJ/좌표값에도 다수 출현 | datum 선언은 config, versions, script constant, comments를 기준으로 분류해야 함 | `docs/population_aux_v4.csv` 같은 표의 숫자값은 geoid 사용처로 세지 않는다. |

## 4. "사실상 정본 = D4" 가설 검증

가설: "사실상 정본 = D4 레시피이고, `gs_d4` ckpt가 D7~D12 전부의 기반이다."

### 4.1 체크포인트와 해시

| arm | ckpt | size bytes | sha256 |
|---|---:|---:|---|
| D4 dense | `results/tum_transfer/mob/gs_d4_dense/ckpt/final.pt` | 833492764 | `a4332ea2a51c5dcc95087b60619cb8d62a7a5bf3878172ae8ac8a370546d1214` |
| D4 acmp | `results/tum_transfer/mob/gs_d4_acmp/ckpt/final.pt` | 843910492 | `03dfd9dd568ce708e8659b38c30915402f5d83d554f67201e92c17b3a1b9be05` |
| B1 dense | `results/tum_transfer/mob/gs_b1_dense/ckpt/final.pt` | 837764508 | `df166b5e9d46c617e5c4f39d344b2b3a4932aa11bbc4b8c97818eb09abcec6df` |
| B1 acmp | `results/tum_transfer/mob/gs_b1_acmp/ckpt/final.pt` | 848971292 | `236c58cd6c07e32fe0e8addd4143e3dd5d2014b2eaddd3ff010ecef5768e19bf` |
| D5a dense | `results/tum_transfer/mob/gs_d5a_dense/ckpt/final.pt` | 835670172 | `8abf308cb3439e3b58ab361209d372964c4108a3536ddc2271db0be14b3fa290` |
| D5a acmp | `results/tum_transfer/mob/gs_d5a_acmp/ckpt/final.pt` | 844979676 | `2b3db3e23f3bd164f618bda88ac7a0c9aa4cd0423b6d63ad85f0cf43ec224fc5` |
| D5b dense | `results/tum_transfer/mob/gs_d5b_dense/ckpt/final.pt` | 841443356 | `9d72b2883ac83fbe706ca9299c9e5a69e4413cde4d92609249b0298397978a57` |
| D5b acmp | `results/tum_transfer/mob/gs_d5b_acmp/ckpt/final.pt` | 845792860 | `a8bb12c4d9f07e6ec450b4e36b7948c31aac0bddc506033248c68b89ca3120bf` |
| D5c dense | `results/tum_transfer/mob/gs_d5c_dense/ckpt/final.pt` | 835279580 | `6beb8b8022fb793c5c4ad28327ec96b6616926b74912ecce8be8501c9331cf64` |
| D5c acmp | `results/tum_transfer/mob/gs_d5c_acmp/ckpt/final.pt` | 842898460 | `0d866e2e9850d92b5cf6b319df405f98b0862842f31fb1ed8fe65e7cdf893972` |
| D dense | `results/tum_transfer/mob/gs_prior_full_dense/ckpt/final.pt` | 958355740 | `4e86a7dc10ffe522b562c2aef8dd0571e2795ac613c3342ca7a16412286f202b` |
| D acmp | `results/tum_transfer/mob/gs_prior_full_acmp/ckpt/final.pt` | 1009220060 | `05ee0b95316ae2f4912d7b9ab5dd9ac2ee346dc6bd9cdab6c848bb60527ba787` |

### 4.2 기반성 대조

| 후속 라벨/문서 | D4 기반성 | 근거 |
|---|---|---|
| D5 | 부분 반박 | D5a/b/c는 D4 설정 계열의 cp ablation이지만 새 ckpt가 존재한다. D4 fair arm은 재사용. |
| D6 provenance/shape/overseg | 지지 | `W_D6_*`는 `gs_d4_dense`, `raw_lidar`, `raw_dense` 등 기존 산출을 읽는다. 새 ckpt 없음. |
| D9 overseg-faithfulness | 지지 | `W_observability_inventory.md`가 D9를 면-받침 진단으로 표시하고 기존 D4/B1/ALS 자산을 사용. |
| D10/B1 | 부분 지지 | B1은 D4 config에 `L_mvc`를 추가한 새 학습 arm이다. D4가 대조축이지만 B1 ckpt는 별도 해시. |
| D11 complexity-survey | 지지 | 기존 D4/B1 평가 산출을 분석. 새 학습 없음. |
| D12 observability-test/metric-final | 지지 | `gs_d4`/`gs_b1` final.pt를 footprint clip -> `gssem` -> Roofer로 확대 평가. 새 학습 없음. |
| D7/D8 | 확인 불가 | 현 checkout에 독립 라벨/versions 근거가 없다. |
| v6 generation 8-way | 반박 | v6 숫자는 `gs_seed_*`, raw, LiDAR에서 나온다. D4 기반이 아니다. |
| projection/datum/aux 숫자 | 반박 | 투영 게이트와 모집단 보조표는 image-projection datum config와 관측기하 스크립트 숫자다. D4 ckpt 기반이 아니다. |

관찰: D4는 D6, D9, D11, D12의 큰 축에서 평가 기반으로 반복 사용되고, B1/D10의 비교 기준이자 config 기반이다. 그러나 D5는 별도 ablation ckpt가 있고, v6 8-way와 raw/LiDAR 대조, projection/datum/aux 숫자는 D4 기반이 아니다. 따라서 "D4가 D7~D12 전부의 기반"은 D9~D12 범위에서는 대체로 지지되지만, D7/D8 라벨이 현 checkout에서 확인되지 않아 전부 검증은 불완전하다. 이 문장은 정본 채택이 아니라 기반성 관찰이다.

## 5. geoid 사용처 전수 grep 요약

검색 패턴: `-604`, `-556`, `48.0`, `48.125`, `45.7`, `geoid`, `orthometric_geoid_m`, `input_datum`. 대형 산출물, CSV 수치값, OBJ 좌표값은 datum 선언이 아닌 false positive로 분리했다.

### 5.1 image-projection 경로

| 파일/런 | 값·상수 | 경로 구분 | 메모 |
|---|---|---|---|
| `configs/projection_datum.json` | `orthometric_geoid_m=45.7`; `zeta_hat_m=48.125535` 기록 | image-projection config | 현재 기본은 공식 45.700. 3D seed/training 경로는 이 파일 밖이라고 note가 명시. |
| `phases/p2-gsjso/scripts/projection_datum.py` | orthometric 입력이면 `+orthometric_geoid_m`, ellipsoidal 입력이면 기존 경로 유지 | image-projection shared util | `apply_vertical_datum`, `base_to_canonical_points`, `as_ellipsoidal_points`. |
| `projection_datum_unitcheck.py` | 45.7/48.0/A1 zeta 교체 가능값 목록 | image-projection unit check | A0 영향 목록과 unit check 기록. |
| `evidence_cards.py`, `evidence_cards_v2.py` | `base_to_canonical_points(... input_datum, geoid_m)` | image-projection overlay/cards | orthometric roof/ALS/footprint 투영 호출부. |
| `population_aux_v3.py`, `aux_v4a.py`, `aux_v4b.py` | v3는 projection util, v4a/v4b는 `45.700` 명시 | image-projection observation geometry | v4a/v4b run versions도 `45.700000`. |
| `projection_zeta_ls.py` | command `--zeta0 48.0`; fit output `48.125535` | image-projection LS | A1 참고값. |
| `projection_gate_v2.py` | `projection_geoid_m()` | image-projection gate | A2 versions는 48.125535. |
| `datum_tie.py` | GCG 45.7, effective zeta 45.76, old `GEOID=48.0` snippet | datum tie measurement | raw dense only 사용, raw_acmp/raw_lidar 제외. |
| `datum_tie_overlay.py` | left `45.7`, right `48.126` explicit | visualization overlay | versions context는 48.125535이나 패널 값은 explicit. |
| `ztest.py`, `zmultiview.py`, `zfix_visual.py`, `zresolve.py` | diagnostic `ΔZ=0` vs `+geoid` | old diagnostic | pre-fix/visual 진단 잔존. |

### 5.2 3D seed·라벨·밴드 경로

| 파일/런 | 값·상수 | 경로 구분 | 메모 |
|---|---|---|---|
| `results/tum_transfer/mob/*/versions.txt` | `GS-LOCAL=EPSG:25832-[690953,5336071,604]`; dim `-604`; acmp `-556` | 3D train/seed | GS-local convention. projection config와 별도. |
| `results/tum_transfer/mob/raw/versions.txt` | `ellipsoidal UTM (GS-LOCAL+[690953,5336071,604]); acmp/lidar +48 geoid` | raw 대조 | raw arm 통일 이력. |
| `tum_mob_seed_prep.sh` | comment: dim `-604`, acmp `-558.3` | 3D seed prep | E5 신규 canonical부터 전환. |
| `seed_prep_dense.json` | matrix z `-604` | 3D seed prep | DIM seed. |
| `seed_prep_acmp.json` | matrix z `-558.3` | 3D seed prep | E5 신규 canonical ACMP seed. |
| `src/stage2/semantic_seed.py` | `z_local=Hoehe_orthometric+geoid-604`; labels rendered with `shift_z=604-45.7=558.3` | semantic seed/label | geoid raster는 provenance only. |
| `configs/tum_mob/seed_semantic.yaml` | `shift_z=604-45.7=558.3`, geoid path | semantic seed/label | E5 신규 canonical label 이력. |
| `configs/tum_mob/depth_release_{range,oracle}.yaml` | `world_offset=[690953,5336071,604]`, geoid raster path | seed band | bands file가 per-building z band 제공. |
| `results/tum_transfer/mob/depth_release_{range,oracle}/versions.txt` | labels `shift_z=556`, `ground_local=H_ortho+geoid(48)-604=H_ortho-556` | seed band | P2 impl 2 versions. |
| `seed_depth_bands.py` | `--geoid default=45.7`, `--shift-z` 사용 | seed band generation | E5 신규 canonical band 경로. |
| `seed_material_audit.py` | `--geoid-val default=45.7`; ref height local 변환 | seed audit | E5 신규 canonical seed material 감사 경로. |
| `scripts/stage2/tum_tsdf_extract.py`, `tum_qc_*` | `SHIFT=[690953,5336071,604]` | 3D extract/QC | image-projection config 미사용. |
| `overseg_faithfulness.py` | `GEOID=48.165` comment | analysis readability | ellip-ortho readability용으로 보이며 projection config와 별도. |

### 5.3 run별 geoid flag

| run/config | image-projection flag | 3D seed/train flag | 메모 |
|---|---|---|---|
| `runs/20260702_A0_projection_fix` | `orthometric_geoid_m=48.000000` | 해당 없음 | A0 projection fix 당시 기본값. |
| `runs/20260702_A1_zeta_ls` | command `zeta0=48.0`; fit/config `48.125535` | 해당 없음 | LS 참고값. |
| `runs/20260702_A2_projection_gate_v2` | `orthometric_geoid_m=48.125535` | 해당 없음 | A2 측정 불능/게이트 v2 이력. |
| `runs/20260703_datum_tie_v3` | GCG 45.7, effective 45.76, old 48.0 snippet | raw dense versions `GS-LOCAL+[...604]` | datum tie measurement. |
| `runs/20260703_datum_tie_overlay` | left 45.7, right 48.126; config context 48.125535 | 해당 없음 | 순수 렌더 시각 대조. |
| `runs/20260703_aux_v4a` | `orthometric_geoid_m=45.700000`, `geoid_m=45.700000` | 3D/씨드 `-556` 건드리지 않음 | population aux v4a. |
| `runs/20260703_aux_v4b` | `orthometric_geoid_m=45.700000`, `geoid_m=45.700000` | 3D/씨드 `-556` 건드리지 않음 | lowtex/cards v4b. |
| `gs_seed_*`, `gs_seed_*_protect` | 해당 없음 | `GS-LOCAL -604`, dim `-604`, acmp `-556` | v6/C 계열. |
| `gs_prior_full_*`, `gs_d4_*`, `gs_d5*`, `gs_b1_*` | 해당 없음 | `GS-LOCAL -604`, acmp `-556`; `data_geoidfix` | D/D4/D5/B1 계열. |
| `depth_release_*` | 해당 없음 | labels `shift_z=556`, geoid 48 band logic | P2 impl 2. |

## canonical 사전등록서에 넘길 미결정 항 목록

1. `정본` 별명을 부여할 레시피를 하나로 지정할지, 또는 별명을 쓰지 않고 `config/run/versions` 조합만 canonical 식별자로 쓸지.
2. D7/D8 라벨을 회수할지, 현 checkout 밖 근거 파일을 추가해 매핑할지.
3. D4를 "D9~D12 평가 기반"으로만 등록할지, D5/B1처럼 별도 ckpt가 있는 후속 arm까지 포함해 계열로 등록할지.
4. v6 수치 인용 시 `smrf`와 `gssem` read-out 구분을 필수 필드로 둘지.
5. D/D4/D5/B1 per-building 산출물의 `gssem -> smrf` 덮어쓰기 이력을 canonical 표에서 어떤 수준까지 노출할지.
6. projection/datum/aux 숫자는 GS 레시피 대장과 별도 registry로 분리할지, 본 registry의 geoid flag 필드에 계속 포함할지.
7. 3D seed·라벨·밴드 경로의 `-556`/`48.0` 관례는 E5 신규 canonical부터 `-558.3`/`45.7` 세트로 전환했다. 과거 run versions는 이력으로 보존한다.
8. `gssem`을 read-out 이름으로만 고정할지, 문서에 남은 `gssem 정본` 표현을 일괄 치환할지.
9. `v5`처럼 현 checkout에서 근거가 없는 옛 라벨을 사전등록서에서 폐기 라벨로 명시할지.
