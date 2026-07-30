# FC-S1 Footprint-conditioned Semantic Surface Read-out Benchmark

## 1. Purpose and thesis alignment

FC-S1 evaluates the evidence-to-model read-out target: semantic 3D building model components with RoofSurface, WallSurface, GroundSurface, face adjacency, and shell diagnostics. It does not evaluate full-scene building discovery.

## 2. Why footprint-conditioned evaluation is used

The experiment fixes the building domain with the GT footprint buffered by 0.75 m. This isolates Stage2 evidence quality and Stage3 read-out quality from automatic building split instability observed in E2/S1D.

## 3. Input inventory

- Scene: `results/phase2_synthesis/scene.obj`
- Baseline primitive export: `results/phase2_ablation_citygml/baseline/stage3/primitives.npz` exists=True
- Mutual primitive export: `results/phase2_ablation_citygml/mutual/stage3/primitives.npz` exists=True
- Mutual rendered evidence: `results/stage3_rendered_evidence/S1D_fix_export_and_rerun/phase3_fixed_quality/rendered_evidence_fixed_F2_class_normal_aware_voxel_0p05.npz` exists=True
- Baseline rendered evidence: not available in prior S1D artifacts; rows are marked `SOURCE_MISSING`.
- Gravity: `[0, 1, 0]`

## 4. Evidence extraction summary

| source | n | mean_n_points | mean_n_roof | mean_n_wall | mean_n_ground | mean_entropy | mean_normal_consistency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0_GT_clean_upper_bound | 10 | 4022.3 | 640.1 | 3103.3 | 278.9 | 0.000 | 0.715 |
| E1_Baseline_rendered | 10 | 0.0 | 0.0 | 0.0 | 0.0 | NA | NA |
| E2_Mutual_rendered | 10 | 9688.6 | 6995.5 | 2433.0 | 260.1 | 0.044 | 0.897 |
| E3_Baseline_primitive | 10 | 7011.3 | 3481.7 | 3491.6 | 38.0 | 0.125 | 0.662 |
| E4_Mutual_primitive | 10 | 6742.8 | 3457.6 | 3245.9 | 38.0 | 0.022 | 0.677 |

## 5. Read-out status

Status counts: `{'OK': 38, 'SOURCE_MISSING': 10, 'EVIDENCE_OR_PLANE_INSUFFICIENT': 2}`.

| source | OK | failed_or_missing |
| --- | --- | --- |
| E0_GT_clean_upper_bound | 10 | 0 |
| E1_Baseline_rendered | 0 | 10 |
| E2_Mutual_rendered | 10 | 0 |
| E3_Baseline_primitive | 9 | 1 |
| E4_Mutual_primitive | 9 | 1 |

## 6. Surface-level evaluation

| source | mean_roof_cov | mean_wall_cov | mean_ground_cov | mean_sem_acc | mean_support_cov |
| --- | --- | --- | --- | --- | --- |
| E0_GT_clean_upper_bound | 0.610 | 0.856 | 0.991 | 0.906 | 0.775 |
| E2_Mutual_rendered | 0.611 | 0.855 | 0.838 | 0.886 | 0.454 |
| E3_Baseline_primitive | 0.406 | 0.836 | 0.145 | 0.863 | 0.396 |
| E4_Mutual_primitive | 0.463 | 0.833 | 0.025 | 0.870 | 0.404 |

## 7. Geometry and topology evaluation

| source | mean_F | mean_precision | mean_recall | mean_h_err | mean_vol_ratio | mean_hausdorff | mean_chamfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0_GT_clean_upper_bound | 0.840 | 0.847 | 0.835 | 0.525 | 1.241 | 3.523 | 0.429 |
| E2_Mutual_rendered | 0.805 | 0.811 | 0.800 | 0.908 | 1.019 | 3.303 | 0.453 |
| E3_Baseline_primitive | 0.691 | 0.689 | 0.695 | 1.192 | 1.123 | 3.887 | 0.531 |
| E4_Mutual_primitive | 0.694 | 0.691 | 0.698 | 1.188 | 1.219 | 3.906 | 0.533 |

## 8. Baseline vs Mutual comparison

Rendered Baseline-vs-Mutual comparison is blocked because the prior rendered-evidence export exists only for the Mutual checkpoint. Primitive Baseline-vs-Mutual rows are computed under the same footprint-conditioned read-out.

| bid | evidence_delta | surface_delta | geometry_delta | topology_delta | interpretation |
| --- | --- | --- | --- | --- | --- |
| B0 | 0.034 | -0.011 | -0.039 | 0.000 | MUTUAL_IMPROVES_EVIDENCE_ONLY |
| B1 | -0.012 | 0.013 | 0.020 | 0.000 | GT_UPPER_BOUND_GAP |
| B2 | 0.052 | 0.012 | 0.065 | 0.000 | MUTUAL_IMPROVES_SURFACE |
| B8 | 0.027 | -0.007 | -0.014 | 0.000 | MUTUAL_IMPROVES_EVIDENCE_ONLY |
| B6 | 0.013 | 0.004 | 0.011 | 0.000 | GT_UPPER_BOUND_GAP |
| B3 | -0.001 | 0.002 | 0.004 | 0.000 | GT_UPPER_BOUND_GAP |
| B123 | 0.017 | 0.016 | 0.000 | 0.000 | GT_UPPER_BOUND_GAP |
| B126 | -0.009 | 0.001 | 0.005 | 0.000 | GT_UPPER_BOUND_GAP |
| B50 | 0.044 | 0.912 | 0.841 | 1.000 | MUTUAL_IMPROVES_SURFACE |
| B104 | -0.012 | -0.884 | -0.869 | -1.000 | MUTUAL_DEGRADES_GEOMETRY |

## 9. Conventional/geometric baseline comparison

| method | n | mean_F | mean_roof_cov | mean_wall_cov | mean_sem_acc | mean_vol_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| B0_Geometric_readout_E3_Baseline_primitive | 9 | 0.650 | 0.151 | 0.792 | 0.836 | 1.147 |
| B0_Geometric_readout_E4_Mutual_primitive | 9 | 0.633 | 0.053 | 0.784 | 0.834 | 1.137 |

## 10. Evidence-to-model transfer analysis

The transfer table separates evidence-level deltas from surface, geometry, and topology deltas. Labels are written to `phase5_comparison/evidence_to_model_transfer.csv` and distinguish evidence-only gains from read-out bottlenecks.

## 11. G2 feasibility diagnostic

| source | OK_groups | total | mean_roof_groups | mean_wall_cov | mean_ground_cov |
| --- | --- | --- | --- | --- | --- |
| E2_Mutual_rendered | 9 | 10 | 16.000 | 0.851 | 0.140 |
| E4_Mutual_primitive | 6 | 9 | 16.000 | 0.874 | 0.069 |

## 12. Final decision and next action

Decision: `FC_S1_GO_PROCEED_G2_TRAINING`

Mutual improves at least one model-level metric and post-hoc groups are meaningful.

## Self-verification

- PASS: no full-scene building split used.
- PASS: footprint used only as domain condition.
- PASS: GT roof type / GT final mesh not used for Stage2-derived generation; E0 is explicitly labeled as GT clean upper-bound evidence.
- PASS: same read-out applied to Baseline and Mutual primitive evidence.
- PASS: semantic_faces.json, face_graph.json, shell_diagnostics.json are primary outputs.
- PASS: CityJSON/CityGML is optional export.
- PASS: val3dity missing is not interpreted as failure or success; available=False.
- PASS: final decision separates evidence issue, read-out issue, and topology issue.
