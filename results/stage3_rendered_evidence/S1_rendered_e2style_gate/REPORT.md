# S1 Rendered Evidence E2-style Gate

## 1. Purpose and research intent

This experiment tests whether the current Mutual Stage2 checkpoint can be read as rendered full-scene surface evidence for Stage3. The target is not improved primitives; the target interface is semantic surface evidence that can feed a semantic face graph.

## 2. Why E2-style evidence is the correct interface test

E2 takes only position, normal, semantic class, and support weight. Replacing E2 clean evidence with Stage2 rendered evidence isolates the Stage2->Stage3 interface while keeping the splitter/read-out fixed.

## 3. Fusion method and why F2 is default

F2 groups samples by voxel (0.05m), semantic label, and normal bin. Class and normal bins prevent roof/wall/terrain and boundary-normal mixing; normals are aggregated with a second-moment principal direction.

## 4. E2 reference reproduction

| input | n_gt | n_pred | matched | instance_recall | instance_precision | overmerge | oversplit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2_GT_clean_evidence | 131 | 143 | 121 | 0.924 | 0.846 | 1 | 15 |

## 5. Rendered evidence export summary

| n_views | n_raw_samples | n_valid_samples | roof_samples | wall_samples | terrain_samples | mean_alpha | mean_sem_conf |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 56 | 2752512 | 2700538 | 1210959 | 223793 | 790180 | 0.837 | 0.839 |

## 6. Fusion comparison

| fusion | n_points | roof | wall | terrain | mean_view_count | mean_support | normal_consistency_mean | semantic_entropy_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F0 | 450000 | 112500 | 112500 | 112500 | 1.000 | 0.685 | 1.000 | 0.239 |
| F1 | 2643931 | 1197639 | 222149 | 750325 | 1.021 | 0.692 | 1.000 | 0.240 |
| F2 | 2646220 | 1199313 | 222452 | 750572 | 1.021 | 0.692 | 1.000 | 0.239 |

## 7. Evidence quality audit

| fusion | n_points | normal_cosine_mean | semantic_accuracy | mIoU | roof | wall | terrain |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F0 | 450000 | 0.542 | 0.419 | 0.310 | 112500 | 112500 | 112500 |
| F1 | 2643931 | 0.541 | 0.418 | 0.309 | 1197639 | 222149 | 750325 |
| F2 | 2646220 | 0.542 | 0.418 | 0.309 | 1199313 | 222452 | 750572 |

| bid | stratum | boundary@0.5 | roof_cov | wall_boundary | terrain_cov | normal_cos | sem_acc | diagnostic |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | OK_CONTROL | 0.753 | 0.979 | 0.753 | 0.688 | 0.407 | 0.254 | SEMANTIC_NOISY+NORMAL_NOISY |
| B1 | OK_CONTROL | 0.995 | 1.000 | 0.995 | 0.122 | 0.413 | 0.299 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B2 | OK_CONTROL | 0.435 | 1.000 | 0.435 | 0.250 | 0.410 | 0.270 | SEMANTIC_NOISY+NORMAL_NOISY+WALL_BOUNDARY_INSUFFICIENT+TERRAIN_SUPPORT_INSUFFICIENT |
| B8 | OK_CONTROL | 0.669 | 1.000 | 0.669 | 0.125 | 0.439 | 0.299 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B6 | HIP | 0.961 | 0.961 | 0.961 | 0.406 | 0.491 | 0.366 | SEMANTIC_NOISY+NORMAL_NOISY |
| B123 | SHARED_WALL | 0.896 | 0.872 | 0.896 | 0.186 | 0.457 | 0.386 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B126 | SHARED_WALL | 0.796 | 0.825 | 0.796 | 0.267 | 0.583 | 0.477 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B50 | GROUND_EVIDENCE | 0.839 | 0.835 | 0.839 | 0.031 | 0.428 | 0.393 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B104 | GROUND_EVIDENCE | 0.922 | 1.000 | 0.922 | 0.156 | 0.453 | 0.357 | SEMANTIC_NOISY+NORMAL_NOISY+TERRAIN_SUPPORT_INSUFFICIENT |
| B111 | E2_UNMATCHED_GT | 0.910 | 1.000 | 0.910 | 0.500 | 0.591 | 0.453 | SEMANTIC_NOISY+NORMAL_NOISY |
| B117 | E2_UNMATCHED_GT | 0.661 | 1.000 | 0.661 | 0.656 | 0.486 | 0.426 | SEMANTIC_NOISY+NORMAL_NOISY |

Figures: `phase3_quality_audit/rendered_evidence_topdown_semantic.png`, `phase3_quality_audit/rendered_evidence_normal_color.png`, and `phase3_quality_audit/overlays/`.

