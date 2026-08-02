# Codex-to-Work Return — P2 C1/C2 feasibility pilot recovery R2 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-v1`
- source commit: `846bc2638ac84854e588fb7ac1aa7a6f38ce06b6`
- activation commit: `c5c2c872d51354d6c5916da47f4fc3c1170c3e0a`
- offered commit: `f57ca0dc93abcddf7db10d370a549a1eef7ecff7`
- accepted commit: `fc52b791a0e64e78651c8b8c0d933f7ccd2e7d10`
- output commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- requested run_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-RUN-v1`
- completed_at: `2026-08-02T11:30:05+09:00`
- proposed technical status: `BLOCKED_PRE_SCIENTIFIC_SYNTHETIC_SMOKE_STRICT_SCREEN`
- scientific_verdict: `null`

## Answer first

The exact R2 wrapper was invoked once. Its zero-scientific preflight passed, but the
single synthetic Roofer smoke attempt failed the required strict LoD2.2/schema screen.
Roofer itself exited `0` and serialized five synthetic buildings; all five were
point-cloud-unusable LoD `0` placeholders rather than LoD2.2 outputs. The wrapper
stopped before scientific mounts, processing streams, buildings or rows.

This is implementation/synthetic-fixture evidence only. It is not a C1/C2 result,
not a scientific Roofer failure, and not evidence for a C3 strategy. The exact failed
namespace is preserved without rerun, salvage, finalization or promotion. The correct
closure is this Return, an artifact-attestation-inheriting `200-blocked`, and a
direct-child `300-closed` returning writer ownership to Work Host.

## Lifecycle and authority outcomes

- Read root `AGENTS.md` and the complete current canonical contract set
  `docs/research/00_*.md` through `06_*.md`; legacy `EXPERIMENT_PLAN.md` and
  `RESEARCH_CONTEXT.md` were not used as execution authority.
- Started clean at the prior recovery's closed commit
  `663d62b10b1a94fd670ce99d86c5a9a171794f0b`, fetched `origin/main`, and inspected
  the exact remote packet, source and `000-offered` before pull.
- Proved reviewed source `846bc263` → activation `c5c2c872` → offer `f57ca0dc`, then
  fast-forwarded only to the exact offer.
- Confirmed the prior recovery namespace remained absent and its closed Return
  reported no science and `0/102` rows. Its packet, Return and receipts were not
  edited or reopened.
- Verified direct original source attestation commit
  `896fe284bc4d496e6e9c79720f4e75396a41d0b2`, Git 300-receipt SHA-256
  `705348ecde9d139254bdd24e59ed02312d5321c20f802649f1ce4ca19f5b9bda`, and
  canonical five-record identity
  `f63d5d4405157615d807d6babd4a9bf74a16ab13818193945ed9bbfc02532db3`.
- Verified exact local project image
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
  and immutable Roofer image ID
  `sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba`.
- The authority parser, exact-source drift check, shell syntax, executable Git mode,
  five attested input sizes and empty R2 namespace all passed before acceptance.
- Docker zero-scientific preflight passed with 51 buildings, five groups,
  exact development roster identity and
  `scientific_payload_bytes_read_or_hashed=0`.
- Created, committed and pushed add-once `100-accepted` at `fc52b791`; Docker
  validation passed before and after push without `--artifact-root`. It binds the
  direct original closed attestation and records zero payload rehashes.

## Synthetic smoke outcome

- wrapper invocations: `1`
- synthetic prepare calls: `1`
- synthetic Roofer attempts: `1`
- synthetic retries: `0`
- Roofer exit code: `0`
- source footprints submitted / processed / serialized: `5 / 5 / 5`
- CityJSONSeq records: `6` (one header plus five features)
- CityObjects: `5`
- LoD2.2 geometries: `0`
- semantic surface counts: `{}`
- strict result: `SYNTHETIC_G0_G1_REQUIREMENTS_NOT_MET`
- `G0_generated`: `false`
- `G1_schema_semantic`: `false`
- G1 failure: `SEMANTIC_VALUES_SHAPE_OR_INDEX_INVALID`
- geometry ring diagnostic: `true`, class
  `DIAGNOSTIC_RING_INDEX_SANITY_NOT_G2_NOT_VAL3DITY`
- `G2_geometry_topology_valid`: `null`
- G2 null reason: `CANONICAL_VALIDATOR_UNAVAILABLE`
- scientific_verdict: `null`

Every synthetic feature reports `rf_pointcloud_unusable=true`,
`rf_pc_select=_HIGHEST_YET_INSUFFICIENT_COVERAGE`, `rf_nodata_frac=1.0`,
`rf_pt_density=0.0`, `rf_roof_type=no points`, zero roof planes and only LoD `0`
geometry. `rf_success=true` is process-level and is not LoD2.2 or G0 success.

The frozen synthetic fixture creates four class-6 points at the four roofprint
vertices and four surrounding class-2 points for each polygon. The immutable Roofer
image classified the resulting point support as insufficient. This supports the
bounded diagnosis `SYNTHETIC_FIXTURE_TOOL_CONTRACT_INSUFFICIENT_COVERAGE`; it does
not establish a deeper scientific or production-input cause. The semantic-shape
failure is downstream of the LoD `0` output with no semantic surfaces.

## Scientific execution and row completeness

- synthetic-smoke PASS ledger: `absent`
- scientific prepare calls: `0`
- scientific mount openings: `0`
- scientific processing-and-digest streams: `0`
- unique scientific Roofer operations: `0`
- development buildings opened/processed: `0 / 51`
- C1 `SELF_REFERENCE_UPPER_BASELINE` rows: `0 / 51`
- C2 `INDEPENDENT_UAS_SCORE_ONLY` rows: `0 / 51`
- total result rows: `0 / 102`
- G3, G4 and `PASS_usable`: `null / not available`
- C1-versus-C2 quantitative or qualitative comparison: `not available`
- finalize calls: `0`
- promote calls: `0`

The five labels in the synthetic fixture include C1 through C5 only to exercise the
zero-payload tool interface. They are not scientific C3/C4/C5 execution or data
access. No scientific failure structure can be compared between C1 and C2.

## Preserved external evidence

External namespace:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r2_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R2-v1/`

