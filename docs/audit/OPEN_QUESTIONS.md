# P1 Open Questions and Downstream Blocks

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- P1 documentation: `READY_FOR_REVIEW`
- scientific_verdict: null

These are findings for Work Host and human review. P1 did not resolve them by
guessing and does not request repeated user judgment inside the already
approved audit.

## Blocks Gate S0 or P2

| ID | Status | Question/evidence gap | Blocked claim/action | Required next evidence |
|---|---|---|---|---|
| P1-Q01 | UNKNOWN | Which 937 of 962 images form the common current-image base, and why are 25 unposed/excluded? | C2–C5 common input and per-building view support | Deterministic image/camera ledger and coverage report |
| P1-Q02 | UNKNOWN | Which UAS LiDAR file is C1: manual, nadir, or a frozen merge; and what vertical datum/registration applies? | C1 identity/readiness and C1/C4 comparison | Exact source/derivative hashes, merge/de-duplication and overlap/coverage-union rule, survey metadata, transform and residual receipt |
| P1-Q03 | MISSING | Where is the provenance-bound UAS class-2/6 adapter? Raw bounded samples are class 0. | C1 Roofer input | Frozen classification/ground procedure, derivative lineage, class inventory, and per-building coverage |
| P1-Q04 | PARTIAL | How is Existing ALS encoded as a C4 prior, with confidence and independence from reference/current UAS? | C4 implementation and comparison | ALS-specific adapter/config/loss/interface and independence receipt |
| P1-Q05 | MISSING | Where is an independent LoD1 prior? | C5, `E_paired`, full matrix | Exact URI/bytes/hash/CRS/datum/lineage and leakage guard |
| P1-Q06 | UNKNOWN | What exact AOI, `U_target`, `E_paired`, split mode, IDs, spatial groups, seed, and sample size are frozen? | Gate S0 and all P2/P3/P4 assignments | Immutable Gate S0 manifest after P1 review |
| P1-Q07 | PARTIAL | Which extraction adapter and campaign-wide `R_derived` method/version apply identically across C1–C5, and what once-estimated gravity is bound? | Common Stage 3 comparison | Common lock, tests, method-specific polygon hashes, terrain-MVS normal source, gravity estimator/vector/hash, and wall-normal perpendicularity test |
| P1-Q08 | MISSING | Where are the building×method writer, G0–G4 evaluator, Sheet A–D generator, and missingness schema? | Auditable final matrix | Versioned CPU-tested aggregation path |
| P1-Q09 | MISSING | What trusted CityJSON→CityGML serializer and cjval route will be used? | CityGML/G1 conformance claims | Pinned tool/image, converter, validator, hashes, tests |
| P1-Q10 | UNKNOWN | What G3/G4 numerical criteria, matching rules, units, and aggregation are frozen? Decision state is `DEFERRED`. | `PASS_usable` | P2 pre-held-out criterion approval |
| P1-Q11 | UNKNOWN | What are the bounded per-condition compute/storage costs and retention policy? | Exhaustive-vs-sampled feasibility | Non-held-out calibration bound to exact recipes |

## Program-governance questions

| ID | Status | Finding | Consequence |
|---|---|---|---|
| P1-Q12 | PARTIAL | `AGENTS.md` still names `RESEARCH_CONTEXT.md` and `EXPERIMENT_PLAN.md` as durable definitions; the new Decision Log does not supersede them and leaves four-vs-five-condition relationship pending. | Human must decide the long-term canon relationship before scientific execution; R2 P1 authority itself remains valid. |
| P1-Q13 | PARTIAL | `HANDOFF_INDEX.md` and portions of the roadmap still state R2 offer-pending/pre-activation state. | Work Host should reconcile live status in a later authorized documentation packet; P1 scope did not allow these edits. |
| P1-Q14 | PARTIAL | The qualitative v5 pilot is byte-verifiable but uses P0 DIM and a supplied footprint. | Keep it as frozen capability/visual-lineage evidence; do not promote it to new C1–C5 evidence. |
| P1-Q15 | PARTIAL | Active Fusion W1 contains useful TSDF/Roofer/metric capabilities under protected, sometimes exception-specific locks. | Reuse requires a later adapter decision; P1 must not alter or relabel active results. |

## Resolved for P1

- R2 activation and write ownership were valid.
- Artifact absence/uncertainty is a P1 finding, not an activation blocker.
- Current UAS/Drone LiDAR and Existing ALS are different assets and roles.
- An occupied-cell `R_derived` candidate exists in E5/C001, but its upstream
  ground mask is exception-bound and its test entry is stale; a
  campaign-wide reference-independent adapter remains unresolved.
- `R_ext` remains out of scope.
- P2/P3 share development+validation; P4 first opens all held-out buildings.
- P1 may propose only `READY_FOR_REVIEW`; scientific and phase verdicts remain
  human decisions.

## Recommended Work Host sequence

1. Cross-review the nine audit documents and this issue ledger.
2. Reconcile the durable-canon relationship and stale status indexes in a new
   authorized packet.
3. Resolve Q01–Q11 with a Gate S0 preparation packet that preserves active
   Fusion W1 and does not touch held-out data.
4. Only then request the user to freeze AOI/split/mode/criteria decisions that
   are explicitly reserved for human approval.
