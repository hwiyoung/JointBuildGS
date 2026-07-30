# Stage3-v1 Auditable Semantic Surface Read-out and FC-S1 v0-v1 Comparison

## 1. Objective and alignment

This run compares the original FC-S1 Stage3-v0 against Stage3-v1 while preserving the same building set, source definitions, footprint/domain condition, gravity convention, and evidence files wherever they exist. The target remains semantic 3D building read-out: RoofSurface, WallSurface, GroundSurface, face adjacency, edge incidence, and shell diagnostics.

## 2. Controlled inputs

- FC-S1 source root: `results/footprint_conditioned_readout/FC_S1_semantic_surface_readout`
- Output root: `results/footprint_conditioned_readout/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison`
- Target bids: `B0, B1, B2, B8, B6, B3, B123, B126, B50, B104`
- Footprint buffer: `0.75` m
- Gravity: `[0, 1, 0]`
- E1_Baseline_rendered remains `SOURCE_MISSING`; regeneration status is recorded in `phase0_inventory/baseline_rendered_regeneration_status.json`.

## 3. Comparison matrix

The matrix includes `Stage3Algo-v0 + Metric-v0`, `Stage3Algo-v0 + Metric-v1`, `Stage3Algo-v1 + Metric-v1`, and optional `Stage3Algo-v1 + Metric-v0`. This separates evaluator effects from read-out effects.

| algo | metric | source | n_rows | OK | mean_F | mean_roof_cov | mean_wall_cov | mean_ground_cov | mean_open_edges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage3Algo-v0 | Metric-v0 | E0_GT_clean_upper_bound | 10 | 10 | 0.840 | 0.610 | 0.856 | 0.991 | 0.000 |
| Stage3Algo-v0 | Metric-v0 | E1_Baseline_rendered | 10 | 0 | NA | NA | NA | NA | NA |
| Stage3Algo-v0 | Metric-v0 | E2_Mutual_rendered | 10 | 10 | 0.805 | 0.611 | 0.855 | 0.838 | 0.000 |
| Stage3Algo-v0 | Metric-v0 | E3_Baseline_primitive | 10 | 9 | 0.691 | 0.406 | 0.836 | 0.145 | 0.000 |
| Stage3Algo-v0 | Metric-v0 | E4_Mutual_primitive | 10 | 9 | 0.694 | 0.463 | 0.833 | 0.025 | 0.000 |
| Stage3Algo-v0 | Metric-v1 | E0_GT_clean_upper_bound | 10 | 10 | 0.838 | 0.614 | 0.858 | 0.989 | 0.000 |
| Stage3Algo-v0 | Metric-v1 | E1_Baseline_rendered | 10 | 0 | NA | NA | NA | NA | NA |
| Stage3Algo-v0 | Metric-v1 | E2_Mutual_rendered | 10 | 10 | 0.803 | 0.609 | 0.854 | 0.837 | 0.000 |
| Stage3Algo-v0 | Metric-v1 | E3_Baseline_primitive | 10 | 9 | 0.692 | 0.412 | 0.837 | 0.145 | 0.000 |
| Stage3Algo-v0 | Metric-v1 | E4_Mutual_primitive | 10 | 9 | 0.691 | 0.464 | 0.836 | 0.025 | 0.000 |
| Stage3Algo-v1 | Metric-v0 | E0_GT_clean_upper_bound | 10 | 10 | 0.840 | 0.610 | 0.856 | 0.991 | 0.000 |
| Stage3Algo-v1 | Metric-v0 | E1_Baseline_rendered | 10 | 0 | NA | NA | NA | NA | NA |
| Stage3Algo-v1 | Metric-v0 | E2_Mutual_rendered | 10 | 10 | 0.805 | 0.611 | 0.855 | 0.838 | 0.000 |
| Stage3Algo-v1 | Metric-v0 | E3_Baseline_primitive | 10 | 10 | 0.669 | 0.412 | 0.787 | 0.131 | 0.000 |
| Stage3Algo-v1 | Metric-v0 | E4_Mutual_primitive | 10 | 10 | 0.681 | 0.517 | 0.790 | 0.023 | 0.000 |
| Stage3Algo-v1 | Metric-v1 | E0_GT_clean_upper_bound | 10 | 10 | 0.838 | 0.614 | 0.858 | 0.989 | 0.000 |
| Stage3Algo-v1 | Metric-v1 | E1_Baseline_rendered | 10 | 0 | NA | NA | NA | NA | NA |
| Stage3Algo-v1 | Metric-v1 | E2_Mutual_rendered | 10 | 10 | 0.803 | 0.609 | 0.854 | 0.837 | 0.000 |
| Stage3Algo-v1 | Metric-v1 | E3_Baseline_primitive | 10 | 10 | 0.669 | 0.418 | 0.787 | 0.131 | 0.000 |
| Stage3Algo-v1 | Metric-v1 | E4_Mutual_primitive | 10 | 10 | 0.679 | 0.517 | 0.791 | 0.023 | 0.000 |

## 4. Metric-v1 audit

Metric-v1 writes explicit `metric_version`, per-face matching logs, and deterministic per-sample matching logs. Surface coverage requires nearest-surface distance within 0.5 m and matching semantic type. Logs are stored under `phase1_metric_v1_audit_stage3_v0/` and `phase2_stage3_v1_metric_v1_audit/`.

## 5. Stage3Algo-v1 patch

