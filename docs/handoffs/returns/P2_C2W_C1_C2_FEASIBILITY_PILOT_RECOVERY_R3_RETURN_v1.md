# Codex-to-Work Return — P2 C1/C2 feasibility pilot recovery R3 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1`
- source commit: `8346a1f40763a17b02f40e47dbe74c8102f0a76e`
- activation commit: `59c6b7f42b9444bf1bf92fe5e8c88d60c56d7513`
- offered commit: `f787a4220c9c77529eca519784e585f1e51b8b6f`
- accepted commit: `7b96d0211777da26d2ff4bc79d1a1be407958433`
- output commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- requested run_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-RUN-v1`
- completed_at: `2026-08-02T12:17:43+09:00`
- proposed technical status: `BLOCKED_FINALIZE_CITYJSONSEQ_HEADER_EMPTY_VERTEX_SHAPE`
- scientific_verdict: `null`

## Answer first

The exact R3 wrapper was invoked once. The zero-scientific preflight and the single
synthetic Roofer smoke passed. The wrapper then opened the five exact scientific
sources in one processing-and-digest stream each, froze the exact 51-building C1/C2
development association surface, and completed all seven unique Roofer execution
units once with no retries. It stopped in the committed `finalize` path before any
building-method metric row was serialized or promoted.

The first failure is:

```text
File "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/contract.py", line 1855, in finalize
  triangles[unit_id] = roof_triangles(store.path(unit["output_directory"]))
File "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/contract.py", line 1727, in roof_triangles
  vertices = _transformed_vertices(record, inherited)
File "scripts/p2_baselines/c1_c2_feasibility_pilot_v1/contract.py", line 1692, in _transformed_vertices
  raise RuntimeError("CityJSON vertex/transform shape is invalid")
