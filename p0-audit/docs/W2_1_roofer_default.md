# W2-1 Roofer Default Reconstruction

- Run ID: `w2_1_roofer_default_20260612_152729`
- Run directory: `runs/w2_1_roofer_default_20260612_152729`
- AOI: `scene_aoi.gpkg` bounding box, EPSG:25832.
- Footprints: `data/work/w2/footprints_scene_aoi.gpkg` from `docs/scene_aoi_buildings.csv` (199 buildings).
- Input A: ALS validation LAZ tiles from `data/raw/als/`.
- Input B: `data/work/classify/dim_v1_classified_z.laz` with the +0.174 m median DIM-ALS residual removed (`Z := Z - 0.174 m`) as `data/work/w2/dim_v1_classified_z_minus0p174.laz`.
- Roofer parameters: defaults, with only `--id-attribute building_id` and `--box` for AOI plumbing.

## Outputs

- ALS CityJSON: `runs/w2_1_roofer_default_20260612_152729/cityjson/als_roofer.city.json`
- ALS val3dity report: `runs/w2_1_roofer_default_20260612_152729/val3dity/als_val3dity_report.json`
- DIM CityJSON: `runs/w2_1_roofer_default_20260612_152729/cityjson/dim_roofer.city.json`
- DIM val3dity report: `runs/w2_1_roofer_default_20260612_152729/val3dity/dim_val3dity_report.json`
- Building success/failure CSV: `runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv`

## Summary

| Input | Success | Failure | val3dity valid features | val3dity validity |
|---|---:|---:|---:|---|
| ALS | 163 | 36 | 164/179 | invalid |
| DIM | 102 | 97 | 166/179 | invalid |

## Failure Reason Counts

| Reason | ALS | DIM |
|---|---:|---:|
| `missing_lod22_geometry` | 0 | 16 |
| `missing_roofer_output` | 20 | 20 |
| `pointcloud_unusable` | 1 | 0 |
| `pointcloud_unusable_no_planes` | 0 | 2 |
| `pointcloud_unusable_no_points` | 0 | 46 |
| `success` | 163 | 102 |
| `val3dity_invalid` | 15 | 13 |
