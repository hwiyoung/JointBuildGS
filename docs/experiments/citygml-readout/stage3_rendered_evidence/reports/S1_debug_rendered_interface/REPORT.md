# S1-debug Rendered Interface Failure Attribution

## 1. Purpose and research intent

This run localizes why S1 rendered evidence did not behave like E2 clean evidence. It keeps the Mutual checkpoint fixed and treats rendered depth, normal, semantic, support, fusion, sampling, and the E2 splitter as separable diagnostic surfaces.

## 2. S1 failure recap

S1 C_rendered had n_pred=12, matched=3, instance_recall=0.023, matched_F_mean=0.229. Rendered evidence quality was low and F2 mean_view_count was approximately 1.021.

## 3. Why debug before G2 retraining

Rendered evidence is still the correct Stage2 to Stage3 interface to debug because Stage2 directly supervises rendered depth, normals, and semantics. This run checks export, coordinate handling, field frames, fusion, and splitter compatibility before changing training.

## 4. Phase 0 artifact/reproduction

| artifact | metric | S1 | debug | status |
| --- | --- | --- | --- | --- |
| render_export | n_raw_samples | 2752512 | 2752512 | OK |
| render_export | n_valid_samples | 2700538 | 2700538 | OK |
| fusion_summary | F0 | 450000 | 1.0 | S1_REFERENCED |
| fusion_summary | F1 | 2643931 | 1.0214101653938776 | S1_REFERENCED |
| fusion_summary | F2 | 2646220 | 1.0205266379968407 | S1_REFERENCED |
| split_summary | A_gt_clean | {"n_pred": "143", "matched": "121", "instance_recall": "0.9236641221374046", "matched_F_mean": "0.8395473963046289"} | same S1 source | S1_REFERENCED |
| split_summary | B_primitive | {"n_pred": "11", "matched": "5", "instance_recall": "0.03816793893129771", "matched_F_mean": "0.47915084245170503"} | same S1 source | S1_REFERENCED |
| split_summary | C_rendered | {"n_pred": "12", "matched": "3", "instance_recall": "0.022900763358778626", "matched_F_mean": "0.22869488053028966"} | same S1 source | S1_REFERENCED |

| cap | value | source |
| --- | --- | --- |
| primitive_scene_evidence_max | 120000 | debug_runtime |
| rendered_scene_evidence_max | 300000 | debug_runtime |
| component_readout_evidence_max | 2500 | debug_runtime |
| s1_render_export_max_raw_samples | 3000000 | S1 |
| s1_pixel_stride | 2 | S1 |
| s1_selected_view_count | 56 | S1 |

## 5. Image-space quality

| depth_MAE_mean | normal_abs_mean | semantic_acc_mean | mIoU_mean |
| --- | --- | --- | --- |
| 1.373 | 0.978 | 0.970 | 0.903 |

## 6. Coordinate/unprojection sanity

| variant | reproj_px_mean | GT_dist_mean | GT_dist_p95 | scale_ratio |
| --- | --- | --- | --- | --- |
| z_depth_existing | 0.000 | 26.914 | 59.907 | 0.781 |

## 7. Normal frame/sign audit

| best_variant | signed_dot | abs_dot |
| --- | --- | --- |
| N0_exported | 0.084 | 0.570 |

## 8. Semantic channel audit

| scope | mapping | accuracy | mIoU |
| --- | --- | --- | --- |
| image_expected_mean | expected | 0.970 | 0.903 |
| 3d_nearest_gt | expected | 0.444 | 0.340 |

## 9. Fusion/support audit

