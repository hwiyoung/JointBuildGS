# E5 C001 corrected-S1 재점검

> 관찰 자료. 학습 0 원칙을 따랐고, 예외는 Step 0에서 허용된 `final_prune_opa=0` 폴백 3 arm뿐이다. 정본 S0/S1/corrected-S1은 수정하지 않았고 판정 0이다.

## Step 0 · 스냅샷 재고

- corrected-S1 기존 run에는 `final.pt`, `step_010000.pt`, `step_020000.pt`만 있었고 final prune 직전 상태는 없었다.
- 그래서 발주문 폴백을 사용했다: corrected-S1과 동일 config/seed(2001), 변경은 `final_prune_opa=0` 및 `ckpt_every=5000`뿐.
- snapshot inventory: `docs/e5_c001_corrected_s1_recheck_snapshot_inventory.csv`.

## Step 1 · 문턱 스윕

- thresholded ckpt: `docs/e5_c001_corrected_s1_recheck_ckpt_thresholds.csv`.
- sweep table: `docs/e5_c001_corrected_s1_recheck_prune_sweep.csv`.
- best threshold for voxel02 follow-up by pre-registered fallback ranking: `keepall`.
- A-clean 후보 존재: `False`. 단 collapse-view depth는 역사적 기준과 같은 방식으로 재현하지 못해 gate 밖 보조 proxy로 분리했다.
- 짝 그림: `docs/figs/e5_c001_corrected_s1_recheck/prune_sweep_dense_gate.png`, `docs/figs/e5_c001_corrected_s1_recheck/prune_sweep_threshold_arm_coverage.png`.

| threshold | has_lod22 | valid_assembled | median_ref_rms_m | mean_coverage_post_sor | normal6_raw_anchor_count | normal6_median_delta_vs_s1_m | a_clean_candidate_dense_primary |
|---|---|---|---|---|---|---|---|
| keepall | 7 | 6 | 4.6850 | 0.1291 | 3 | 0.2605 | false |
| opa001 | 7 | 6 | 4.6850 | 0.1291 | 2 | -0.0147 | false |
| opa002 | 7 | 5 | 4.6850 | 0.1291 | 3 | 0.5401 | false |
| opa005 | 7 | 5 | 4.6850 | 0.1291 | 3 | -0.0091 | false |

### Step 1-B · 20k 중간 스냅샷

최종 prune 전후만이 아니라 학습 중간에도 표면이 있었는지 보기 위해 20k 스냅샷을 같은 base readout으로 처리했다.

| arm | has_lod22 | valid_assembled | median_ref_rms_m | mean_coverage_post_sor | run_name |
|---|---|---|---|---|---|
| sparse | 12 | 10 | 5.9274 | 0.1570 | gs_e5_C001_corrected_s1_preprune_mid20k_sparse_r1 |
| dense | 8 | 5 | 3.5187 | 0.1196 | gs_e5_C001_corrected_s1_preprune_mid20k_dense_r1 |
| acmp | 12 | 6 | 5.0305 | 0.1779 | gs_e5_C001_corrected_s1_preprune_mid20k_acmp_r1 |

## Step 2 · H2 물질 추적

- Gaussian roofcrop CSV: `docs/e5_c001_corrected_s1_recheck_gaussian_roofcrop.csv`.
- 짝 그림: `docs/figs/e5_c001_corrected_s1_recheck/gaussian_roofcrop_dense_4907202.png`, `docs/figs/e5_c001_corrected_s1_recheck/gaussian_roofcrop_dense_4908168.png`, `docs/figs/e5_c001_corrected_s1_recheck/gaussian_roofcrop_dense_8568392.png`.

