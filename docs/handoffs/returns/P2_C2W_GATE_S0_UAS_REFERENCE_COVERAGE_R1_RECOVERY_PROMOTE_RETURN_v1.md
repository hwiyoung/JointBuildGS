# Codex-to-Work Return - Gate S0 UAS Reference Coverage R1 Recovery/Promote v1

## Return metadata

- handoff_id: `P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1`
- task_id: `P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1`
- offered commit: `b0e13d35d1db6fe514b3830372b62f7a749e79ab`
- accepted/source commit: `5eb8028930b49ae311406620b7f5150f92fc33fc`
- output commit: `SELF`
- proposed technical status: `TECHNICALLY_COMPLETE_PROMOTED_BLOCKER_EVIDENCE`
- Gate S0 decision: `null`
- P2 performance: `PROHIBITED`
- scientific_verdict: `null`

## Answer first

The bounded recovery completed without reopening or hashing any scientific source and without recalculating segmentation, eligibility, grouping, splitting, power, or performance. The historical R1 evidence is now promoted and reproducibly bound.

The result is unchanged: 72 of 199 buildings are evaluation candidates, but they form only nine independent shared-reference/spatial groups. Held-out has ten buildings in two groups. The valid scope is `PILOT_ONLY_REFERENCE_SCOPE`, the recommended Gate action remains `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`, and no P2 performance run is authorized.

## Exact frozen result

- `U_target`: 199
- `E_paired` technical candidate: 72
- development / validation / held-out buildings: 51 / 11 / 10
- independent groups: 9
- development / validation / held-out groups: 5 / 2 / 2
- claim scope: `PILOT_ONLY_REFERENCE_SCOPE`
- Gate recommendation: `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`
- Gate decision: `null`
- scientific_verdict: `null`

This is not a 72-independent-building experiment. Shared UAS patches and spatial lineage collapse the information to nine independent groups. A confirmatory main P2 claim would overstate the evidence.

## Reproducibility recovery

The historical defect was repaired by one canonical checkpoint write/reload serializer preserving `digest_method: same_stream_as_add_once_serialization`. Six checkpoints and 16 derived output records validated against recorded bytes and SHA-256 values.

- historical `reference_grid` attempts: 1
- historical `eligibility_metadata` attempts: 1
- `capture_exact` calls: 0
- `SourceAttempts.start` calls: 0
- scientific-source reads or hashes: 0
- scientific recalculations: 0

The first invocation wrote a clean-state 100 validation attestation, verified existing derived outputs, and promoted byte-identical copies. A separate second process returned `COMPLETED_FAST_PATH` with zero source reads and recalculations. Crash/pending recovery and partial retry are fail-closed.

## Exact evidence

- recovery ledger URI: `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1/control/recovery_ledger_v1.json`
- recovery ledger: 4,395 bytes; SHA-256 `5fa7a1d2c80633bae957b5b1e88f0165da9d7285a26676901d4bc113075c5be0`
- promoted manifest: 24,728 bytes; SHA-256 `312ac10ea3ee730d1677265645de4f762d6d9104fa4d42be93986ce0d416e321`
- promoted report: 1,115 bytes; SHA-256 `5babf16dbcf60c1ac141df9f9fd9b35223dd86c67cbaa50143a024646db497b5`

The ten promoted tables are byte-identical to historical derived records and digest-bound by the manifest and recovery ledger.

## Scope and leakage review

No raw UAS, compact UAS grid, predecessor input checkpoint/eligibility input, images/poses, SfM/MVS/depth/normal/confidence, ALS, LoD1/LoD2 geometry, `scene.mvs`, R1 inputs, `Images.zip`, `OPF.zip`, held-out outcomes, C1-C5 performance, Fusion W1, or `R_ext` was opened or hashed by recovery.

The LoD2-derived LoD1 remains diagnostic/self-conditioned and cannot make primary C5 or paired evaluation READY. Recovery did not alter that isolation contract.

## Gate consequence

The promotion blocker is resolved. The scientific Gate blocker is not: only nine independent groups overall and two held-out groups remain. No additional technical execution is automatically required. The next action is a Gate decision between obtaining materially more independent evaluation reference (or expanding the defensible universe) and explicitly approving a separately labelled feasibility pilot with no confirmatory or population/generalization claim.

Until that decision, no P2 performance run, including a pilot, is authorized. `scientific_verdict` remains `null`.
