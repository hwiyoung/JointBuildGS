# P1 Surface Extraction Audit

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- primary roofprint policy: `R_derived`
- external `R_ext`: not accessed, not executed, not approved
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Candidate adapters

| Adapter | Evidence | Narrow status | Campaign status | Contract note |
|---|---|---|---|---|
| Rendered-depth direct fusion | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1167-1390` | READY | PARTIAL | Median/expected depth, alpha/range filtering, backprojection, per-view voxel uniqueness, min observations, and SOR are implemented for a locked E5/C001 setting. |
| C001/E5 occupied-cell `R_derived` candidate | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1449-1555`; lock `phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase3_lock.json:50-59`; test intent `tests/e5_c001/test_e5_c001_s3ap_phase3.py:512-518` | PARTIAL | PARTIAL | The roofprint polygon function uses a global 0.5 m occupied-cell union and emits class 2/6 LAS without directly opening a supplied footprint. Upstream ground-region lineage uses the approved C001/E5 `GroundSurface` XY exception; current test import also fails. |
| P0 exception-bound construction | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase0_baselines.py:6-10,440-500,731-758,807-825` | PARTIAL | PARTIAL | Provides another occupied-cell/class-2/6 implementation, but clips/fills using supplied footprint geometry and is not data/reference-independent. |
| True TSDF/mesh extraction | `phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_tsdf_20260726.py:428-579,980-1162` | READY | PARTIAL | Open3D TSDF, mesh component handling, surface sampling, CRS/datum receipts exist but are bound to protected Fusion W1 inputs. |
| Historical “TSDF” driver | `scripts/stage3_readout/tum_mob_tsdf_extract.py:1-10,47-60,87-180` | PARTIAL | PARTIAL | It performs voxel direct fusion and defaults to LoD2 footprint boxes; production eligibility is prohibited under the honest-arm contract. |
| Historical GT building assignment | `scripts/stage3_readout/run_stage3.py:107-151,240-255` | READY | PARTIAL | The diagnostic works as written, but GT bbox/scene assignment makes production eligibility prohibited. |

## `R_derived` conclusion

`R_derived` is not missing as an algorithm candidate. An occupied-cell
roofprint construction and class-2/6 adapter exist for E5/C001, but their
upstream ground mask is tied to the approved local `GroundSurface` XY
exception. The current test entry point also imports a nonexistent sibling
implementation (`tests/e5_c001/test_e5_c001_s3ap_phase3.py:21-26`). The
narrow route and campaign readiness are therefore `PARTIAL`. The following
have not been frozen for the complete development+validation pool:

- one method ID, source hash, image digest, parameters, and expected schema;
- non-GT building association and crop/terrain/buffer rules;
- coordinate frame, offset, CRS, vertical datum, and gravity binding;
- identical derivation algorithm across C1–C5 with method-specific polygon
  hashes;
- failure retention as G0 rather than post-hoc building exclusion;
- coverage, runtime, memory, and storage calibration.

## Direct fusion versus TSDF versus mesh sampling

These are distinct extraction choices and must not be conflated:

1. Direct rendered-depth fusion aggregates observed surface voxels.
2. TSDF integrates signed-distance evidence and extracts a mesh.
3. Mesh sampling creates a Roofer-compatible point representation.

The repository contains evidence for all three concepts, but under different
locks and data roles. P2 must compare or preselect the adapter before threshold
inspection, then freeze the chosen method. Active Fusion W1 cannot be modified
or silently promoted as the campaign adapter.

## Terrain, crop, and buffer requirements

The C1–C5 common protocol must derive all crop and roofprint geometry from the
method evidence, not LoD2/evaluation geometry. Terrain points may support the
once-estimated gravity and class-2 ground representation, but evaluation
labels, roof surfaces, roof type, LoD2 Z, and final roof models must remain
score-only. The approved C001/E5 `GroundSurface` XY exception is local to its
lock and is not a general policy.

## Output receipt minimum

For each building and condition, the extraction receipt should bind:

- native checkpoint/input hash and condition ID;
- extraction algorithm and exact parameters;
- source views and valid-view count;
- output point/mesh URI, bytes, SHA-256, count, bounds, and class inventory;
- CRS, vertical datum, local offset, gravity vector source;
- terrain/crop/buffer rule and whether any external geometry was opened;
- `R_derived` polygon URI/hash and derivation code/config hash;
- terminal status, including empty/no-evidence outcomes.

## Gate consequence

P1 may report the capability as `PARTIAL`, but Gate S0/P2 entry is blocked
until a campaign-wide adapter and non-GT association rule are frozen. `R_ext`
remains out of scope.
