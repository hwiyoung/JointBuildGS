# P1 Result Output Feasibility Matrix

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

## Artifact-chain feasibility

| Layer | Required object | Existing evidence | Status | Before execution |
|---|---|---|---|---|
| `G_native` | lossless GS state and provenance | stage2 checkpoint schema and tests | READY core / PARTIAL diagnostics | Add CRS/datum/gravity, split, input, prior-confidence, and extraction binding. |
| `S_extracted` | point/mesh surface with method lineage | direct fusion and Fusion W1 TSDF/mesh implementations | PARTIAL | Freeze one common adapter and non-GT crop/association rule. |
| `P_Roofer` | class 2/6 LAS/LAZ + method-specific `R_derived` | exception-bound E5/C001 occupied-cell path and digest-pinned Roofer capability | PARTIAL | Establish and test a reference-independent common rule across C1–C5. |
| `H_LoD2` | Roofer-generated semantic model | CityJSON/CityJSONSeq output | PARTIAL | Add trusted CityGML conversion if CityGML is required. |
| `A_acceptance` | continuous metrics + G0–G4 | component metrics and contract definitions | PARTIAL | Implement versioned writer/evaluator; thresholds remain deferred. |

## Required output set

| Output | Contract location | Feasibility | Evidence/gap |
|---|---|---|---|
| Sheet A — method/input/provenance | result contract `:105-127` | PARTIAL | Fields are defined; no C1–C5 generator exists. |
| Sheet B — artifact inventory | `:129-145` | PARTIAL | Exact hash/bytes utilities and receipts exist, but no campaign aggregation. |
| Sheet C — building×method metrics | `:147-171` | PARTIAL | Individual metrics exist; common grain and missingness writer absent. |
| Sheet D — acceptance/transitions | `:173-188` | PARTIAL | Formulae defined; boolean gate artifact and thresholds absent. |
| `building_method_metrics.parquet` | `:228-303` | MISSING as artifact/writer | Schema only. |
| `building_acceptance_gates.csv` | `:304-323` | MISSING as artifact/writer | Definitions only. |
| C4-vs-C3/C5-vs-C3 transition table | `:325-364` | PARTIAL | Computable once the gate table exists. |
| CityJSON | source and Roofer paths | READY | Must retain output/provenance hashes. |
| CityGML | fixed repo/runtime search | MISSING | No trusted serializer/converter. |
| val3dity report | wrappers and tools image | PARTIAL | Separate environment required. |
| cjval report | fixed repo/runtime search | MISSING | No path found. |

## Gate feasibility

| Gate | Continuous/structural evidence | Current status |
|---|---|---|
| G0 generated | output existence, terminal failure receipts | PARTIAL: available per older paths, no unified writer |
| G1 schema/semantic | CityJSON semantics; cjval required by new contract | PARTIAL: CityJSON available, cjval missing |
| G2 geometry/topology | val3dity wrappers and edge diagnostics | PARTIAL: tools route exists, common receipt absent |
| G3 roof structure | plane correspondence, completeness/correctness/F1, boundary distances | PARTIAL: calculations exist, numerical criterion deferred |
| G4 geometric accuracy | RMSXY/RMSZ/Hausdorff | PARTIAL: calculations exist, numerical criterion deferred |

`PASS_usable = G0 ∧ G1 ∧ G2 ∧ G3 ∧ G4` is a contract definition, not a P1
result. P1 does not set thresholds or produce building verdicts.

## Qualitative pilot lineage

The v5 qualitative pilot is `READY` as a frozen artifact:

- PDF and manifest bytes were rehashed.
- Git manifest records all declared outputs rehashed and
  `canonical_evidence_claim=false`.
- Its config and wrapper pin inputs, images, Roofer digest, output contracts,
  read-only/no-network behavior, and `scientific_verdict:null`.

It is only `PARTIAL` for the new program because it uses a P0 DIM point cloud
and a supplied footprint rather than the new common `R_derived`/C1–C5 path.
It may be cited as capability and visual-lineage evidence, not as new
five-condition scientific evidence.

## Split and matrix feasibility

The result schema correctly requires P2 and P3 to share one
development+validation pool, and P4 to run the frozen C1–C5 matrix for the
first time on every held-out building. Actual feasibility is `UNKNOWN` until
Gate S0 freezes `E_paired`, mode, spatial groups, and cost. Under
`STRATIFIED_SAMPLE`, no all-eligible coverage claim is permitted without a
later census.

## P1 proposal

The documentation set is suitable for human review. Data/P2 readiness,
criteria, split mode, and scientific verdict remain unapproved.