## 8. E2-style split comparison A/B/C

Implementation note: B/C split-read-out uses GT-free global caps for runtime control: primitive scene evidence max `120000`, rendered F2 scene evidence max `300000`, and component read-out evidence max `2500`. These are fixed globally and not tuned by building.

| input | n_pred | matched | instance_recall | instance_precision | overmerge | oversplit | matched_F_mean | matched_F_median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_gt_clean | 143 | 121 | 0.924 | 0.846 | 1 | 15 | 0.840 | 0.877 |
| B_primitive | 11 | 5 | 0.038 | 0.455 | 6 | 0 | 0.479 | 0.467 |
| C_rendered | 12 | 3 | 0.023 | 0.250 | 9 | 0 | 0.229 | 0.200 |

| bid | input | matched_component | match_IoU | F | footprint_IoU | h_err | vol_ratio | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | A_gt_clean | pred_004 | 0.996 | 0.966 | 0.996 | 0.063 | 1.359 | OK_GEOMETRY_ONLY |
| B1 | A_gt_clean | pred_009 | 0.994 | 0.988 | 0.994 | 0.022 | 1.006 | OK_GEOMETRY_ONLY |
| B2 | A_gt_clean | pred_018 | 0.989 | 0.988 | 0.989 | 0.019 | 1.307 | OK_GEOMETRY_ONLY |
| B8 | A_gt_clean | pred_046 | 0.810 | 0.804 | 0.810 | 0.003 | 0.819 | OK_GEOMETRY_ONLY |
| B6 | A_gt_clean | pred_020 | 0.884 | 0.851 | 0.884 | 3.660 | 0.231 | OK_GEOMETRY_ONLY |
| B123 | A_gt_clean | pred_057 | 0.495 | 0.490 | 0.495 | 1.250 | 0.553 | LOW_RECALL_UNDERFILL |
| B126 | A_gt_clean | pred_048 | 0.487 | 0.403 | 0.487 | 16.197 | 0.120 | LOW_RECALL_UNDERFILL |
| B50 | A_gt_clean | pred_079 | 0.764 | 0.732 | 0.764 | 0.893 | 2.054 | LOW_PRECISION_OVERFILL |
| B104 | A_gt_clean | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B111 | A_gt_clean | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B117 | A_gt_clean | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B0 | B_primitive | pred_000 | 0.523 | 0.467 | 0.523 | 0.835 | 0.371 | LOW_PRECISION_OVERFILL |
| B1 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B2 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B8 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B6 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B123 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B126 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B50 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B104 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B111 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B117 | B_primitive | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B0 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B1 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B2 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B8 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B6 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B123 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B126 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B50 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B104 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B111 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |
| B117 | C_rendered | NA | NA | NA | NA | NA | NA | UNMATCHED_GT |

## 9. Semantic face graph preview

| n_faces | n_roof_faces | n_wall_faces | n_ground_faces | face_planarity_max | open_edges | nonmanifold_edges | edge_incidence_ok | optional_cityjson_export_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1716 | 840 | 864 | 12 | 0.000 | 0 | 0 | True | EXPORTED_COMPONENT_CITYJSON |

## 10. GO/NG decision

| criterion | value |
| --- | --- |
| recommendation | S1_NG_RENDERED_EVIDENCE_RUN_G2_FEASIBILITY |
| C_improves_over_B_recall_and_F | False |
| C_instance_recall | 0.023 |
| B_instance_recall | 0.038 |
| A_instance_recall | 0.924 |
| C_matched_F_mean | 0.229 |
| B_matched_F_mean | 0.479 |
| OK_CONTROL_F_gt_0p6 | 0 |
| C_recall_ge_70pct_A | False |
| face_graph_preview_has_faces | True |
| next_action | run S3-pre G2 surface-group feasibility before any Stage2 retraining |

## 11. Recommendation for next experiment

Final recommendation: `S1_NG_RENDERED_EVIDENCE_RUN_G2_FEASIBILITY`.
Next action: run S3-pre G2 surface-group feasibility before any Stage2 retraining.

## Self-verification

- PASS: gravity=[0,1,0] asserted.
- PASS: Stage2 retraining was not performed; only Mutual checkpoint inference/export was used.
- PASS: GT was not used in rendered evidence generation or split/read-out.
- PASS: GT was used only for quality audit and post-generation matching.
- PASS: F2 class-normal-aware voxel fusion is the default C_rendered input.
- PASS: F0/F1 are diagnostic only.
- PASS: A/B/C use the same E2 splitter/read-out implementation.
- PASS: semantic_faces.json and face_graph.json are primary Phase 5 outputs.
- PASS: val3dity dependency status is separate from structural metrics.
