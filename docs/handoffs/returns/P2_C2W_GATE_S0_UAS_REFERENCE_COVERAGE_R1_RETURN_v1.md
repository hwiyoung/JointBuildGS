# Codex-to-Work Return  Gate S0 UAS Reference Coverage R1 v1

## Return metadata

- handoff_id: `P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1`
- task_id: `P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1`
- offered commit: `ac828f0017ee6bebc9c282d17adcc61bfffb3ce3`
- accepted/source commit: `da24ba68123ced5b4b95efd558688e92b9c9e086`
- output commit: `SELF`
- verified/blocked receipt commit: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- closed receipt commit: `PENDING_SEPARATE_300_EVENT`
- proposed technical status: `BLOCKED_TECHNICAL_REPRODUCIBILITY_VALIDATION`
- Gate S0 decision: `null`
- P2 performance: `PROHIBITED`
- scientific_verdict: `null`

## Answer first

The outcome-free calibration completed its first checkpointed calculation and increased
the independent-UAS-supported candidate set from 10 to 72 buildings. That does not
make the main P2 experiment ready. The 72 candidates collapse to only nine
tile/shared-reference groups with sizes `47, 7, 5, 5, 4, 1, 1, 1, 1`. Held-out has
10 buildings in only two groups. The precommitted scope is therefore
`PILOT_ONLY_REFERENCE_SCOPE`, and the recommended Gate action is
`BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`.

A mandatory second-process completed-ledger reuse check failed before any scientific
source reopen. The first process wrote checkpoint records containing the serialization
metadata field `digest_method`; `Checkpoints._load()` reconstructs the same records
without that field, so an exact dict-list comparison rejects an otherwise identical
ledger. Promotion uses the same validator and was not attempted. This is a technical
reproducibility failure and is correctly closed through `200-blocked.json`, not
`200-verified.json`.

## Outcome-free result

- canonical `U_target`: 199
- `E_paired` technical candidate: 72
- split building counts: development 51, validation 11, held-out 10
- independent groups: 9
- split group counts: development 5, validation 2, held-out 2
- largest group: 47/72 = 65.3% (contract maximum 10%)
- held-out largest group: 5/10 = 50% (contract maximum 20%)
- all-candidate `n_eff` at rho 0.05: 28.051948
- held-out `n_eff` at rho 0.05: 8.333333
- confirmatory minimum held-out groups: FAIL (2 observed, 20 required)
- overall and held-out group criteria: FAIL
- claim scope: `PILOT_ONLY_REFERENCE_SCOPE`
- Gate recommendation: `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`

The local-plane proposal produced 177 patches and 20,520 score cells. Of 177 patches,
99 intersect multiple canonical buildings and one intersects six eligible buildings.
Patch-connected transitivity is therefore material, not bookkeeping: the 72 buildings
must not be treated as 72 independent evaluation samples.

## Scientific isolation

Patch membership was frozen from the exact compact UAS grid before loading the
199-row candidate ledger. All unchanged per-cell and global-plane limits were
enforced. Independent review found global RMSE, maximum residual and local/global
normal diagnostics within their frozen limits. Every candidate ledger row records
`held_out_outcome_accessed=false`; no C5 or LoD2 geometry, ALS/MVS roof result,
performance output, quality score, Fusion W1 or `R_ext` was accessed by reference
construction or claim planning.

The result generalizes only, if separately approved as a pilot, to the achieved
reference-covered candidate subset. It does not justify a primary efficacy or
population/generalization claim over all 199 buildings.

## Read, hash and duplicate-work accounting

Each compact input had one known-successful same-stream read/digest pass:

- 3,023,643-byte grid: min 1, max 1, prior unknown attempts 0
- 3,140-byte predecessor checkpoint: min 1, max 1, prior unknown attempts 0
- 56,719-byte predecessor eligibility ledger: min 1, max 1, prior unknown attempts 0
- raw UAS reads: 0
- separate grid hash passes: 0
- first-process exact in-memory algorithm replays: 1
- second-process scientific source reopens before failure: 0
- R1/Images.zip/OPF.zip rehashes: 0

The failed second invocation stopped at completed-ledger envelope comparison before
`capture_exact`. No threshold sweep, candidate-count targeting, raw-source replay or
performance computation occurred.

## Exact external evidence

External namespace:
`artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/`

- `control/execution_ledger_v1.json`: 11,268 bytes,
  SHA-256 `cdf41594f1c218aa1c60206b9a6c070e5222f00da8149796151b15385f1f6bec`
- `freeze/technical_summary_v1.json`: 5,434 bytes,
  SHA-256 `2ac13fe6edd8227bdfae3f49ae17723fdc057ce58b2ce647dce62c4c445607c7`
- `freeze/candidate_ledger_v1.csv`: 83,814 bytes,
  SHA-256 `7f5759739a473952b4d3826b09c83ec3c2c4e0b68148a51405eb22609cec9b41`
- `analysis/claim_scope_v1.json`: 9,937 bytes,
  SHA-256 `cceac670f9ab27b87cf09ac198fd236d44e8b215f85e13f3f2d11e63f03bb8eb`
- `reference/patch_summary_v1.csv`: 96,539 bytes,
  SHA-256 `8a4379bdc7c58f7470fa37163f5471160601eb0475a86178054e47c5714ea3d0`
- `reference/patch_association_qa_v1.csv`: 7,078 bytes,
  SHA-256 `1dc618a400d795c139b504041321f0ea1676a75f3a3814ae8efeb868351ea93c`

These existing add-once artifacts and checkpoints must not be edited, deleted,
renamed or regenerated. Git promotion did not occur because its validator correctly
encounters the same normalization defect.

## Independent reviews

- scientific isolation and claim scope: the 72-building evidence is internally
  coherent and leakage-free within the reviewed artifacts, but independence is
  insufficient and P2 confirmatory performance remains blocked.
- Gate-minimal path: no split reassignment can repair a universe containing only nine
  independent groups; do not tune thresholds or patches again.
- reproducibility: remote read-only inspection confirmed six of six checkpoint records become byte-for-byte equal after restoring the single omitted `digest_method` field; attempts remain 1/1 and the second invocation opened no scientific source.

## Exact blocker and next bounded task

The exact defect is a normalization mismatch between `Checkpoints.write()` and
`Checkpoints._load()`: ledger checkpoint records written in process one contain
`digest_method`, while reloaded records contain only
`ordinal/stage/path/bytes/sha256`. Payload bytes, checkpoint chain and scientific
result are not contradicted.

The sole recommended next task is
`P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1`:

1. DRAFT on the Work Host first.
2. Use one checkpoint-record serializer for write and reload, restoring historical
   `digest_method: same_stream_as_add_once_serialization`, and add an exact
   write-to-new-instance reload regression test.
3. Add a recovery-only verification/promotion mode bound to the historical
   `da24ba68123ced5b4b95efd558688e92b9c9e086` operation. It must fail closed on
   mismatch and must not call `capture_exact` or `SourceAttempts.start`.
4. Verify every existing checkpoint, payload and ledger digest without opening or
   hashing the grid, predecessor checkpoint, predecessor eligibility ledger or any
   other scientific source. Preserve attempt counts 1/1 and min=max=1.
5. Reuse the existing result exactly; no segmentation, eligibility, split, power or
   source calculation may run again.
6. Promote the existing evidence and report
   `PILOT_ONLY_REFERENCE_SCOPE` /
   `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`.
7. Return writer ownership through a correct verified recovery chain.

Until that bounded recovery and a separate human Gate decision, Gate S0 remains
blocked and C1-C5 performance is unauthorized. `scientific_verdict` remains `null`.
