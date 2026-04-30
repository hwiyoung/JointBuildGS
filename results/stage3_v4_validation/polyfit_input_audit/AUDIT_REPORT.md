# GT-derived PolyFit Input Audit

- source GT: `results/phase2_synthesis/scene.obj`
- linked metrics: `results/stage3_polyfit_phase2/metrics.json`
- target bids: B1, B2, B6, B8, B0, B3
- core GO/NG bids: B1, B2, B6, B8, B0

## Existing PolyFit result summary

| bid | type | val3dity | errors | coverage | vol_ratio | Hausdorff | Chamfer |
|---:|---|---|---|---:|---:|---:|---:|
| B1 | flat | PASS |  | 0.478046 | 0.999975 | 0.8137 | 0.2288 |
| B2 | flat | PASS |  | 0.024378 | 0.049238 | 12.2232 | 3.0811 |
| B6 | hip | FAIL | 303;303;303;303;303;303 | 0.060865 | 0.142760 | 7.5210 | 1.2622 |
| B8 | gable | PASS |  | 0.056964 | 0.110796 | 10.5084 | 1.8440 |
| B0 | tri-slope | FAIL | 303;303 | 0.018061 | 0.035653 | 12.2147 | 2.3351 |
| B3 | complex | SKIPPED | polyfit_fail: Line: 55 | NA | NA | NA | NA |

## Input validation summary

| bid | n_points | n_planes | invalid_normals | out_of_range_plane_id | duplicate_ratio | bbox_match | verdict |
|---:|---:|---:|---:|---:|---:|---|---|
| B1 | 80 | 7 | 0 | 0 | 0.5250 | True | PASS |
| B2 | 80 | 8 | 0 | 0 | 0.5250 | True | PASS |
| B6 | 284 | 21 | 0 | 0 | 0.4930 | True | PASS |
| B8 | 120 | 10 | 0 | 0 | 0.5167 | True | PASS |
| B0 | 214 | 16 | 0 | 0 | 0.4953 | True | PASS |
| B3 | 1123 | 66 | 0 | 0 | 0.4292 | True | PASS |

## Plane count / sampling density summary

| bid | type | n_gt_faces | n_planes | n_points | small_area_plane_ratio | low_point_planes | unsampled_faces | unsampled_area_ratio |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| B1 | flat | 8 | 7 | 80 | 0.000 | 4 | 0 | 0.000000 |
| B2 | flat | 8 | 8 | 80 | 0.000 | 6 | 0 | 0.000000 |
| B6 | hip | 28 | 21 | 284 | 0.190 | 14 | 0 | 0.000000 |
| B8 | gable | 12 | 10 | 120 | 0.000 | 6 | 0 | 0.000000 |
| B0 | tri-slope | 21 | 16 | 214 | 0.312 | 11 | 0 | 0.000000 |
| B3 | complex | 127 | 66 | 1123 | 0.439 | 39 | 0 | 0.000000 |

## Over/under segmentation summary

| bid | possible_oversegmented_pairs | possible_undersegmented_planes | key issue |
|---:|---:|---:|---|
| B1 | 0 | 0 | reference successful Stage A case |
| B2 | 0 | 0 | input covers GT and validates, but PolyFit output is invalid or low coverage |
| B6 | 0 | 1 | plane_count=21, small_area_plane_ratio=19.0% |
| B8 | 0 | 0 | input covers GT and validates, but PolyFit output is invalid or low coverage |
| B0 | 0 | 1 | plane_count=16, small_area_plane_ratio=31.2% |
| B3 | 0 | 16 | plane_count=66, small_area_plane_ratio=43.9% |

## Visualization links

