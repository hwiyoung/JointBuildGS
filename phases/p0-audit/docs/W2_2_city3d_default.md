# W2-2 City3D Default Reconstruction

- Run ID: `w2_2_city3d_default_20260612_175449`
- Run directory: `runs/w2_2_city3d_default_20260612_175449`
- Input A: ALS LAZ tiles from `data/raw/als/`.
- Input B: `data/work/w2/dim_v1_classified_z_minus0p174.laz`.
- Footprints: `data/work/w2_city3d/footprints_scene_aoi.geojson` converted from the same W2 GPKG subset.
- City3D defaults: `Method::min_points=40`, `Method::pixel_size=0.15`; source commit `c9299efe61625f03a78245683eaa155a9670df0e`.
- City3D input point filter: ASPRS class `6` per footprint.
- City3D execution: `CITY3D_WORKERS=8`, `CITY3D_TIMEOUT_SEC=240`.

## Outputs

- Model set: `runs/w2_2_city3d_default_20260612_175449/models/`
- val3dity reports: `runs/w2_2_city3d_default_20260612_175449/val3dity/`
- Building status CSV: `runs/w2_2_city3d_default_20260612_175449/building_reconstruction_status.csv`
- Paired CSV: `docs/W2_2_city3d_paired_status.csv`
- Success rates: `docs/W2_2_city3d_success_rates.csv`
- Roofer/City3D 2x2: `docs/W2_2_roofer_city3d_2x2.csv`

## Execution Notes

- The City3D container builds the upstream command-line example only; GUI/Qt targets are excluded.
- Each building uses one footprint GeoJSON and one clipped PLY containing class 6 points.
- Resume mode reuses existing non-empty OBJ outputs and existing timeout/failure logs.
- Per-building timeouts and reconstruction failures are kept in `building_reconstruction_status.csv` as failure reasons.

## Success Rates

| population | n | ALS success | DIM success | both success | ALS only | DIM only | both fail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full_199 | 199 | 4/199 (2.0%) | 1/199 (0.5%) | 0/199 (0.0%) | 4/199 (2.0%) | 1/199 (0.5%) | 194/199 (97.5%) |
| both_attempted_179 | 179 | 4/179 (2.2%) | 1/179 (0.6%) | 0/179 (0.0%) | 4/179 (2.2%) | 1/179 (0.6%) | 174/179 (97.2%) |
| coverage_controlled | 93 | 1/93 (1.1%) | 1/93 (1.1%) | 0/93 (0.0%) | 1/93 (1.1%) | 1/93 (1.1%) | 91/93 (97.8%) |

## Coverage-Controlled 2x2

| input | n | Roofer success | City3D success |
| --- | ---: | ---: | ---: |
| ALS | 93 | 84/93 (90.3%) | 1/93 (1.1%) |
| DIM | 93 | 75/93 (80.6%) | 1/93 (1.1%) |

## City3D Failure Reasons

| reason | ALS | DIM |
| --- | ---: | ---: |
| `city3d_reconstruction_failed` | 0 | 36 |
| `city3d_timeout` | 23 | 38 |
| `pointcloud_unusable_low_points` | 0 | 5 |
| `pointcloud_unusable_no_points` | 1 | 52 |
| `success` | 4 | 1 |
| `val3dity_invalid` | 171 | 67 |
