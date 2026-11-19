# inputs_sizes

2.2: input sizes per method x prior x cell, read from the receipts under OUT (scenes/, prior/, prep/geogs/, da3/geogs/, lgdm/); missing field = 없음

scientific_verdict: null

| method | prior | cell | train_views | test_views | initial_points | note | prior_cell_mesh_vertices | prior_cell_mesh_faces | surface_vertices | surface_faces | prior_depth_maps | protection_cloud_points | da3_views | da3_batches | cdgs_s | composite_depth_maps | change_area_m2 | prior_surface_vertices | prior_surface_faces |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2DGS | 없음 | 0 | 308 | 41 | 119,304 | TU1 cell scene SfM points, origin 0 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 |
| 2DGS | 없음 | 1 | 471 | 54 | 164,609 | TU1 cell scene SfM points, origin 0 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 |
| 2DGS | 없음 | 2 | 544 | 53 | 168,260 | TU1 cell scene SfM points, origin 0 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 |
| 2DGS | 없음 | 3 | 324 | 38 | 131,905 | TU1 cell scene SfM points, origin 0 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | ALS | 0 | 308 | 41 | 52,854 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 1,097,900 | 2,182,085 | 1,097,900 | 1,096,643 | 349 | 1,000,000 | 308 | 26 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | ALS | 1 | 471 | 54 | 50,716 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 1,378,984 | 2,739,341 | 1,378,984 | 1,637,951 | 525 | 1,000,000 | 471 | 40 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | ALS | 2 | 544 | 53 | 60,367 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 1,716,372 | 3,406,436 | 1,716,372 | 1,422,579 | 597 | 1,000,000 | 544 | 46 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | ALS | 3 | 324 | 38 | 48,836 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 1,475,778 | 2,928,188 | 1,475,778 | 1,532,158 | 362 | 1,000,000 | 324 | 27 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | LoD2 | 0 | 308 | 41 | 84,673 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 13,863 | 4,621 | 13,863 | 3,845 | 349 | 1,000,000 | 308 | 26 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | LoD2 | 1 | 471 | 54 | 73,238 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 30,042 | 10,014 | 30,042 | 7,728 | 525 | 1,000,000 | 471 | 40 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | LoD2 | 2 | 544 | 53 | 91,499 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 13,683 | 4,561 | 13,683 | 3,856 | 597 | 1,000,000 | 544 | 46 | 없음 | 없음 | 없음 | 없음 | 없음 |
| GeoGS | LoD2 | 3 | 324 | 38 | 65,031 | prior depth maps = all cell images (train + test), as the previous GeoGS scenes | 29,346 | 9,782 | 29,346 | 7,485 | 362 | 1,000,000 | 324 | 27 | 없음 | 없음 | 없음 | 없음 | 없음 |
| CDGS | ALS | 0 | 308 | 41 | 114,970 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 308 | 없음 | 없음 | 없음 | 17.03 | 없음 | 없음 | 없음 | 없음 |
| CDGS | ALS | 1 | 471 | 54 | 159,404 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 471 | 없음 | 없음 | 없음 | 19.32 | 없음 | 없음 | 없음 | 없음 |
| CDGS | ALS | 2 | 544 | 53 | 165,537 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 544 | 없음 | 없음 | 없음 | 21.45 | 없음 | 없음 | 없음 | 없음 |
| CDGS | ALS | 3 | 324 | 38 | 128,020 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 324 | 없음 | 없음 | 없음 | 22.66 | 없음 | 없음 | 없음 | 없음 |
| CDGS | LoD2 | 0 | 308 | 41 | 114,970 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 308 | 없음 | 없음 | 없음 | 17.03 | 없음 | 없음 | 없음 | 없음 |
| CDGS | LoD2 | 1 | 471 | 54 | 159,404 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 471 | 없음 | 없음 | 없음 | 19.32 | 없음 | 없음 | 없음 | 없음 |
| CDGS | LoD2 | 2 | 544 | 53 | 165,537 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 544 | 없음 | 없음 | 없음 | 21.45 | 없음 | 없음 | 없음 | 없음 |
| CDGS | LoD2 | 3 | 324 | 38 | 128,020 | WD campus SfM observations on the cell poses; points with >= 2 training observations in the expanded cell | 없음 | 없음 | 없음 | 없음 | 324 | 없음 | 없음 | 없음 | 22.66 | 없음 | 없음 | 없음 | 없음 |
| LGDM | ALS | 0 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 308 | 15,535.31 | 3,556,910 | 7,070,427 |
| LGDM | ALS | 1 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 471 | 15,535.31 | 3,556,910 | 7,070,427 |
| LGDM | ALS | 2 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 544 | 15,535.31 | 3,556,910 | 7,070,427 |
| LGDM | ALS | 3 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 324 | 15,535.31 | 3,556,910 | 7,070,427 |
| LGDM | LoD2 | 0 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 308 | 3,365.69 | 58,848 | 19,616 |
| LGDM | LoD2 | 1 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 471 | 3,365.69 | 58,848 | 19,616 |
| LGDM | LoD2 | 2 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 544 | 3,365.69 | 58,848 | 19,616 |
| LGDM | LoD2 | 3 | 없음 | 없음 | 없음 | judge / decide over the campus (819 training views), composite per cell; change area = campus total | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 없음 | 324 | 3,365.69 | 58,848 | 19,616 |
