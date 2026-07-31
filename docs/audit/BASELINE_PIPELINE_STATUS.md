# P1 Baseline Pipeline Status

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- evidence time: `2026-07-31T16:50:24+09:00`
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Five-condition readiness

| Condition | Required route | Repository evidence | Status | Blocking gap |
|---|---|---|---|---|
| `C1_L_upper` | Current UAS/Drone LiDAR → class 2/6 Roofer | Live 2024 ULS assets; reusable class validator in `scripts/pilot_1wave/pilot_1wave_scoring.py:1197-1226`; locked Roofer examples | PARTIAL | Raw ULS sample classifications are class 0, vertical datum is undeclared in the headers, and no approved C1 classification/ground/roof adapter exists. |
| `C2_MVS` | Current-image MVS → class 2/6 Roofer | Live Pix4Dmatic point cloud; separate imagery/OPF→COLMAP/OpenMVS DIM lineage; P0 Roofer adapters | PARTIAL | The exact C2 source, classification, crop, `R_derived`, and output receipt are not frozen. |
| `C3_GS_image` | Images → image-only GS → extraction → Roofer | GS core, rendered-depth direct fusion, exception-bound E5 occupied-cell adapter | PARTIAL | Common development+validation extraction method/version and building assignment are not frozen. |
| `C4_GS_lidar_prior` | Same images/base as C3 + Existing ALS prior | Existing ALS tiles and active prior-related code/receipts | PARTIAL | The new C4 prior equation, confidence field, adapter, loss weights, and derivative independence contract are deferred; C1 ULS must not be reused as C4. |
| `C5_GS_lod1_prior` | Same images/base as C3 + independent LoD1 prior | Contract only | MISSING | No independent LoD1 payload was found in the fixed Git + canonical artifact search; deriving it from scored LoD2 would leak reference geometry. |

## Sensor-role separation

`L_upper` and `P_LiDAR` are not interchangeable:

| Property | Current UAS/Drone LiDAR | Existing ALS |
|---|---|---|
| Candidate files | `TUM_Downtown_ULS_20241217_manual.laz`, `TUM_Downtown_ULS_20241217_nadir.laz` | `690_5335.laz`, `690_5336.laz`, `691_5335.laz`, `691_5336.laz` |
| Campaign/header date | 2024-12-17 campaign; LAS creation 2024-12-23 | LAS creation 2022-06-16 |
| Role | C1 direct high-quality Roofer input candidate | C4 coarse/existing prior candidate |
| CRS/datum evidence | UTM zone 32 WKT/GeoKeys; vertical datum not declared in headers | Official ETRS89/UTM32 + DHHN2016 evidence; raw header has no CRS VLR |
| Classification observation | fixed three-chunk sample was class 0 only | fixed sample contained classes 2, 6, 20, 22 |
| Density observation | manual/nadir gross-bbox density is not directly comparable to tiled ALS density | approximately 20.18–22.80 points/m² per 1 km² tile |
| Contract risk | class 2/6 conversion and datum registration unresolved | age, lower density, temporal change, coverage, and prior confidence unresolved |

The 2022 ALS versus 2024-12-17 UAS separation supports distinct asset identity,
but does not by itself prove independence or fitness. C1/C4 comparison and Gate
S0 remain blocked until survey lineage, overlap, temporal-change handling, and
derivative independence are frozen.

## Existing capability inventory

| Capability | Exact evidence | Narrow capability | Campaign status |
|---|---|---|---|
| gsplat model/render | `src/stage2/model.py:86-200`; `src/stage2/renderer.py:23-151` | Native C3 base | PARTIAL |
| Direct rendered-depth fusion | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1167-1390` | Locked E5/C001 extraction | PARTIAL |
| Exception-bound `R_derived` candidate | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1449-1555`; lock `phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase3_lock.json:50-59`; static test intent `tests/e5_c001/test_e5_c001_s3ap_phase3.py:512-518` | E5/C001 occupied-cell union and class 2/6 LAS | PARTIAL; upstream ground masks use the approved C001/E5 GroundSurface-XY exception and the test import path is broken |
| TSDF/mesh extraction | `phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_tsdf_20260726.py:428-579,980-1162` | Active Fusion W1 only | PARTIAL |
| Roofer invocation | `phases/p2-gsjso/scripts/fusion_w1/fusion_w1_readout_v1_20260726.py:4203-4538` | Digest/argv/receipt handling | PARTIAL |
| CityJSON serialization | `src/stage3/citygml_export.py:23-163` | CityJSON 2.0 Solid | READY |
| CityGML serialization | repo and live-environment fixed search | None found with provenance-bound test | MISSING |
| val3dity | `scripts/stage3_readout/run_stage3.py:169-214` plus P0 tools image | Wrapper and historical execution evidence | PARTIAL |
| cjval | repo and live-environment fixed search | None found | MISSING |
| Continuous roof metrics | `scripts/input_and_alignment/tum2twin_rv1/prepare_tum2twin_rv1_cache.py:320-364`; `phases/p0-audit/scripts/15_roofer_quality_w3.py:401-466` | RMSXY/RMSZ, plane and boundary metrics | READY |
| Unified G0–G4 evaluator | research contract only | No versioned building×method generator | MISSING |

## Current Fusion W1 relationship

Fusion W1 demonstrates that several components can operate under exact locks.
It also uses an approved first-wave LoD2 `GroundSurface` XY exception in some
paths. That exception is not the new general `R_derived` rule, and its
footprints must not migrate into C1–C5 without a separate approval. P1 did not
execute or alter Fusion W1.

## Immediate gate consequences

- `C1`: blocked by ULS class/datum/adapter contract.
- `C4`: blocked by prior definition, independence, and registration contract.
- `C5`: blocked by missing independent LoD1.
- `C2–C5`: blocked by common image/camera identity and the 962-image versus
  937-pose discrepancy.
- All conditions: blocked from Gate S0 by missing exact `E_paired`, split
  manifest, common `R_derived` campaign lock, compute/storage calibration, and
  integrated G0–G4 writer.
