# P1 Roofer and Evaluation Audit

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- Stage 3 policy: Roofer-style evidence-to-CityGML read-out without external roofprint
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Roofer input adapter

| Requirement | Evidence | Status |
|---|---|---|
| EPSG:25832 and class inventory validation | `scripts/pilot_1wave/pilot_1wave_scoring.py:1197-1226` | READY |
| Class 2 ground / class 6 building generation | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1427-1446,1518-1523` | READY |
| Exception-bound occupied-cell roofprint | `phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase3.py:1449-1555`; lock `phases/p2-gsjso/configs/e5_c001/e5_c001_s3ap_phase3_lock.json:50-59` | PARTIAL: polygon construction is occupied-cell-derived, but upstream ground masks use the C001/E5 GroundSurface-XY exception |
| Digest-pinned Roofer invocation/receipt | `phases/p2-gsjso/scripts/fusion_w1/fusion_w1_readout_v1_20260726.py:4203-4538` | READY |
| Campaign-wide C1–C5 adapter | fixed search | MISSING |

The existing capability is strong enough to reuse, but the new program still
needs one common adapter/config/receipt schema. UAS LiDAR C1 cannot enter
Roofer directly because its raw sample classification is class 0. Existing
ALS class 2/6 is not a substitute for the current UAS C1 branch.

## Output serialization

| Output | Evidence | Status | Restriction |
|---|---|---|---|
| Roofer CityJSON/CityJSONSeq | locked P0/P2 invocation paths | READY | Bind exact image digest, arguments, input LAS, roofprint, and output hash. |
| Custom CityJSON 2.0 Solid | `src/stage3/citygml_export.py:23-163` | READY | This is CityJSON, despite the module filename. |
| CityGML | repo and live image fixed search | MISSING | No trusted provenance-bound serializer/converter/test was found. |
| `val3dity` | wrapper `scripts/stage3_readout/run_stage3.py:169-214`; P0 tools environment | PARTIAL | Not installed in the main live image; wrapper reports not-found. |
| `cjval` | repo and live image fixed search | MISSING | No callable path or test found. |

Until a trusted converter and validation receipt exist, outputs must be named
CityJSON or Roofer-generated LoD2.2 semantic models, not CityGML.

## GT separation

The following historical paths are not honest-arm production paths:

- `scripts/stage3_readout/run_stage3.py:107-151,240-255` uses GT scene boxes
  and building metadata to assign primitives.
- `scripts/stage3_readout/tum_mob_tsdf_extract.py:21-60` uses selected LoD2
  footprint boxes for default extraction.
- The approved C001/E5 LoD2 `GroundSurface` XY exception remains limited to
  its frozen lock. It cannot become the new campaign roofprint.

Evaluation LoD2 may be opened only after the method output, building identity,
and `R_derived` artifact are frozen. Method failure remains G0 failure and may
not trigger post-hoc exclusion.

## Evaluation capability

| Metric/gate evidence | Code | Status |
|---|---|---|
| Roof-plane precision/recall/F1 and boundary Chamfer/Hausdorff | `phases/p0-audit/scripts/15_roofer_quality_w3.py:401-466` | READY |
| Completeness/correctness/F1, RMSZ/RMSXY, roof Hausdorff | `scripts/input_and_alignment/tum2twin_rv1/prepare_tum2twin_rv1_cache.py:277-364` | READY |
| Symmetric mesh Hausdorff and semantic/face aggregates | `scripts/stage3_readout/eval_citygml.py:1-16,278-293,350-403,431-486` | PARTIAL: historical oracle diagnostic opens GT, uses GT assignment, and samples without a fixed seed |
| val3dity validity/error extraction | `scripts/stage3_readout/run_stage3.py:169-214` | READY |
| Building×method C1–C5 schema | `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md:228-303` | READY |
| G0–G4 definitions | `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md:304-323,366-428` | READY |
| Integrated schema writer/gate evaluator | fixed search | MISSING |
| Numerical G3/G4 thresholds | research contract | UNKNOWN; decision state is `DEFERRED` |

Individual measurements are implemented, but the campaign acceptance chain is
`PARTIAL`. Existing R_v1 tables are provisional and do not have the new
building×C1–C5 grain.

## Required evaluation receipt

Each row must bind condition/building/split IDs, all artifact hashes,
`R_derived` hash, reference version, matcher/metric version, units,
missingness reason, val3dity/cjval reports, continuous G3/G4 measurements, and
boolean G0–G4 values. C1/C2 non-applicable learning/prior fields must be null
with a reason, never zero.

## Gate consequence

Roofer, CityJSON, val3dity wrappers, and continuous metric components are
reusable. CityGML, cjval, the integrated C1–C5 writer, and thresholds are not
ready. No `PASS_usable` or scientific success/failure determination is made.
