# W_E5_C001 렌더·플로터 점검

## 시작 전 확인

- 브랜치/HEAD: `exp/3b-surface-restore` / `9286a83306b25dedcd81ea3c9fb582178bb49b4b`.
- C001 재고: checkpoint 3개, 기존 RGB render 180개, MVS depth map 856개, semantic mask 428개, readout NPZ 3개.
- D4 상수 재사용: `w_distort=0`, `prune_opa=0.005`, `seed_protect=true`, `sh_degree=3`, `w_depth=0.03`, `readout=minobs3/voxel0.05/alpha0.5/SOR`.
- 수행 범위: 체크포인트 추론 + 기존 산출 재측정. 학습 0, 정식 재점군화 0, 재조립 0, 판정 0.
- 좌표: footprint/readout coverage는 EPSG:25832, GS-local은 `local + [690953, 5336071, 604]`.

## 한계

- C001 18동·2씨드·체크포인트 추론만의 진단이다. "지금 왜 무너지나"의 관찰이며, "고치면 되나"는 ③ 재학습 ablation 대상이다.
- SH 낮춤과 readout 전 backprojection은 진단 프록시다. 원 readout 파이프라인과 동일한 전체뷰 TSDF가 아니라 test split 샘플 + target 대표 view 렌더에서 산출했다.
- LoD2 참조 depth map 파일은 재고에서 확인되지 않았다. B의 깊이 비교는 MVS/ACMP depth valid pixel 대비로 축소했다.
- 영상 텍스처는 기존 C001 video-layer 프록시를 사용했고, 가림은 정밀 분리하지 않았다.
- MVS/ACMP depth와 ACMP 성공은 목표 기준선·메커니즘 단서이며 정답은 아니다.

## 산출 파일

- 표: `docs/e5_c001_render_eval_metrics.csv`, `docs/e5_c001_render_floater_metrics.csv`, `docs/e5_c001_render_depth_supervision.csv`, `docs/e5_c001_render_readout_coverage.csv`, `docs/e5_c001_render_condition_strata.csv`, `docs/e5_c001_render_cause_attribution.csv`.
- 그림: `docs/figs/e5_c001_3b_s1/render`/.
- run 기록: `phases/p2-gsjso/runs/20260708_e5_c001_3b_s1_render/versions.txt`.

## A. 렌더 품질

기존 TensorBoard final eval과 동일한 test split 앞 4뷰를 재렌더했다. SSIM은 동일 뷰에서 deterministic subsampling으로 계산했다. readout 전 coverage 프록시에는 target 대표 view 5개를 추가했다.

| run_name | sh_degree | psnr | ssim | depth_mae_m | rend_dist_mean |
| --- | --- | --- | --- | --- | --- |
| gs_e5_C001_s1_acmp_r1 | 0 | 16.7972 | 0.5507 | 6.4160 | 2.2884 |
| gs_e5_C001_s1_acmp_r1 | 1 | 17.5086 | 0.5658 | 6.4160 | 2.2884 |
| gs_e5_C001_s1_acmp_r1 | 3 | 19.7158 | 0.6100 | 6.4160 | 2.2884 |
| gs_e5_C001_s1_dense_r1 | 0 | 14.3201 | 0.4693 | 18.3856 | 2.9769 |
| gs_e5_C001_s1_dense_r1 | 1 | 14.8938 | 0.4790 | 18.3856 | 2.9769 |
| gs_e5_C001_s1_dense_r1 | 3 | 16.6794 | 0.5129 | 18.3856 | 2.9769 |
| gs_e5_C001_s1_sparse_r1 | 0 | 15.7577 | 0.5306 | 10.2982 | 4.1550 |
| gs_e5_C001_s1_sparse_r1 | 1 | 16.3019 | 0.5436 | 10.2982 | 4.1550 |
| gs_e5_C001_s1_sparse_r1 | 3 | 18.1856 | 0.5854 | 10.2982 | 4.1550 |

## B. 렌더 깊이 품질

MVS depth valid pixel에서 expected/median depth를 비교했다. LoD2 참조 depth map은 재고에 없어서 직접 비교하지 않았다.