RuntimeError: CityJSON vertex/transform shape is invalid
```

This is a committed finalize-reader defect, not a Roofer-process failure and not a
scientific C1/C2 result. Each of the seven native CityJSONSeq outputs starts with a
valid `CityJSON` header carrying a three-element `scale` and `translate` plus an
empty `vertices: []`, followed by one `CityJSONFeature` carrying the actual vertices.
`roof_triangles()` calls `_transformed_vertices()` on the header itself. NumPy
represents that empty list with shape `(0,)`, so the frozen `vertices.ndim != 2`
guard fails on the first C1 output before the feature record is scored.

The failed namespace is preserved without wrapper retry, manual finalize,
alternative score calculation, promotion or scientific salvage. The required
disposition is this blocked Return, an attestation-inheriting `200-blocked`, and a
direct-child `300-closed` returning writer ownership to Work Host.

## Lifecycle and ownership outcomes

- Read root `AGENTS.md` and the complete current canonical contract set
  `docs/research/00_*.md` through `06_*.md`; legacy `EXPERIMENT_PLAN.md` and
  `RESEARCH_CONTEXT.md` were not used as execution authority.
- Began clean at the exact prior R2 `300-closed` commit
  `a7828af5380c5070de92526b5c82249cb7be8e25`; the exact R3 external namespace was
  absent before fetch and again immediately before the wrapper invocation.
- Fetched and inspected the remote reviewed source, activation packet, offered event
  and prior R2 close before pull. Proved source `8346a1f4` → activation `59c6b7f4` →
  offer `f787a422`, with the offer a direct child of activation.
- Fast-forwarded only to the exact offer. Packet `status` and `user_approval` were
  each exactly `APPROVED_FOR_EXECUTION`, the packet bound the exact source and kept
  `scientific_verdict: null`, and the 000 scope/commit tuple was exact.
- Verified the direct original, non-nested source attestation at commit
  `896fe284bc4d496e6e9c79720f4e75396a41d0b2`, receipt SHA-256
  `705348ecde9d139254bdd24e59ed02312d5321c20f802649f1ce4ca19f5b9bda`, five records,
  and record identity
  `f63d5d4405157615d807d6babd4a9bf74a16ab13818193945ed9bbfc02532db3`.
- Created direct-child `100-accepted` at `7b96d021`; Docker validation passed before
  and after push without `--artifact-root`. Acceptance-time artifact/scientific
  full-read or hash passes were zero.
- Experiment Host remained the sole writer through execution and this Return. No
  protected repository path was modified.

## Zero-scientific preflight and synthetic smoke

- wrapper invocations: `1`
- zero-scientific preflight: `PASS_ZERO_SCIENTIFIC_PAYLOAD`
- preflight buildings/groups: `51 / 5`
- preflight scientific bytes read or hashed: `0`
- synthetic prepare calls: `1`
- synthetic Roofer attempts/retries: `1 / 0`
- synthetic input: `1,620` points, `55,307` bytes,
  SHA-256 `318feaba986dc21282d7ec9a81b89a39b336364d70a333ef8efcff26100a1a20`
- synthetic `R_derived`: `872` bytes,
  SHA-256 `db7fffae05394cee8d17f022b24b2e4041706ac48f84236f38e3aeb268eda88b`
- Roofer exit/records/CityObjects: `0 / 6 / 10`
- LoD2.2 geometries: `5`
- semantic surfaces: Roof `5`, Wall `20`, Ground `5`
- synthetic `G0_generated / G1_schema_semantic`: `true / true`
- synthetic G1 failures: `[]`
- synthetic G2: `null`, reason `CANONICAL_VALIDATOR_UNAVAILABLE`
- synthetic scientific bytes read or hashed: `0`
- synthetic scientific_verdict: `null`

The five synthetic labels remain an interface check only. They are not scientific
C3–C5 executions.

## Scientific execution and row state

The scientific-prepared ledger is `PREPARED` and binds the requested run/source,
the exact 51-building roster, and a 102-association surface:

- expected/prepared building-method associations: `102` (`51 C1 + 51 C2`)
- finalized building-method metric rows: `0 / 102`
- promoted rows/reports/manifests: `0`
- unique execution units: `7` (`1 C1 + 6 C2`)
- terminal operation ledgers: `7 / 7`
- unique Roofer attempts/retries: `7 / 0`
- operation-level `G0_generated=true`: `7 / 7`
- operation-level `G1_schema_semantic=true`: `7 / 7`
- operation-level G2: `null / 7`, reason `CANONICAL_VALIDATOR_UNAVAILABLE`
- duplicate Roofer calculations prevented: `94`
- association rows mapped to the seven exact operation units: `101`
- mapped-row Roofer reuses beyond the seven unique units: `94`
- association rows without an operation unit: `1`
- finalize calls: `1`, first call failed before row serialization
- promote calls: `0`

The sole association without an operation unit is C2 building
`DEBY_LOD2_4907183`, group `GROUP_37b5107f054e56e8`; its frozen association has
`component_id: null`, `operation_unit_id: null`, zero component/reference-cell
overlap and 14 score reference cells. Because finalize did not complete, no final
failure label or metric row was fabricated for it.

The seven operation-level G0/G1 outcomes establish only that the six C2 components
and one C1 component produced internally screened LoD2.2 output. They do not provide
51-by-2 building-level scores. In particular:

- C1 technical output: one shared execution unit, Roofer process complete,
  provisional internal G0/G1 `true/true`; no finalized C1 row or continuous score.
- C2 technical output: six unique execution units, each Roofer process complete,
  provisional internal G0/G1 `true/true`; one building has no operation unit; no
  finalized C2 row or continuous score.
- C1-versus-C2 geometry metrics, group-balanced summaries and representative
  building comparison: unavailable.
- G3, G4 and `PASS_usable`: unavailable/null by contract.

C1 remains `SELF_REFERENCE_UPPER_BASELINE`; it is not pooled or ranked as an
independent-reference accuracy condition. No scientific comparison or C3 strategy
inference is made from this failed finalize.

## Scientific source read/hash ledger

Exactly five approved scientific sources were opened by the wrapper. Each was read
and digested in its existing processing stream exactly once:

| Source | Bytes | Full read-and-digest passes |
|---|---:|---:|
| C1 grid | 3,023,643 | 1 |
| C1 checkpoint | 3,140 | 1 |
| C2 common-base derivative | 7,327,590 | 1 |
| C2 checkpoint | 2,951 | 1 |
| independent UAS reference candidate cells | 3,785,261 | 1 |
| **Total** | **14,142,585** | **5** |

Reference processing streamed 20,520 global source-cell rows, retained 16,290 unique
development source cells and 21,714 building-cell associations, and retained/scored/
promoted zero non-development rows. The UAS reference association role stayed
`SCORE_IDENTITY_ONLY_AFTER_FROZEN_CONDITION_GEOMETRY`; every execution-unit ledger
records `reference_or_bbox_used_to_derive_input: false` and
`stable_id_used_to_derive_input: false`.

The wrapper did not mount or comprehensively rehash R1, `Images.zip`, `OPF.zip`, raw
UAS LAZ or raw `dim_dense`. Ledger counts are:

- raw `dim_dense` accesses: `0`
- validation payload accesses: `0`
- held-out payload accesses: `0`
- C3/C4/C5 scientific inputs/execution: `0`
- LoD1/LoD2 scientific input accesses: `0`
- Fusion W1 or `R_ext` accesses: `0`
- closure-time scientific source rereads/rehashes: `0`

Before the later header-shape exception, the committed `roofer_point_counts` path
also performed one verified read of each of the seven derived operation LAS files.
It did not repeat that read for the 101 mapped building-method associations. There
is no OS syscall audit; nonaccess to the prohibited archives is evidenced by exact
mount isolation, committed source-attempt ledgers and the zero access counters.

## Preserved failure namespace and no-repeat contract

External namespace:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/`

