# W2-1b Paired Roofer Analysis

- Source run: `runs/w2_1_roofer_default_20260612_152729`
- Paired unit: `building_id` from `building_reconstruction_status.csv`.
- Final success definition: W2-1 `status=success`, which includes Roofer LoD2.2 output and val3dity validity.
- Comparison population: buildings where both ALS and DIM produced a Roofer feature attempt, i.e. neither side is `missing_roofer_output`.

## Paired Categories

| Category | Full 199 | Both-attempted 179 |
|---|---:|---:|
| `both_success` | 89 | 89 |
| `ALS_only` | 74 | 74 |
| `DIM_only` | 13 | 13 |
| `both_fail` | 23 | 3 |

## Recomputed Success Rates

| Population | ALS final success | DIM final success | ALS Roofer-stage LoD2.2 output | DIM Roofer-stage LoD2.2 output |
|---|---:|---:|---:|---:|
| Full 199 | 163/199 (81.9%) | 102/199 (51.3%) | n/a | n/a |
| Both-attempted 179 | 163/179 (91.1%) | 102/179 (57.0%) | 178/179 (99.4%) | 115/179 (64.2%) |

## Reason Crosstab

| als_reason | `missing_lod22_geometry` | `missing_roofer_output` | `pointcloud_unusable_no_planes` | `pointcloud_unusable_no_points` | `success` | `val3dity_invalid` | `row_total` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| missing_roofer_output | 0 | 20 | 0 | 0 | 0 | 0 | 20 |
| pointcloud_unusable | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| success | 16 | 0 | 2 | 44 | 89 | 12 | 163 |
| val3dity_invalid | 0 | 0 | 0 | 2 | 12 | 1 | 15 |

## Missing Roofer Output Diagnosis

- ALS `missing_roofer_output`: 20
- DIM `missing_roofer_output`: 20
- Same ID set on both inputs: yes.
- ID issue: not observed; all 20 IDs are present in the footprint source and scene CSV.
- Footprint geometry issue: not observed by simple checks; rings are closed and have positive area.
- Box diagnosis: all 20 footprints intersect the Roofer AOI box but have centroids outside it and are not fully inside it.
- Action for paired comparison: exclude these 20 AOI-edge buildings from the both-attempted population.
- Future fix if edge buildings are needed: rerun Roofer with an expanded/no `--box`, then clip/evaluate to AOI after reconstruction.

## ALS Roofer-Stage Failure Memo

- ALS Roofer-stage failures: 21 buildings.
- 20 are the shared AOI-edge `missing_roofer_output` buildings above.
- 1 is `pointcloud_unusable`: Roofer produced a record but skipped 3D geometry because local pointcloud coverage was insufficient.
- ALS val3dity-invalid buildings are kept in the paired CSV, but they are geometry-validity failures after Roofer output, not part of this 21-building Roofer-stage memo.

## Failure Gallery

- Selected DIM `missing_lod22_geometry` examples: high-density/no-nodata, high-nodata, and highest plane-count cases.
- `docs/figs/w2_1b_dim_missing_lod22_DEBY_LOD2_104586480.png`
- `docs/figs/w2_1b_dim_missing_lod22_DEBY_LOD2_4907175.png`
- `docs/figs/w2_1b_dim_missing_lod22_DEBY_LOD2_4907510.png`

## Files

- Paired table: `docs/W2_1b_paired_status.csv`
- Reason crosstab: `docs/W2_1b_reason_crosstab.csv`
- Missing Roofer exclusion list: `docs/W2_1b_missing_roofer_exclusions.csv`
- ALS Roofer-stage failure memo: `docs/W2_1b_als_roofer_failure_memo.csv`
