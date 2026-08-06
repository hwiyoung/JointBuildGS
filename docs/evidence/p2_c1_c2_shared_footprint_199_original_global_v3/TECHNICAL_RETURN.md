# C1/C2 Original-global Roofer v3 Technical Return

- Task: `P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3`
- Decision: `DEC-P1-019-ORIGINAL-GLOBAL-CORRECTION-20260806`
- Execution state: `TECHNICAL_COMPLETE_WITH_EXPLICIT_MISSINGNESS`
- Scientific verdict: `null`
- Official `PASS_usable`: `null`

## What changed

The formal C1/C2 comparison now follows the historical Roofer scene-wide pattern.
Each condition used one scene-wide class-2/6 cloud, the same 199-feature
`R_shared` GroundSurface-XY source, and one Roofer invocation. The v1/v2 external
per-building crops and 398 Roofer calls remain historical diagnostics only.

Both conditions used the same historical classification recipe: PDAL SMRF assigns
ground class 2 and a shared-footprint overlay assigns non-ground points within each
footprint to building class 6. No voxel sampling or quality-driven retry was used.
Roofer 1.0.0 reconstruction parameters remained at defaults; `--jobs 1` was an
execution determinism control.

## Input preparation

| Condition | Classified scene points | Class 2 | Class 6 | Classified LAZ SHA-256 |
|---|---:|---:|---:|---|
| C1 current UAS LiDAR | 177,968,343 | 66,654,555 | 72,299,289 | `17c036a340bc46539754db7e57f711af9be05aab46427a4e186e3b144e0c671c` |
| C2 recovered common-base MVS | 43,848,711 | 11,734,146 | 23,449,221 | `0326c0982dc1512317b4e7eeb7d28fc86581372e326fd6eb5acf1fdc2a6d9912` |

The shared 199-feature footprint source SHA-256 is
`5f9b703b06676db4400f6568fc3db315e319913f98ba491e98922eb747e4488a`.

## Roofer and conformance results

| Condition | Roofer calls | Process exit | Output features | LoD2.2 present | val3dity-valid LoD2.2 | Internal-RMSE median | Internal-RMSE p90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 current UAS LiDAR | 1 | 0 | 179 | 107 | 99 | 1.599 m | 3.289 m |
| C2 recovered common-base MVS | 1 | 0 | 179 | 114 | 103 | 1.503 m | 3.426 m |

The paired count with val3dity-valid LoD2.2 in both conditions is 86. This is a
post-output descriptive intersection, not the pre-outcome `E_paired` population.

## Explicit missingness

| Reason | C1 | C2 |
|---|---:|---:|
| Missing Roofer feature | 20 | 20 |
| `rf_pointcloud_unusable=true` | 66 | 50 |
| Feature present but LoD2.2 missing | 6 | 15 |
| LoD2.2 present but val3dity invalid | 8 | 11 |
| val3dity-valid LoD2.2 | 99 | 103 |

The same 20 buildings are missing in both conditions. All 199 footprints intersect
the historical Roofer AOI, but 47 cross its boundary and the 20 missing buildings
are a subset of those boundary-crossing footprints. Consequently, these 20 cases
cannot yet be interpreted as LiDAR/MVS evidence failures. A separate user decision
is required before either (a) retaining the exact historical AOI for strict legacy
comparison or (b) expanding the AOI to fully contain all 199 footprints for the
new census.

## Quality interpretation boundary

This run records G0 candidates, val3dity for G2, and Roofer self-diagnostics. It
does not establish G3 roof-structure fidelity, G4 positional accuracy, or
`PASS_usable`. `rf_rmse_lod22` measures fit to the condition input and is not an
independent truth metric. Numerical G3/G4 thresholds remain pending a separate
pre-result freeze using reference uncertainty, blind review, application needs,
and sensitivity analysis.

## Canonical artifacts

- Runtime root: `phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3`
- Final receipt: `control/finalized_v3.json`
- Building-level JSONL: `results/building_method_results_v3.jsonl`
- Building-level CSV: `results/building_method_status_v3.csv`
- Per-condition assembled CityJSON and val3dity reports: `work/<condition>/`
