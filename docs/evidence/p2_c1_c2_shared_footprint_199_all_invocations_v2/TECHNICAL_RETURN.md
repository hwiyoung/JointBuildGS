# C1/C2 shared-footprint 199동 전체 Roofer 호출 기술 반환

- Task: `P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2`
- Decision: `DEC-P1-019`
- Date: 2026-08-05
- Population: fixed `U_target=199`
- Building-method rows: 398
- Roofer invocations: 398 (`C1_L_upper=199`, `C2_MVS=199`)
- Shared control: exact LoD2 `GroundSurface` XY and stable ID only
- LoD2 Z / input `RoofSurface` use: false
- Scientific verdict: `null`

## Why v2 supersedes the v1 count

The v1 diagnostic converted minimum class-6/ground checks into pre-invocation gates.
It invoked Roofer for only 107 LiDAR rows and 123 MVS rows, so its zero process-failure
count did not describe all 199 buildings. v2 keeps those checks as diagnostics only.
Every row receives a valid LAS, including a zero-point LAS for an empty source crop,
and every row is passed to the exact pinned Roofer container.

## Technical counts

| Condition | Population | Roofer calls | Process exit/output complete | Actual LoD2.2 | No LoD2.2 |
|---|---:|---:|---:|---:|---:|
| C1 current UAS LiDAR | 199 | 199 | 199 | 106 | 93 |
| C2 recovered current MVS | 199 | 199 | 199 | 126 | 73 |

Paired building accounting:

- LoD2.2 from both C1 and C2: 96
- C1 only: 10
- C2 only: 30
- neither: 63

The process-complete count is not the usable Roofer geometry count. Roofer can return
exit code 0 and a CityJSONSeq record without a LoD2.2 Solid. The technical availability
count above therefore uses actual LoD2.2 geometry presence.

## Input-diagnostic audit

| Condition | Diagnostic rows | LoD2.2 despite diagnostic | Empty source crop | Insufficient class-6 |
|---|---:|---:|---:|---:|
| C1 | 92 | 2 | 46, all no-LoD2.2 | 46, of which 2 LoD2.2 |
| C2 | 76 | 7 | 24, all no-LoD2.2 | 51, of which 7 LoD2.2 |

C2 also had one insufficient-ground-candidate diagnostic row and it produced no
LoD2.2. Since nine diagnostic rows produced actual geometry, the diagnostic threshold
must not be used as a future Roofer invocation gate.

## Deterministic execution lock

- Project image ID: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- Roofer image: `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`
- Roofer image ID: `sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba`
- Roofer jobs: 1
- Normalized 398-row geometry digest:
  `954dbfb23d71160d163918d0088b5551434b9922354601fb313a257e34b68faa`

Volatile CityJSON metadata and runtime attributes are excluded from the normalized
geometry digest. Transform, vertices, geometry boundaries, semantics, status,
classification diagnostics, input hash, and shared-footprint hash are retained.

## Artifact pointers

- Result JSONL:
  `phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2/results/building_method_results_v1.jsonl`
- Status CSV:
  `phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2/results/building_method_status_v1.csv`
- Finalized receipt:
  `phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2/control/finalized_v1.json`
- Reproducibility manifest:
  `phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2/control/reproducibility_geometry_manifest_v1.json`

No numerical `PASS_usable`, confirmatory inference, or scientific verdict is made in
this technical return.
