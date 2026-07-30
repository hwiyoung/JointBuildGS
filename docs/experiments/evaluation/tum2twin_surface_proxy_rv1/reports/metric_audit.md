# Metric and execution audit — `20260728_2327`

## Overall assessment: Share with caveats

- Execution integrity: **trusted**
- Analysis grain: one row per canonical building, 178 rows / 178 unique IDs
- Run branch: `exp/fusion-w1`
- Run commit: `6f7366626cc491567926c64d96f8f028485559e0`
- Config: `configs/input_and_alignment/tum2twin_rv1_20260728_2327.yaml`
- Completed: `2026-07-28T15:05:23.153532+00:00` (UTC timestamp; start state is recorded in KST)
- No GS learning, Roofer rerun, ICP, or distance metric recomputation was performed in post-analysis.

## Actual distance directions

- **Precision@0.2:** each reconstructed DIM class-6 voxel centroid → nearest ALS reference class-6 voxel centroid; fraction ≤0.2 m.
- **Recall@0.2:** each ALS reference class-6 voxel centroid → nearest reconstructed DIM class-6 voxel centroid; fraction ≤0.2 m.
- `reconstruction_to_reference_p95_m` is the surface-proxy-to-reference direction used by reliability.
- `reference_to_reconstruction_p95_m` is the reference-to-surface-proxy direction used by completeness.
- The implementation uses SciPy `cKDTree` point nearest neighbours, not triangle/mesh nearest-surface queries.

## Units, CRS and sampling

- Coordinates and distances: metres; CRS: EPSG:25832 for all 178 rows.
- Footprint crop buffer: 1.0 m.
- Voxelization: 0.1 m centroid per occupied voxel.
- Directional cap: 250,000 points after voxelization; deterministic linspace selection. 11 buildings were capped.
- Worker count: 1; ICP: disabled for all rows; normal estimation: disabled.
- `surface_thickness_p90_m` is a 0.2 m XY-cell Z-span p90. It is excluded from reliability because slope, walls and multiple surfaces are not separated.

## Missingness

| Metric | Missing n | Missing rate |
|---|---:|---:|
| `surface_recall_0p2m` | 43 | 24.2% |
| `reference_to_reconstruction_p95_m` | 43 | 24.2% |
| `surface_precision_0p2m` | 43 | 24.2% |
| `reconstruction_to_reference_p95_m` | 43 | 24.2% |
| `surface_thickness_p90_m` | 43 | 24.2% |
| `roof_plane_f1` | 64 | 36.0% |
| `rmsz_m` | 64 | 36.0% |

All four required surface proxy metrics are simultaneously available for 135/178 buildings. The 43 missing rows have zero reconstructed class-6 points; reference class-6 is present. Their pipeline record is `processing_status=success`, so execution success must not be confused with metric validity.

## Source immutability evidence

`run_metadata.source_data_modified=false`, `cache_manifest.source_files_unchanged=true`, and current size/mtime agree with the frozen snapshot:

| Source | Exists | Size match | mtime match |
|---|---|---|---|
| `docs/regression_input_snapshot.csv` | True | True | True |
| `results/tum_transfer/analysis/footprints_aoi.geojson` | True | True | True |
| `phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz` | True | True | True |
| `results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz` | True | True | True |
| `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv` | True | True | True |
| `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/cityjson/dim_roofer.city.json` | True | True | True |
| `phases/p0-audit/data/raw/lod2/690_5336.gml` | True | True | True |
| `phases/p0-audit/data/raw/lod2/690_5334.gml` | True | True | True |

This proves no observed size/mtime change across the recorded inputs; it is not a fresh full-file cryptographic rehash.

## Data-quality issues and minimum remediation

1. **High — 43/178 metric-invalid rows are counted as processing successes.** Downstream analyses must use `surface_proxy_metric_valid`, not `processing_status`. A metric-only rerun will not help; minimum recovery is upstream DIM class-6 classification/surface recovery for those IDs, then affected-ID metric rerun.
2. **Medium — “nearest surface” is a point-set proxy.** Keep the `surface_proxy` name. Only if an explicit mesh claim becomes necessary, minimally recompute the four directional metrics against frozen meshes using triangle nearest-surface distance.
3. **Medium — 11 capped buildings use an order-dependent deterministic spatial sample.** None of the selected candidates is capped. Recompute only capped IDs with a documented spatial sampler if they become decision-critical.
4. **Medium — thickness is not validated.** Do not include it in reliability until local plane separation or signed surface-normal thickness is implemented and tested.
5. **Low — population view counts are sparse.** Existing `views.csv` covers 9/178. Candidate eligibility was checked separately with the locked selector; do not generalize that count distribution.

No minimum geometry metric recalculation is required for the 135 valid buildings or the five selected candidates.

## Reproduction

Run `scripts/input_and_alignment/tum2twin_rv1/analyze_tum2twin_surface_proxy_rv1.py` inside the existing `jointbuildgs:dev` container with the completed run root and `post_analysis/` output directory. Then run `tests/test_tum2twin_surface_proxy_rv1_analysis.py`. The script reads frozen metrics and writes only post-analysis artifacts; it does not launch training, Roofer, ICP, or geometry-distance recomputation.
