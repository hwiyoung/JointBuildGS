# DIM v1 Classification Stats

- Run ID: t4_classify_20260612_120320
- Input DIM LAZ: data/work/mvs/dim/dim_v1.laz
- Output classified LAZ: data/work/classify/dim_v1_classified.laz
- CRS assertion: EPSG:25832
- DIM point count before classification: 43,942,554
- LoD2 GroundSurface footprints parsed: 12,049
- LoD2 GroundSurface footprints overlapping DIM bounds: 8,064
- Classification method: PDAL filters.smrf ground=2 other=1, then filters.overlay sets non-ground points inside LoD2 footprints to building=6.
- ALS handling: source ALS files were not modified; existing classifications were counted for verification only.
- Plan view PNG: docs/figs/dim_v1_classification_plan.png
- Run config: runs/t4_classify_20260612_120320/config.yaml
- Run versions: runs/t4_classify_20260612_120320/versions.txt

## DIM Classified Counts

| Class | Label | Points | Share |
|---:|---|---:|---:|
| 1 | unclassified | 8,652,857 | 19.691% |
| 2 | ground | 11,262,067 | 25.629% |
| 6 | building | 24,027,630 | 54.680% |

## ALS Existing Classification Verification

| File | Total points | Ground(2) | Building(6) | Other classified |
|---|---:|---:|---:|---:|
| 690_5335.laz | 20,697,252 | 7,357,806 | 6,924,891 | 6,414,555 |
| 690_5336.laz | 21,428,108 | 7,118,191 | 6,766,881 | 7,543,036 |
| 691_5335.laz | 20,182,679 | 7,979,333 | 6,649,140 | 5,554,206 |
| 691_5336.laz | 22,797,949 | 7,609,223 | 6,241,373 | 8,947,353 |

## lasinfo output

    lasinfo laspy-backed 0.1
    file name: /workspace/data/work/classify/dim_v1_classified.laz
    LAS version: 1.4
    point data format: 3
    number of point records: 43942554
    min x y z: 687815.690 5335223.920 438.400
    max x y z: 692967.610 5338416.550 827.330
    bounding box width x depth: 5151.920 3192.630
    bounding box area: 16448174.350 square meters
    point density: 2.671576 points per square meter
    scale factor x y z: 0.010 0.010 0.010
    offset x y z: 0.000 0.000 0.000
    coordinate reference system: EPSG:25832