| condition | building_id | n_gaussians_in_footprint | z_p50 | z_std | opacity_p50 | opacity_lt_005_abs | opacity_lt_0050_count | axis_ratio_gt10_count |
|---|---|---|---|---|---|---|---|---|
| s1 | DEBY_LOD2_4907184 | 23969 | 581.6657 | 6.0782 | 0.0355 | 9036 | 12400 | 3582 |
| s1 | DEBY_LOD2_4907202 | 1188 | 567.0390 | 13.1149 | 0.0855 | 477 | 564 | 75 |
| s1 | DEBY_LOD2_4908168 | 102 | 566.2634 | 1.8722 | 0.4706 | 35 | 39 | 4 |
| s1 | DEBY_LOD2_8568392 | 30 | 565.4143 | 9.5213 | 0.0037 | 20 | 22 | 0 |
| corrected | DEBY_LOD2_4907184 | 7396 | 582.0406 | 5.2734 | 0.9804 | 0 | 0 | 1440 |
| corrected | DEBY_LOD2_4907202 | 10 | 576.4144 | 1.1172 | 0.8972 | 0 | 0 | 0 |
| corrected | DEBY_LOD2_4908168 | 31 | 657.9312 | 25.9949 | 0.0949 | 0 | 0 | 0 |
| corrected | DEBY_LOD2_8568392 | 0 |  |  |  | 0 | 0 | 0 |
| preprune_keepall | DEBY_LOD2_4907184 | 7494 | 581.9096 | 2.3861 | 0.9761 | 25 | 301 | 1534 |
| preprune_keepall | DEBY_LOD2_4907202 | 5 | 575.6246 | 0.3235 | 0.5699 | 0 | 0 | 0 |
| preprune_keepall | DEBY_LOD2_4908168 | 0 |  |  |  | 0 | 0 | 0 |
| preprune_keepall | DEBY_LOD2_8568392 | 0 |  |  |  | 0 | 0 | 0 |
| preprune_opa005 | DEBY_LOD2_4907184 | 7193 | 581.8392 | 2.3871 | 0.9808 | 0 | 0 | 1426 |
| preprune_opa005 | DEBY_LOD2_4907202 | 5 | 575.6246 | 0.3235 | 0.5699 | 0 | 0 | 0 |
| preprune_opa005 | DEBY_LOD2_4908168 | 0 |  |  |  | 0 | 0 | 0 |
| preprune_opa005 | DEBY_LOD2_8568392 | 0 |  |  |  | 0 | 0 | 0 |

## Step 3 · H3 val3dity 유형

- val3dity/status type CSV: `docs/e5_c001_corrected_s1_recheck_val3dity_types.csv`.
- 짝 그림: `docs/figs/e5_c001_corrected_s1_recheck/val3dity_type_breakdown.png`.

| condition | arm | run_name | building_id | has_lod22 | val3dity_valid | status_reason | val3dity_error_codes |
|---|---|---|---|---|---|---|---|
| recheck | acmp | gs_e5_C001_corrected_s1_preprune_keepall_acmp_r1 | DEBY_LOD2_4907184 | True | False | val3dity_invalid | 405 |
| recheck | acmp | gs_e5_C001_corrected_s1_preprune_mid20k_acmp_r1 | DEBY_LOD2_4907184 | True | False | val3dity_invalid | 405 |
| recheck | acmp | gs_e5_C001_corrected_s1_preprune_opa001_acmp_r1 | DEBY_LOD2_4907184 | True | False | val3dity_invalid | 405 |
| recheck | acmp | gs_e5_C001_corrected_s1_preprune_opa002_acmp_r1 | DEBY_LOD2_4907184 | True | False | val3dity_invalid | 405 |

## Step 4 · 결손 메움

- render/depth proxy CSV: `docs/e5_c001_corrected_s1_recheck_floater_render.csv`.
- 짝 그림: `docs/figs/e5_c001_corrected_s1_recheck/floater_render_depth_proxy.png`, `docs/figs/e5_c001_corrected_s1_recheck/rend_dist_x2_scale_test.png`.
- 주의: 이 값은 검수 문서의 S0 9~13 m / S1 20~44 m collapse-view metric을 동일 방식으로 재현한 것이 아니라, 같은 스크립트에서 새로 뽑은 render proxy다.