It contains exactly eight regular files, 13,242 content bytes and zero symlinks:

| Path | Bytes | Status |
|---|---:|---|
| `control/synthetic_inputs_v1.json` | 531 | `READY_ZERO_SCIENTIFIC_PAYLOAD` |
| `smoke/attempt_01.started.json` | 166 | `STARTED`, retry false |
| `smoke/attempt_01.result.json` | 1,159 | `FAILED` |
| `smoke/work/input.las` | 1,587 | synthetic only |
| `smoke/work/r_derived.geojson` | 872 | synthetic only |
| `smoke/work/runtime.log` | 1,410 | complete process log |
| `smoke/work/roofer.log.json` | 2,695 | complete Roofer log |
| `smoke/work/out/000001_000001.city.jsonl` | 4,822 | five LoD `0` features |

There is no `scientific_started`, `scientific_prepared`, freeze/execution-unit,
condition, operation, metric, finalized or promotion record. No technical result
manifest or promoted experiment report was fabricated after the failed smoke.

## Scope, leakage and read ledger

- acceptance-time scientific payload full-read/hash passes: `0`
- closure-time scientific payload full-read/hash passes: `0`
- exact scientific-file checks before smoke: existence/regular-file metadata only
- scientific payload bytes read or hashed: `0`
- R1 large inputs, `Images.zip`, `OPF.zip`, raw UAS LAZ, raw `dim_dense`, or
  inherited large-input content access: `0`
- validation outcome access: `0`
- held-out outcome access: `0`
- C3/C4/C5 scientific execution or input access: `0`
- LoD1/LoD2 scientific input access: `0`
- Fusion W1 access: `0`
- `R_ext` access: `0`
- repeated source stream, duplicate scientific calculation or duplicate Roofer
  operation: `0`
- scientific_verdict: `null`

## No-repeat contract

The exact namespace has a durable started marker, failed result and output directory,
but no PASS ledger. The source restart guard therefore rejects any second synthetic
action as `synthetic smoke is partial or failed; duplicate execution is prohibited`.
No scientific retry policy was entered.

Preserve all eight external files byte-for-byte. Do not rerun the wrapper, synthetic
prepare/decision/verification, Roofer smoke, scientific prepare, finalize or promote.
Do not create a synthetic PASS ledger, result rows, technical manifest or experiment
report for this R2 identity. Do not pass the artifact root to the `200` or `300`
validator, and do not reread or rehash the five accepted scientific records during
closure. Any remediation requires a new reviewed source, handoff/task/run/result
identity and external namespace.

## Independent post-run reviews

- Scientific scope/leakage: `PASS_FOR_TRUTHFUL_BLOCKED_CLOSURE`; confirmed the exact
  G0/G1/G2 evidence, zero scientific access, `0/102` row meaning, synthetic-label
  limitation and prohibition on C1/C2 comparison or C3 inference.
- Ownership/receipt chain: `PASS_FOR_HONEST_BLOCKED_CLOSURE`; confirmed clean
  accepted ownership and required Return → `200-blocked` → direct-child
  `300-closed` artifact-inheriting sequence.
- Reproducibility/path/no-repeat: `PASS_FOR_TRUTHFUL_BLOCKED_CLOSURE`; confirmed the
  exact eight-file inventory, no scientific/finalized/promoted state, single attempt,
  fail-closed restart guard and zero payload rereads at closure.

The reviews made no repository edits and did not rerun the task or hash scientific
payloads.

## Recommended next action

After `300-closed` returns writer ownership, Work Host may prepare a new reviewed
source that corrects and end-to-end tests the synthetic fixture/tool contract, then
offer a completely new add-once handoff and namespace. This R2 chain and namespace
must remain closed. No C1/C2 comparison or C3 strategy can be derived from this run.

`scientific_verdict` remains `null`.