| run_name | view_role | view_idx | image_name | psnr | ssim | depth_mae_m | depth_rmse_m | depth_pred_valid_frac_on_mvs | rend_dist_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gs_e5_C001_s1_sparse_r1 | test_eval | 9 | DJI_20241217084611_0109_D.JPG | 19.1516 | 0.5780 | 2.8385 | 9.6938 | 1.0000 | 0.5330 |
| gs_e5_C001_s1_sparse_r1 | test_eval | 19 | DJI_20241217084647_0127_D.JPG | 22.3814 | 0.6862 | 1.1074 | 6.1495 | 0.9999 | 0.5529 |
| gs_e5_C001_s1_sparse_r1 | test_eval | 29 | DJI_20241217084707_0137_D.JPG | 20.6173 | 0.6621 | 1.8451 | 7.9464 | 0.9984 | 0.5645 |
| gs_e5_C001_s1_sparse_r1 | test_eval | 39 | DJI_20241217084727_0147_D.JPG | 10.5921 | 0.4153 | 35.4020 | 40.5729 | 1.0000 | 14.9694 |
| gs_e5_C001_s1_sparse_r1 | target_case_proxy | 375 | DJI_20241217102919_0005_D.JPG | 19.1227 | 0.6986 | 5.8173 | 26.7022 | 0.9683 | 4.4826 |
| gs_e5_C001_s1_sparse_r1 | target_case_proxy | 135 | DJI_20241217095441_0023_D.JPG | 18.3778 | 0.4803 | 1.2476 | 5.2669 | 0.9928 | 1.0330 |
| gs_e5_C001_s1_sparse_r1 | target_case_proxy | 177 | DJI_20241217095607_0066_D.JPG | 23.0829 | 0.7845 | 0.5451 | 3.5418 | 0.9981 | 0.4649 |
| gs_e5_C001_s1_sparse_r1 | target_case_proxy | 54 | DJI_20241217084845_0186_D.JPG | 22.5508 | 0.6544 | 1.4725 | 6.8351 | 0.9944 | 0.6262 |
| gs_e5_C001_s1_sparse_r1 | target_case_proxy | 31 | DJI_20241217084711_0139_D.JPG | 23.1404 | 0.6760 | 2.1373 | 8.6104 | 0.9994 | 0.5761 |
| gs_e5_C001_s1_dense_r1 | test_eval | 9 | DJI_20241217084611_0109_D.JPG | 10.4023 | 0.2480 | 43.8349 | 45.0481 | 1.0000 | 2.2580 |
| gs_e5_C001_s1_dense_r1 | test_eval | 19 | DJI_20241217084647_0127_D.JPG | 22.0209 | 0.6694 | 1.1133 | 6.1503 | 0.9984 | 0.4913 |
| gs_e5_C001_s1_dense_r1 | test_eval | 29 | DJI_20241217084707_0137_D.JPG | 20.8922 | 0.6847 | 1.8366 | 7.9340 | 0.9974 | 0.4706 |
| gs_e5_C001_s1_dense_r1 | test_eval | 39 | DJI_20241217084727_0147_D.JPG | 13.4022 | 0.4497 | 26.7574 | 34.4836 | 1.0000 | 8.6879 |
| gs_e5_C001_s1_dense_r1 | target_case_proxy | 375 | DJI_20241217102919_0005_D.JPG | 18.4679 | 0.6892 | 18.9429 | 87.4583 | 0.9852 | 1.8240 |
| gs_e5_C001_s1_dense_r1 | target_case_proxy | 135 | DJI_20241217095441_0023_D.JPG | 18.5429 | 0.5293 | 1.2705 | 5.4397 | 0.9951 | 0.8668 |
| gs_e5_C001_s1_dense_r1 | target_case_proxy | 177 | DJI_20241217095607_0066_D.JPG | 23.3367 | 0.8003 | 0.5305 | 3.5226 | 0.9960 | 0.3984 |
| gs_e5_C001_s1_dense_r1 | target_case_proxy | 54 | DJI_20241217084845_0186_D.JPG | 22.8632 | 0.6829 | 1.5079 | 6.7910 | 0.9780 | 0.6708 |
| gs_e5_C001_s1_dense_r1 | target_case_proxy | 31 | DJI_20241217084711_0139_D.JPG | 23.4155 | 0.6960 | 2.1412 | 8.5895 | 0.9980 | 0.5257 |
| gs_e5_C001_s1_acmp_r1 | test_eval | 9 | DJI_20241217084611_0109_D.JPG | 19.4117 | 0.5957 | 2.8327 | 9.6962 | 1.0000 | 0.4811 |
| gs_e5_C001_s1_acmp_r1 | test_eval | 19 | DJI_20241217084647_0127_D.JPG | 22.2696 | 0.6830 | 1.1005 | 6.1597 | 0.9997 | 0.5307 |
| gs_e5_C001_s1_acmp_r1 | test_eval | 29 | DJI_20241217084707_0137_D.JPG | 14.6371 | 0.5581 | 20.5730 | 29.4944 | 0.9974 | 7.6071 |
| gs_e5_C001_s1_acmp_r1 | test_eval | 39 | DJI_20241217084727_0147_D.JPG | 22.5446 | 0.6030 | 1.1577 | 5.8315 | 0.9567 | 0.5348 |
| gs_e5_C001_s1_acmp_r1 | target_case_proxy | 375 | DJI_20241217102919_0005_D.JPG | 18.8391 | 0.7032 | 5.7748 | 26.7684 | 0.9613 | 5.5881 |
| gs_e5_C001_s1_acmp_r1 | target_case_proxy | 135 | DJI_20241217095441_0023_D.JPG | 19.6211 | 0.5563 | 1.2344 | 5.3678 | 0.9943 | 0.6345 |

