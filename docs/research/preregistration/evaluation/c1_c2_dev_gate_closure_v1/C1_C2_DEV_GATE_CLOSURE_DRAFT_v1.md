# C1/C2 development G2–G4 closure DRAFT v1

- status: `USER_DIRECTED_PROVISIONAL_DEVELOPMENT_DIAGNOSTIC_CLOSURE`
- scope: sealed C1/C2 development 51 buildings only
- criterion candidate: `C1C5_CANON_v2_DEV_CLOSURE_CANDIDATE_v1`
- reconstruction / Roofer invocation: `0 / 0`
- validation / held-out access: prohibited
- scientific_verdict: `null`

## Purpose

This task closes the evaluator implementation gap without changing or rerunning the
sealed R3 reconstruction and Roofer outputs. It reads each unique sealed C2
CityJSONSeq at most once, reuses the already sealed R4 continuous metrics, and emits
one candidate gate row for each of the exact 51 × 2 development cells.

The output is not a final scientific result. The numerical G3/G4 values are an
outcome-free implementation candidate for human review. They do not change the
canonical rule that numerical thresholds remain provisional until a separate freeze.

If the candidate is later executed on the 51 C2 development rows, its G3/G4 rows
are only calibration input. A separate add-once calibration candidate must report
the development distributions, threshold sensitivity, candidate thresholds, and a
null scientific verdict. It is human-review input, not a frozen criterion; it may
not read validation or held-out data.

## Gate behavior

- `G0` and `G1` are copied from the sealed R4 row.
- `G2` uses val3dity 2.6.0 with the recorded
  `overlap=-1`, point-to-plane planarity `0.01 m`, normal planarity `20°`, and snap
  `0.001 m` settings. Image `jointbuildgs-p0-tools:t0` is fixed by image ID
  `sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8`.
  Each of the six unique C2 CityJSONSeq streams is read once and piped to the
  official `val3dity ... stdin` interface. A unit is valid only when every feature
  line is valid; that conservative unit verdict is inherited by associated buildings.
- `G3` diagnostic uses sealed development UAS patch cells as reference planes and the semantic
  Roofer `RoofSurface` polygons as predicted planes. Matching is performed on the
  frozen 1 m grid, requires at most 15° sign-invariant normal difference and at
  least 0.5 bilateral support overlap. Candidate thresholds are completeness and
  correctness ≥ 0.8, quality ≥ 2/3, and over/under-segmentation ≤ 0.25. It cannot
  become a gate until concave surfaces, small planes, overlaps, and many-to-many
  matching are validated.
- `G4` diagnostic reuses, without recomputation, the sealed vertical coverage, height MAE,
  RMSZ, RMSXY, surface RMSE and surface p95. Candidate thresholds are coverage
  ≥ 0.8, MAE/RMSZ/RMSXY/surface RMSE ≤ 1 m, and surface p95 ≤ 2 m. Normal metrics
  remain report-only. The frozen contract has `absolute_z_metrics_enabled=false`,
  so these absolute-distance values cannot become a gate in this closure.
- `C1_L_upper` remains a self-reference upper baseline. Its G3, G4, and PASS fields
  remain null even though its descriptive continuous values remain available.
- `PASS_usable` remains null. G2 can now be observed, but G3 and G4 are diagnostic-only.

## Duplicate-work prevention

The execution key is the sealed `operation_unit_id`, not a building ID. Shared C2
components are parsed once and reused across associated development buildings.
Scoring does not call Roofer, reconstruction, or continuous-metric code. A preexisting
output path fails closed; sealed inputs are read-only and are never overwritten.

## Activation blocker

The pinned six-unit G2 run is technically executable. A positive `PASS_usable`
remains blocked until a validated G3 matcher and a G4 acceptance rule consistent
with `absolute_z_metrics_enabled=false` are separately frozen. The current output
is diagnostic input for C3 planning, not a scientific verdict.