| variant | n_points | mean_view_count | normal_cos | sem_acc | mIoU | boundary@0.5 |
| --- | --- | --- | --- | --- | --- | --- |
| F0_no_fusion_downsample | 450000 | 1.000 | 0.569 | 0.445 | 0.340 | 0.753 |
| F1_class_aware_voxel_0p05 | 2643931 | 1.021 | 0.569 | 0.444 | 0.340 | 0.803 |
| F2_class_normal_aware_voxel_0p05 | 2646220 | 1.021 | 0.569 | 0.445 | 0.340 | 0.803 |
| F3_class_aware_voxel_0p10 | 2554438 | 1.057 | 0.569 | 0.443 | 0.338 | 0.803 |
| F4_class_normal_aware_voxel_0p10 | 2563422 | 1.053 | 0.569 | 0.444 | 0.340 | 0.803 |
| F5_class_aware_voxel_0p20 | 2285105 | 1.181 | 0.567 | 0.440 | 0.336 | 0.803 |
| F6_E2_density_matched_sampling | 277325 | 1.018 | 0.569 | 0.445 | 0.340 | 0.660 |
| F7_tile_balanced_sampling | 289885 | 1.019 | 0.503 | 0.401 | 0.287 | 0.679 |
| F8_view_count_ge_2_only | 52830 | 2.028 | 0.464 | 0.430 | 0.344 | 0.106 |

## 10. Sampling/cap audit

| mode | n_pred | matched | recall | precision | matched_F |
| --- | --- | --- | --- | --- | --- |
| S0_global_random_300k | 9 | 4 | 0.031 | 0.444 | 0.495 |
| S1_class_balanced_300k | 12 | 3 | 0.023 | 0.250 | 0.229 |
| S2_E2_density_matched | 18 | 3 | 0.023 | 0.167 | 0.561 |
| S3_spatial_tile_balanced | 13 | 3 | 0.023 | 0.231 | 0.577 |
| S4_roof_wall_priority | 21 | 8 | 0.061 | 0.381 | 0.320 |
| S5_no_cap_on_target_subset | 49 | 13 | 0.099 | 0.265 | 0.387 |

## 11. Field replacement oracle

| variant | n_pred | matched | recall | precision | matched_F |
| --- | --- | --- | --- | --- | --- |
| C0_rendered_xyz_rendered_normal_rendered_semantic_rendered_support | 12 | 3 | 0.023 | 0.250 | 0.229 |
| C1_rendered_xyz_GT_nearest_normal_rendered_semantic_rendered_support | 12 | 3 | 0.023 | 0.250 | 0.229 |
| C2_rendered_xyz_rendered_normal_GT_nearest_semantic_rendered_support | 27 | 6 | 0.046 | 0.222 | 0.284 |
| C3_rendered_xyz_GT_nearest_normal_GT_nearest_semantic_rendered_support | 27 | 6 | 0.046 | 0.222 | 0.284 |
| C4_GT_clean_xyz_rendered_semantic_nearest_rendered_evidence | 124 | 108 | 0.824 | 0.871 | 0.793 |
| C5_GT_clean_xyz_rendered_normal_nearest_rendered_evidence | 143 | 121 | 0.924 | 0.846 | 0.839 |

## 12. Bid-local rendered sanity