## C. 플로터·퇴화 정량

off-surface는 정답 표면 거리가 아니라 arm별 seed point cloud에 대한 center-distance 프록시다.

| run_name | n_gaussians | opacity_p50 | opacity_below_prune005_frac | inplane_ratio_p95 | elongated_ratio_gt10_frac | seed_distance_p90_m | off_seed_gt1m_proxy_frac |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gs_e5_C001_s1_sparse_r1 | 3414807 | 0.0100 | 0.4085 | 47.2496 | 0.4099 | 154.0403 | 0.9545 |
| gs_e5_C001_s1_dense_r1 | 1010777 | 0.1428 | 0.2336 | 29.8976 | 0.2420 | 111.2196 | 0.6908 |
| gs_e5_C001_s1_acmp_r1 | 3100243 | 0.0077 | 0.4524 | 44.8593 | 0.3472 | 157.1634 | 0.8732 |

## D. depth 감독 커버리지

semantic roof pixel 중 COLMAP MVS depth mask가 유효한 비율이다.

| index | roof_pixels | mvs_depth_valid_roof_pixels | mvs_depth_valid_roof_frac | mvs_depth_valid_all_frac |
| --- | --- | --- | --- | --- |
| count | 427.0000 | 427.0000 | 427.0000 | 427.0000 |
| mean | 278947.9344 | 248000.7518 | 0.8721 | 0.8348 |
| std | 209362.0149 | 194669.3325 | 0.1516 | 0.1839 |
| min | 777.0000 | 0.0000 | 0.0000 | 0.0000 |
| 10% | 38863.8000 | 31887.2000 | 0.6518 | 0.5738 |
| 50% | 245100.0000 | 219260.0000 | 0.9268 | 0.9162 |
| 90% | 584235.6000 | 542611.2000 | 0.9956 | 0.9923 |
| max | 851890.0000 | 817041.0000 | 1.0000 | 0.9998 |

## E. readout 귀속

`render_depth_backproj_sample_pre_readout`는 체크포인트 샘플 렌더에서 alpha>0.5·semantic roof 픽셀을 backprojection한 프록시다. `tsdf_minobs_voxel_pre_sor`와 `tsdf_minobs_voxel_post_sor`는 기존 readout NPZ에서 재측정했다.

| source_run | stage | coverage_frac |
| --- | --- | --- |
| gs_e5_C001_s1_acmp_r1 | render_depth_backproj_sample_pre_readout | 0.6599 |
| gs_e5_C001_s1_acmp_r1 | tsdf_minobs_voxel_post_sor | 0.2741 |
| gs_e5_C001_s1_acmp_r1 | tsdf_minobs_voxel_pre_sor | 0.4560 |
| gs_e5_C001_s1_dense_r1 | render_depth_backproj_sample_pre_readout | 0.5432 |
| gs_e5_C001_s1_dense_r1 | tsdf_minobs_voxel_post_sor | 0.2378 |
| gs_e5_C001_s1_dense_r1 | tsdf_minobs_voxel_pre_sor | 0.4035 |
| gs_e5_C001_s1_sparse_r1 | render_depth_backproj_sample_pre_readout | 0.6665 |
| gs_e5_C001_s1_sparse_r1 | tsdf_minobs_voxel_post_sor | 0.2211 |
| gs_e5_C001_s1_sparse_r1 | tsdf_minobs_voxel_pre_sor | 0.3666 |

## F. SH 흡수

동일 checkpoint에서 SH degree 0/1/3을 비교했다. PSNR이 SH와 함께 오르지만 depth MAE가 같이 개선되지 않는 경우는 시점-의존 색이 geometry 오차를 흡수한 프록시로만 본다.