Metadata-only inventory after the first failure found 521 regular files,
55,170,598 content bytes and zero symlinks. No comprehensive post-failure payload hash
was performed. The namespace contains the smoke PASS ledger, scientific-prepared
ledger, frozen associations/components/execution units, seven add-once operation
started/result/final ledgers and seven native CityJSONSeq outputs. It does not contain
`control/finalized_v1.json`, any promotion control, or a committed/promoted R3 result
manifest/report.

The exact R3 wrapper, smoke, science preparation, Roofer operations and finalize must
not be called again for this identity. The 94 reuse decisions plus the seven
add-once operation records prevent repeated Roofer calculations; the first finalize
failure remains terminal for this namespace. Do not manually reshape the header,
call `finalize`, derive metrics, publish a synthetic finalized ledger, or run the
committed promotion path. A correction requires a new reviewed source, handoff/task/
run/result identity and external namespace.

A separate non-hash ownership review found the protected R2 namespace unchanged at
eight regular files and 13,242 bytes, all with timestamps before R3 execution. No
post-R3-start baseline artifact write existed outside the exact R3 namespace.

## Independent post-run reviews

- Scientific scope, C1 self-reference and leakage:
  `PASS_THROUGH_FAILED_FINALIZE / COMPLETED_102_ROW_RESULT_NOT_EVALUABLE`. The reviewer
  confirmed exactly 102 frozen development associations, 51 roster IDs, five groups,
  reference opening only after condition geometry/`R_derived` freeze, all 228 jobs
  with reference/bbox and stable-ID input flags false, and zero validation, held-out,
  C3–C5, LoD1/LoD2 geometry, Fusion W1 or `R_ext` access. C1 remains self-reference
  and must not be pooled. All 13 verdict fields found in the namespace are null.
- Two-host ownership, protected paths and receipt chain:
  `PASS_FOR_HONEST_BLOCKED_CLOSURE`. The reviewer confirmed the exact source →
  activation → offer → accepted chain, direct non-nested five-record attestation
  reuse, unchanged protected Git paths and R2 namespace, and that Experiment Host
  remains writer until a separate `200-blocked` and direct-child `300-closed` return
  ownership.
- Reproducibility, exact paths, stream/hash counts and no-repeat:
  `PASS_THROUGH_UNIQUE_OPERATIONS / BLOCKED_AT_FIRST_FINALIZE`. The reviewer confirmed
  the exact run/source/images/config, one smoke, five single source streams, seven
  unique one-attempt/no-retry Roofer operations, 94 prevented duplicates, no
  `attempt_02`, the exact header-shape traceback, and absence of finalized or promoted
  outputs. The reviewer explicitly prohibits manual row reconstruction.

All three reviews were mutually independent and read-only. They made no repository
edit and did not rerun the wrapper, call finalize/promotion or hash the five original
scientific sources.

## Changes, deviations and limitations

- Added only this required blocked Return in the R3 allowed repository scope.
- Did not edit frozen implementation, config, tests, packet, scientific outputs,
  protected evidence or any predecessor receipt/namespace.
- Did not create success-only compact metrics/manifests/reports because the committed
  finalize and promotion commands did not complete.
- Deviated from the success lifecycle only at the exact stop condition: the requested
  102 finalized rows and promoted technical report are unavailable.
- The internal G0/G1 screen is provisional; canonical G2 is unavailable, and G3/G4/
  `PASS_usable` remain outside this task.
- Development groups remain highly imbalanced (`47/1/1/1/1`). Even a future complete
  development run is descriptive, not confirmatory or population-generalizable.

## Recommended next action

After direct-child `300-closed` returns writer ownership, Work Host may prepare a new
reviewed source that treats a CityJSONSeq header with valid transform and empty
vertices as an inheritance record rather than a feature geometry, adds an exact
native-Roofer multi-record finalize regression test, and offers a completely new
add-once recovery identity. This R3 run and namespace must remain closed. No C1/C2
comparison or C3 strategy should be derived from this Return.

`scientific_verdict` remains `null`.