| condition | view_idx | scale_variant | depth_p50 | depth_p95 | rend_dist_mean_alpha02 | note |
|---|---|---|---|---|---|---|
| s1_dense | 0 |  | 55.1767 | 65.5928 | 1.5037 | render proxy; not the historical collapse-view metric |
| s1_dense | 10 |  | 58.9742 | 64.5164 | 1.0941 | render proxy; not the historical collapse-view metric |
| s1_dense | 30 |  | 59.7783 | 76.5093 | 0.4625 | render proxy; not the historical collapse-view metric |
| s1_dense | 60 |  | 60.4746 | 76.4397 | 0.5393 | render proxy; not the historical collapse-view metric |
| corrected_dense | 0 |  | 53.8192 | 59.7489 | 0.2773 | render proxy; not the historical collapse-view metric |
| corrected_dense | 10 |  | 58.9970 | 64.0583 | 0.4128 | render proxy; not the historical collapse-view metric |
| corrected_dense | 30 |  | 57.4007 | 75.8037 | 0.2031 | render proxy; not the historical collapse-view metric |
| corrected_dense | 60 |  | 57.8930 | 76.2889 | 0.1891 | render proxy; not the historical collapse-view metric |
| preprune_keepall_dense | 0 |  | 53.8112 | 59.8606 | 0.2439 | render proxy; not the historical collapse-view metric |
| preprune_keepall_dense | 10 |  | 59.0021 | 64.4962 | 0.2470 | render proxy; not the historical collapse-view metric |
| preprune_keepall_dense | 30 |  | 57.5840 | 76.1505 | 0.1731 | render proxy; not the historical collapse-view metric |
| preprune_keepall_dense | 60 |  | 58.1965 | 76.3835 | 0.1821 | render proxy; not the historical collapse-view metric |
| rend_dist_unit_test | 10 | original | 59.0021 |  | 0.2470 | x2 camera+Gaussian scale test for rend_dist units |
| rend_dist_unit_test | 10 | x2_centers_camera | 118.3162 |  | 0.3983 | x2 camera+Gaussian scale test for rend_dist units |
| rend_dist_unit_test | 10 | x2_centers_camera_scales | 118.0042 |  | 0.4941 | x2 camera+Gaussian scale test for rend_dist units |

## Step 5 · 사다리 선행 재료

- mono-normal stats CSV: `docs/e5_c001_corrected_s1_recheck_mono_normal_stats.csv`.
- 로컬 repo에는 Omnidata/DSINE 실행 경로와 model weight가 없어 Step 5-B는 실행하지 않았다. COLMAP PatchMatch normal은 존재하지만 mono-normal이 아니므로 대체하지 않았다.
| building_id | status | reason | note |
|---|---|---|---|
| DEBY_LOD2_4907199 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |
| DEBY_LOD2_8568391 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |
| DEBY_LOD2_8568392 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |
| DEBY_LOD2_60098 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |
| DEBY_LOD2_4907186 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |
| DEBY_LOD2_4907188 | not_run | no local Omnidata/DSINE/mono-normal runtime or model weights found in repo | COLMAP PatchMatch normal maps exist but are texture-dependent MVS normals, not the requested mono-normal prior |

## voxel02 천장 보조

- voxel02은 best threshold `keepall` dense arm에만 추가 실행했다.
- dense voxel02 has_lod22=3, valid_assembled=1, median RMS=1.8079.

## 이슈·지문

| part | severity | message | path |
|---|---|---|---|
| Step5-B | warn | mono-normal precheck not run; local 2D foundation normal runtime absent |  |

| arm | gpu_device | elapsed_min | seed | final_prune_opa | ckpt_sha256 |
|---|---|---|---|---|---|
| sparse | 0 | 66.1 | 2001 | 0.0 | 3b234bdc71e22b0d19955c1c6bb5ef32643c2fe01beff62b631bb75576d2df09 |
| dense | 1 | 65.5 | 2001 | 0.0 | 9550c772c4f6f41215cfcbb4b968dd15adc29de90b9ceafcd62590beb31ab5c4 |
| acmp | 1 | 66.8 | 2001 | 0.0 | 2db00671dace8c842b48fe884baaef82273e62ff7836166806a3f50936a65201 |

- config diff: `docs/e5_c001_corrected_s1_recheck_config_diff.csv`.
- train fingerprints: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1_recheck/train_fingerprints.csv`.
- readout fingerprints: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1_recheck/readout_fingerprints.csv`.
- versions: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1_recheck/versions.txt`.
- snapshots: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1_recheck/snapshots`.
- 재확인: 학습 0 원칙(예외=Step 0 폴백뿐), 정본 미변경, 판정 0.