| run_name | sh_degree | psnr | ssim | depth_mae_m |
| --- | --- | --- | --- | --- |
| gs_e5_C001_s1_acmp_r1 | 0 | 16.7972 | 0.5507 | 6.4160 |
| gs_e5_C001_s1_acmp_r1 | 1 | 17.5086 | 0.5658 | 6.4160 |
| gs_e5_C001_s1_acmp_r1 | 3 | 19.7158 | 0.6100 | 6.4160 |
| gs_e5_C001_s1_dense_r1 | 0 | 14.3201 | 0.4693 | 18.3856 |
| gs_e5_C001_s1_dense_r1 | 1 | 14.8938 | 0.4790 | 18.3856 |
| gs_e5_C001_s1_dense_r1 | 3 | 16.6794 | 0.5129 | 18.3856 |
| gs_e5_C001_s1_sparse_r1 | 0 | 15.7577 | 0.5306 | 10.2982 |
| gs_e5_C001_s1_sparse_r1 | 1 | 16.3019 | 0.5436 | 10.2982 |
| gs_e5_C001_s1_sparse_r1 | 3 | 18.1856 | 0.5854 | 10.2982 |

## G. 조건 층화

대표 조건 3건을 기존 C001 GS 진단 지표와 이번 readout coverage 재측정에 붙였다.

| building_id | texture_class | texture_sufficient_proxy | n_views_nadir | raw_dense_success | acmp_success | mechanism_bucket | gs_median_clean_coverage | gs_median_render_backproj_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEBY_LOD2_4907184 | not_reviewed | unknown | 1.4200 | True | True | both_have_success | 0.9996 | 1.0000 |
| DEBY_LOD2_60098 | not_reviewed | unknown | 0.0000 | True | False | gs_only_success | 0.0415 | 0.5217 |
| DEBY_LOD2_8568391 | texture_poor | false | 1.0200 | False | False | gs_only_success | 0.0181 | 1.0000 |

## 원인 귀속표

| failure_axis | candidate_cause | evidence_metric | value | observation |
| --- | --- | --- | --- | --- |
| coverage_collapse | readout_minobs_sor_discard | mean(drop_render_to_minobs + drop_minobs_to_sor) | 0.3788 | positive means sampled render support exceeds retained TSDF/SOR footprint coverage |
| coverage_collapse | render_depth_support_absent | mean(render_depth_backproj_sample_pre_readout coverage) | 0.6232 | low sampled pre-readout footprint coverage means the checkpoint render already supplies little roof support |
| coverage_collapse | mvs_depth_no_signal_texture_proxy | median MVS valid fraction on semantic roof pixels | 0.9268 | low roof valid-mask coverage means depth supervision was sparse on roof pixels |
| coverage_collapse_or_flattening | floater_or_degenerate_gaussians | mean off-seed>1m proxy + elongated>10 fraction | 1.1725 | seed-distance proxy is not surface truth; it flags drift away from initialization support |
| flattening_or_depth_error | sh_view_dependent_absorption | mean PSNR gain SH3-SH0; depth MAE delta SH3-SH0 | 2.7402 | depth_mae_delta_sh3_minus_sh0=0.0000; large PSNR gain with non-improved depth suggests appearance absorbs error |
| flattening_or_depth_error | render_depth_itself | mean SH3 depth MAE vs MVS valid pixels | 6.9310 | MVS depth is a baseline signal, not final geometric truth |
| condition_strata | texture_observation_interaction | target case rows available | 3.0000 | 4907184/60098/8568391 retained as named strata cases |

판별 한 줄(판정 아님): 커버리지 붕괴는 sample render footprint coverage mean=0.623; render->TSDF/SOR drop mean=0.379; SH3 depth MAE vs MVS=6.931 m로 관찰된다.

## ③ 라우팅 후보

- depth 감독 강화 0.03->0.5(CityGaussianV2식) 후보
- readout minobs/SOR 완화 후보
- floater/elongation 제어 및 distortion 복원(scene-scale) 후보
- SH 제한 후보

## 인용·근거

- `docs/W_D4_손실config_감사.md`, `docs/W_D4config감사_분석·②연결_20260707.md`, `docs/W_문헌검증_GS기하_foundation·가중·평가_20260707.md`.
- 2DGS: arXiv 2403.17888 (<https://arxiv.org/abs/2403.17888>), depth distortion/normal consistency가 geometry regularization으로 제시됨.
- CityGaussianV2: arXiv 2411.00771 (<https://arxiv.org/abs/2411.00771>), large-scale reconstruction에서 depth regression과 geometry accuracy 이슈를 다룸.
- AlignGS: arXiv 2510.07839 (<https://arxiv.org/abs/2510.07839>), semantic priors를 geometry regularizer로 쓰는 sparse-view reconstruction 방향.

재확인: 학습 0 · 정식 재조립 0 · 판정 0.