Stage3Algo-v1 uses the same v0 relation read-out path. The only algorithm patch is an audited read-out-only ground reference synthesized from the evidence Y distribution when a source has roof evidence but zero ground evidence. It does not change Stage2 evidence files and does not use GT roof type, GT heights, GT final mesh, or GT semantic surfaces.

| bid | source | patch_applied | reason | n_synthetic_ground_points |
| --- | --- | --- | --- | --- |
| B0 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B0 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B0 | E2_Mutual_rendered | False | ground evidence already present |  |
| B0 | E3_Baseline_primitive | False | ground evidence already present |  |
| B0 | E4_Mutual_primitive | False | ground evidence already present |  |
| B1 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B1 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B1 | E2_Mutual_rendered | False | ground evidence already present |  |
| B1 | E3_Baseline_primitive | False | ground evidence already present |  |
| B1 | E4_Mutual_primitive | False | ground evidence already present |  |
| B2 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B2 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B2 | E2_Mutual_rendered | False | ground evidence already present |  |
| B2 | E3_Baseline_primitive | False | ground evidence already present |  |
| B2 | E4_Mutual_primitive | False | ground evidence already present |  |
| B8 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B8 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B8 | E2_Mutual_rendered | False | ground evidence already present |  |
| B8 | E3_Baseline_primitive | False | ground evidence already present |  |
| B8 | E4_Mutual_primitive | False | ground evidence already present |  |
| B6 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B6 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B6 | E2_Mutual_rendered | False | ground evidence already present |  |
| B6 | E3_Baseline_primitive | False | ground evidence already present |  |
| B6 | E4_Mutual_primitive | False | ground evidence already present |  |
| B3 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B3 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B3 | E2_Mutual_rendered | False | ground evidence already present |  |
| B3 | E3_Baseline_primitive | False | ground evidence already present |  |
| B3 | E4_Mutual_primitive | False | ground evidence already present |  |
| B123 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B123 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B123 | E2_Mutual_rendered | False | ground evidence already present |  |
| B123 | E3_Baseline_primitive | False | ground evidence already present |  |
| B123 | E4_Mutual_primitive | False | ground evidence already present |  |
| B126 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B126 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B126 | E2_Mutual_rendered | False | ground evidence already present |  |
| B126 | E3_Baseline_primitive | False | ground evidence already present |  |
| B126 | E4_Mutual_primitive | False | ground evidence already present |  |
| B50 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B50 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B50 | E2_Mutual_rendered | False | ground evidence already present |  |
| B50 | E3_Baseline_primitive | True | no ground evidence; inferred a read-out-only ground reference from evidence Y distribution | 21 |
| B50 | E4_Mutual_primitive | False | ground evidence already present |  |
| B104 | E0_GT_clean_upper_bound | False | ground evidence already present |  |
| B104 | E1_Baseline_rendered | False | SOURCE_MISSING |  |
| B104 | E2_Mutual_rendered | False | ground evidence already present |  |
| B104 | E3_Baseline_primitive | False | ground evidence already present |  |
| B104 | E4_Mutual_primitive | True | no ground evidence; inferred a read-out-only ground reference from evidence Y distribution | 9 |

## 6. Read-out status

Stage3-v0 OK rows: `38/50`. Stage3-v1 OK rows: `40/50`.

## 7. Evaluator effect

Evaluator-effect rows compare Stage3Algo-v0 under Metric-v0 vs Metric-v1. Improvements here are audit/matching changes, not reconstruction changes.

- Metric-v1 higher rows: `165`
- Metric-v1 lower rows: `201`

## 8. Algorithm effect

Algorithm-effect rows compare Stage3Algo-v0 vs Stage3Algo-v1 under Metric-v1.

- Stage3-v1 improvement rows: `0`
- Stage3-v1 degradation rows: `0`
- Stage3-v1 read-out recovered rows: `34`
- Stage3-v1 read-out regressed rows: `0`
- Ground-reference patches applied: `2`

## 9. QA artifacts

- Matrix: `phase3_matrix/matrix_metrics_by_bid.csv`
- Evaluator effect: `phase3_matrix/evaluator_effect_by_bid.csv`
- Algorithm effect: `phase3_matrix/algorithm_effect_by_bid.csv`
- Final effect: `phase3_matrix/final_effect_by_bid.csv`
- Viewer: `viewer/stage3_qa.html`

## 10. Final interpretation

Stage3-v1 is an auditable v1 rather than a replacement reconstruction pipeline. Its main algorithmic value in this run is converting zero-ground-evidence read-out failures into explicit, logged shell attempts where the cause and correction are inspectable. Metric-v1 provides the matching evidence needed to decide whether future changes are evaluator effects or reconstruction effects.

## 11. Self-verification

- PASS: no full-scene building split used.
- PASS: FC-S1 building set preserved.
- PASS: footprint used only as domain condition.
- PASS: gravity convention preserved as `[0, 1, 0]`.
- PASS: source definitions E0/E1/E2/E3/E4 preserved.
- PASS: Stage2 evidence generation logic not changed.
- PASS: footprint buffer size not changed.
- PASS: primary outputs remain `semantic_faces.json`, `face_graph.json`, and `shell_diagnostics.json`.
- PASS: Metric-v1 and Stage3Algo-v1 effects are separated in the comparison matrix.
- PASS: GT roof type, GT roof partition, GT final mesh, and GT semantic surfaces are not used for Stage2-derived generation.