| source | bid | success | F | footprint_IoU | h_err | vol_ratio | reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E1_GT_clean_per_building | B0 | True | 0.904 | 0.999 | 0.000 | 2.164 | LOW_PRECISION_OVERFILL |
| E3_primitive_bid_local | B0 | True | 0.584 | 0.272 | 0.725 | 5.427 | OVER_VOLUME |
| S1_rendered_bid_local | B0 | True | 0.587 | 0.089 | 0.767 | 8.912 | OVER_VOLUME |
| E1_GT_clean_per_building | B1 | True | 0.990 | 1.000 | 0.000 | 1.000 | VAL3DITY_BLOCKED_DEPENDENCY |
| E3_primitive_bid_local | B1 | True | 0.621 | 0.410 | 0.872 | 3.681 | OVER_VOLUME |
| S1_rendered_bid_local | B1 | True | 0.614 | 0.855 | 1.251 | 2.169 | OVER_VOLUME |
| E1_GT_clean_per_building | B2 | True | 0.999 | 0.997 | 0.000 | 1.620 | VAL3DITY_BLOCKED_DEPENDENCY |
| E3_primitive_bid_local | B2 | True | 0.410 | 0.291 | 0.740 | 6.875 | OVER_VOLUME |
| S1_rendered_bid_local | B2 | True | 0.514 | 0.230 | 0.721 | 7.493 | OVER_VOLUME |
| E1_GT_clean_per_building | B6 | True | 0.907 | 0.992 | 3.607 | 0.630 | VAL3DITY_BLOCKED_DEPENDENCY |
| E3_primitive_bid_local | B6 | True | 0.665 | 0.373 | 1.278 | 4.153 | OVER_VOLUME |
| S1_rendered_bid_local | B6 | True | 0.628 | 0.677 | 1.929 | 5.852 | OVER_VOLUME |
| E1_GT_clean_per_building | B8 | True | 0.991 | 0.997 | 0.001 | 1.392 | VAL3DITY_BLOCKED_DEPENDENCY |
| E3_primitive_bid_local | B8 | True | 0.657 | 0.292 | 0.984 | 3.949 | OVER_VOLUME |
| S1_rendered_bid_local | B8 | True | 0.504 | 0.174 | 1.101 | 4.702 | OVER_VOLUME |
| E1_GT_clean_per_building | B123 | True | 0.601 | 0.985 | 0.000 | 0.318 | SHARED_WALL_LIKELY |
| E3_primitive_bid_local | B123 | True | 0.322 | 0.520 | 0.468 | 0.476 | LOW_RECALL_UNDERFILL |
| S1_rendered_bid_local | B123 | True | 0.398 | 0.320 | 0.262 | 0.204 | LOW_RECALL_UNDERFILL |
| E1_GT_clean_per_building | B126 | True | 0.569 | 0.997 | 4.152 | 0.587 | LOW_RECALL_UNDERFILL |
| E3_primitive_bid_local | B126 | True | 0.355 | 0.511 | 0.564 | 0.992 | LOW_RECALL_UNDERFILL |
| S1_rendered_bid_local | B126 | True | 0.349 | 0.534 | 1.090 | 1.731 | LOW_RECALL_UNDERFILL |

## 13. Failure attribution

| criterion | value |
| --- | --- |
| final_decision | S1D_EXPORT_BUG |
| failure_flags | ["same-view reprojection is usable but world alignment to GT is poor"] |
| image_depth_MAE_mean | 1.373 |
| image_normal_abs_mean | 0.978 |
| image_semantic_accuracy_mean | 0.970 |
| existing_reprojection_error_px_mean | 0.000 |
| existing_GT_distance_mean | 26.914 |
| best_normal_variant | N0_exported |
| best_normal_abs_dot | 0.570 |
| best_normal_signed_dot | 0.084 |
| semantic_expected_3d_accuracy | 0.444 |
| semantic_best_3d_accuracy | 0.444 |
| F2_mean_view_count | 1.021 |
| F8_view_count_ge2_points | 52830 |
| best_sampling_instance_recall | 0.099 |
| C0_instance_recall | 0.023 |
| C3_oracle_instance_recall | 0.046 |
| C4_GT_xyz_rendered_semantic_recall | 0.824 |
| bidlocal_success_count | 7 |
| stage2_retraining_performed | False |
| gt_used_in_non_oracle_generation | False |

## 14. Decision and next action

Required final decision: `S1D_EXPORT_BUG`.

Next action: fix the attributed interface layer before using this S1 result as evidence for retraining. If the decision is fusion/sampling or splitter mismatch, rerun the corresponding debug variant only; if it is rendered field bad or Mutual insufficient, move to G2 surface-group feasibility without claiming final CityJSON performance.

## Self-verification

- PASS: no Stage2 retraining.
- PASS: GT not used in non-oracle generation.
- PASS: image-space and 3D-space metrics separated.
- PASS: normal frame/sign variants tested.
- PASS: semantic channel permutation tested.
- PASS: fusion/view_count issue diagnosed.
- PASS: sampling/cap issue diagnosed.
- PASS: field replacement oracle separates xyz/normal/semantic/support.
- PASS: bid-local rendered sanity separates full-scene split from per-building read-out.