| bid | plane PLY | class PLY | GT plane mesh | top | side | oblique | report |
|---:|---|---|---|---|---|---|---|
| B1 | [B1/input_points_by_plane.ply](B1/input_points_by_plane.ply) | [B1/input_points_by_class.ply](B1/input_points_by_class.ply) | [B1/gt_mesh_with_plane_groups.ply](B1/gt_mesh_with_plane_groups.ply) | [top](B1/input_vs_gt_overlay_top_by_plane.png) | [side](B1/input_vs_gt_overlay_side_by_plane.png) | [oblique](B1/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B1/audit_report.md) |
| B2 | [B2/input_points_by_plane.ply](B2/input_points_by_plane.ply) | [B2/input_points_by_class.ply](B2/input_points_by_class.ply) | [B2/gt_mesh_with_plane_groups.ply](B2/gt_mesh_with_plane_groups.ply) | [top](B2/input_vs_gt_overlay_top_by_plane.png) | [side](B2/input_vs_gt_overlay_side_by_plane.png) | [oblique](B2/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B2/audit_report.md) |
| B6 | [B6/input_points_by_plane.ply](B6/input_points_by_plane.ply) | [B6/input_points_by_class.ply](B6/input_points_by_class.ply) | [B6/gt_mesh_with_plane_groups.ply](B6/gt_mesh_with_plane_groups.ply) | [top](B6/input_vs_gt_overlay_top_by_plane.png) | [side](B6/input_vs_gt_overlay_side_by_plane.png) | [oblique](B6/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B6/audit_report.md) |
| B8 | [B8/input_points_by_plane.ply](B8/input_points_by_plane.ply) | [B8/input_points_by_class.ply](B8/input_points_by_class.ply) | [B8/gt_mesh_with_plane_groups.ply](B8/gt_mesh_with_plane_groups.ply) | [top](B8/input_vs_gt_overlay_top_by_plane.png) | [side](B8/input_vs_gt_overlay_side_by_plane.png) | [oblique](B8/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B8/audit_report.md) |
| B0 | [B0/input_points_by_plane.ply](B0/input_points_by_plane.ply) | [B0/input_points_by_class.ply](B0/input_points_by_class.ply) | [B0/gt_mesh_with_plane_groups.ply](B0/gt_mesh_with_plane_groups.ply) | [top](B0/input_vs_gt_overlay_top_by_plane.png) | [side](B0/input_vs_gt_overlay_side_by_plane.png) | [oblique](B0/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B0/audit_report.md) |
| B3 | [B3/input_points_by_plane.ply](B3/input_points_by_plane.ply) | [B3/input_points_by_class.ply](B3/input_points_by_class.ply) | [B3/gt_mesh_with_plane_groups.ply](B3/gt_mesh_with_plane_groups.ply) | [top](B3/input_vs_gt_overlay_top_by_plane.png) | [side](B3/input_vs_gt_overlay_side_by_plane.png) | [oblique](B3/input_vs_gt_overlay_oblique_by_plane.png) | [audit](B3/audit_report.md) |

## Final verdict table

| bid | type | n_planes | n_points | polyfit_val3dity | polyfit_coverage | input_verdict | key_issue | recommended_next |
|---:|---|---:|---:|---|---:|---|---|---|
| B1 | flat | 7 | 80 | PASS | 0.478046 | INPUT_OK | reference successful Stage A case | keep as good-case reference |
| B2 | flat | 8 | 80 | PASS | 0.024378 | INPUT_OK_BACKEND_FAIL | input covers GT and validates, but PolyFit output is invalid or low coverage | treat as PolyFit backend/objective failure |
| B6 | hip | 21 | 284 | FAIL | 0.060865 | INPUT_OVERSEGMENTED | plane_count=21, small_area_plane_ratio=19.0% | test simplified GT major-plane input |
| B8 | gable | 10 | 120 | PASS | 0.056964 | INPUT_OK_BACKEND_FAIL | input covers GT and validates, but PolyFit output is invalid or low coverage | treat as PolyFit backend/objective failure |
| B0 | tri-slope | 16 | 214 | FAIL | 0.018061 | INPUT_OVERSEGMENTED | plane_count=16, small_area_plane_ratio=31.2% | test simplified GT major-plane input |
| B3 | complex | 66 | 1123 | SKIPPED | NA | INPUT_OVERSEGMENTED | plane_count=66, small_area_plane_ratio=43.9% | test simplified GT major-plane input |

## Simplified GT major-plane input recommendation

| bid | needed | planes to keep |
|---:|---|---|
| B1 | no | ground + major walls + 1 roof plane |
| B2 | no | ground + major walls + 1 roof plane |
| B6 | yes | ground + major walls + roof normal modes |
| B8 | no | ground + major walls + 2 roof planes |
| B0 | yes | ground + major walls + 3 roof planes |
| B3 | yes | ground + dominant wall modes + dominant roof modes only |

## GO/NG interpretation

- INPUT_OK_BACKEND_FAIL among 5 core bids: 2/5
- INPUT_OVERSEGMENTED or INPUT_SAMPLING_INSUFFICIENT among 5 core bids: 2/5
- Decision: Mixed result: valid-low-coverage cases point to PolyFit objective/backend, while complex/non-manifold cases need simplified major-plane input.

## Self-verification

- PASS: all bid input_points_by_plane.ply
- PASS: all bid gt_mesh_with_plane_groups.ply
- PASS: all bid top/side/oblique overlay PNG
- PASS: all bid input_planes.csv
- PASS: all bid audit_report.md
- PASS: overall AUDIT_REPORT.md
- PASS: each bid has verdict
- PASS: core metrics linked
