# G1 Numeric Source Mapping

## Core Table Cell Mapping

| table | row | cell | source path / row-filter |
| --- | --- | --- | --- |
| core_table.md | LoD2.2 generation rate (assembly) | ALS | docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_has_lod22 |
| core_table.md | LoD2.2 generation rate (assembly) | DIM | docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_has_lod22 |
| core_table.md | LoD2.2 generation rate (assembly) | gap | docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_has_lod22 |
| core_table.md | LoD2.2 generation rate (assembly) | section6_threshold_position | docs/W3_2c_canonical_paired_status.csv; coverage_control_population=yes; *_has_lod22 |
| core_table.md | Final success rate | ALS | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | Final success rate | DIM | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | Final success rate | gap | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | Final success rate | section6_threshold_position | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | Plane F1 median | ALS | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=plane_f1; old harness from docs/W3_1_threshold_position.csv |
| core_table.md | Plane F1 median | DIM | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=plane_f1; old harness from docs/W3_1_threshold_position.csv |
| core_table.md | Plane F1 median | gap | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=plane_f1; old harness from docs/W3_1_threshold_position.csv |
| core_table.md | Plane F1 median | section6_threshold_position | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=plane_f1; old harness from docs/W3_1_threshold_position.csv |
| core_table.md | Exterior boundary Chamfer (m) | ALS | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=boundary_chamfer_m |
| core_table.md | Exterior boundary Chamfer (m) | DIM | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=boundary_chamfer_m |
| core_table.md | Exterior boundary Chamfer (m) | gap | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=boundary_chamfer_m |
| core_table.md | Exterior boundary Chamfer (m) | section6_threshold_position | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=boundary_chamfer_m |
| core_table.md | Internal boundary Hausdorff (m) | ALS | docs/W3_2c_canonical_internal_boundary_summary.csv; metric=internal_boundary_hausdorff_m |
| core_table.md | Internal boundary Hausdorff (m) | DIM | docs/W3_2c_canonical_internal_boundary_summary.csv; metric=internal_boundary_hausdorff_m |
| core_table.md | Internal boundary Hausdorff (m) | gap | docs/W3_2c_canonical_internal_boundary_summary.csv; metric=internal_boundary_hausdorff_m |
| core_table.md | Internal boundary Hausdorff (m) | section6_threshold_position | docs/W3_2c_canonical_internal_boundary_summary.csv; metric=internal_boundary_hausdorff_m |
| core_table.md | Height NMAD (m) | ALS | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=height_nmad_m |
| core_table.md | Height NMAD (m) | DIM | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=height_nmad_m |
| core_table.md | Height NMAD (m) | gap | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=height_nmad_m |
| core_table.md | Height NMAD (m) | section6_threshold_position | docs/W3_2c_canonical_roofer_quality_summary.csv; metric=height_nmad_m |
| core_table.md | val3dity valid rate | ALS | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | val3dity valid rate | DIM | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | val3dity valid rate | gap | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |
| core_table.md | val3dity valid rate | section6_threshold_position | docs/W3_2c_canonical_success_rates.csv; population=coverage_controlled_93 |

## Appendix And Test Tables

| package item | source path | row/filter |
| --- | --- | --- |
| appendix completeness table | docs/W3_2c_canonical_success_rates.csv | all rows |
| appendix priority bucket table | docs/W3_2c_canonical_priority_buckets.csv | all rows |
| appendix quality metrics | docs/W3_2c_canonical_roofer_quality_summary.csv; docs/W3_2c_canonical_internal_boundary_summary.csv | all metric rows |
| appendix robustness tuning | docs/W2_3a_paired_success.csv | population=coverage_control_93_all |
| appendix robustness variants | docs/W2_3b_variant_success.csv; docs/W2_3b_roof_matching_recovery.csv | population=coverage_control_93_all; canonical missing_lod22 IDs |
| appendix run noise | docs/W3_2b_roofer_repeatability_noise.csv | all rows |
| appendix old-canonical harness comparison | docs/W2_1c_success_rates.csv; docs/W3_1_threshold_position.csv; docs/W3_2c_* | coverage_controlled_93 and Section 6 rows |
| McNemar assembly table | docs/W3_2c_canonical_paired_status.csv | coverage_control_population=yes; *_reason=missing_lod22_geometry |

Figure source mapping is listed in `captions.md`; copied figures keep their original filenames in the caption text or source path.
