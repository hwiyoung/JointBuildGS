# Work-to-Codex Task Packet — P2 Gate S0 Preparation v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-PREP-v1`
- phase: `P2 / pre-result Gate S0 preparation`
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL`
- audit_commit: `c1c6639611bd26e29699337a03f447972676af75`
- target_branch: `main`
- research_charter_version: `P1_AUDIT_v1`
- master_roadmap_version: `P1_AUDIT_v2`
- result_contract_version: `P1_AUDIT_v1`
- data_scope_version: `P1_AUDIT_v1`
- decision_log_through: `DEC-P1-007`
- supersedes: null
- created_at: `2026-07-31T19:08:41+09:00`
- user_approval: `NOT_GRANTED`
- scientific_verdict: null

This packet is a proposal only. It cannot be executed until the source snapshot,
scientific canon update, explicit user approval, and technical handoff are complete.

In this packet, **write ownership is an operational serialization state**, not a
grant or revocation of either host's filesystem permissions. The Work Host may
author and commit this DRAFT. Only after approval does the immutable technical
handoff designate which host may append the task's execution outputs and receipts.

## Goal

Prepare the evidence needed for the human Gate S0 decision before any new C1–C3
baseline result is produced. The task must identify the exact C1–C5 inputs,
outcome-free candidate population, eligibility funnel, feasible split mode, and
bounded cost. It does not approve Gate S0 or execute a scientific experiment.

## Scientific basis

The execution program is the new five-condition C1–C5 design defined by the
root `docs/research/00_*.md` through `06_*.md` contract set:

| ID | Condition | Role |
|---|---|---|
| `C1_L_upper` | Current UAS/Drone LiDAR → Roofer | current high-quality sensor baseline |
| `C2_MVS` | Current-image MVS → Roofer | photogrammetric baseline |
| `C3_GS_image` | Current images → image-only GS → extraction → Roofer | prior-free GS control |
| `C4_GS_lidar_prior` | Current images + Existing ALS prior → GS → Roofer | existing LiDAR-prior arm |
| `C5_GS_lod1_prior` | Current images + independent LoD1 prior → GS → Roofer | coarse-envelope prior arm |

The historical `docs/research/EXPERIMENT_PLAN.md` is not an execution authority
for this packet. Historical four-condition results may be cited only as background
evidence and must not redefine the C1–C5 conditions, phase order, inputs, split,
or acceptance contract.

## Authoritative documents

1. root `AGENTS.md`
2. `docs/research/00_RESEARCH_CHARTER.md`
3. `docs/research/01_MASTER_ROADMAP.md`
4. `docs/research/02_NOVELTY_MAP.md`
5. `docs/research/03_DATA_AND_BASELINE_SCOPE.md`
6. `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
7. `docs/research/05_HANDOFF_PROTOCOL.md`
8. `docs/research/06_DECISION_LOG.md`
9. P1 audit bundle `docs/audit/*.md` and
   `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md`

Before approval, Work must update the authoritative documents so the C1–C5
program and the historical status of `EXPERIMENT_PLAN.md` are unambiguous.

## Frozen decisions

- C1–C5 are five reconstruction conditions, not five learning runs.
- Current UAS/Drone LiDAR for C1 and Existing ALS for C4 are distinct assets and roles.
- C3–C5 share the same current-image/camera base.
- C5 requires an independent LoD1 prior; scored LoD2 must not be simplified into it.
- `R_derived` is primary; external `R_ext` is out of scope and must not be opened.
- P2 and P3 share one development+validation building pool.
- Held-out buildings are first opened in P4.
- `EXHAUSTIVE_PARTITION` is preferred; `STRATIFIED_SAMPLE` requires evidence and user approval.
- G3/G4 thresholds and the final surface adapter are deferred to P2.
- Prior equations, weights, confidence rules, and schedules are deferred to P3.
- Active P2/Fusion W1 files, locks, and results remain protected capability evidence.

## Inputs

| Input | Version/hash | Resolver/path | Role | Required verification |
|---|---|---|---|---|
| P1 audit | `c1c6639611bd26e29699337a03f447972676af75` | Git | starting evidence | exact commit/tree |
| Current imagery | P1 candidate hash | canonical `JBGS_ARTIFACT_ROOT` | C2–C5 image base | files, names, bytes, SHA-256 |
| Camera/OPF/COLMAP | P1 candidate hash | canonical artifact root | C2–C5 poses | deterministic image–pose join |
| Current UAS LiDAR | P1 manual/nadir candidates | canonical artifact root | C1 | identity, class, CRS/datum, coverage |
| Current MVS | P1 Pix4D candidate | canonical artifact root | C2 | identity, transform, classification |
| Existing ALS | four P1 candidate tiles | canonical artifact root | C4 | identity, independence, registration, coverage |
| Independent LoD1 | unresolved | canonical artifact root and approved provider source | C5 | exact bytes, lineage, leakage guard |
| LoD2 reference | two P1 candidate tiles | canonical artifact root | scoring only | exact bytes, CRS/datum, prohibited-input guard |

## In scope

- Resolve the 962-image versus 937-pose discrepancy with a deterministic ledger.
- Select and freeze the proposed C1 source: manual, nadir, or a documented merge.
- Specify a reproducible C1 class-2/6, ground, vertical-datum, registration, and coverage recipe.
- Specify the C2 source, transform, classification, and coverage recipe.
- Establish Existing ALS identity, C1 independence, temporal gap, registration, coverage,
  and the data interface required for a future C4 prior. Do not design the prior loss.
- Locate and verify an independent LoD1 candidate. If none is found, preserve C5 as
  `MISSING` and Gate S0 as blocked; do not derive LoD1 from LoD2.
- Produce outcome-free AOI candidates using input coverage, stable IDs, continuity,
  area, and cost only.
- Compute candidate `U_target → E_paired` funnels with explicit exclusion reasons.
- Estimate bounded per-condition runtime, memory, output bytes, and retention cost
  without running full baselines or opening held-out outputs.
- Propose `EXHAUSTIVE_PARTITION` and, only if necessary, a justified
  `STRATIFIED_SAMPLE` fallback.
- Record the minimum common `R_derived`, coordinate, datum, gravity, and failure
  contract needed to enter P2. Final adapter selection remains deferred to P2.
- Report CityJSON/CityGML, val3dity/cjval, and G0–G4 writer readiness without
  claiming final acceptance criteria.

## Out of scope

- C1–C5 scientific performance runs or comparison results
- GS training, prior-loss implementation, or hyperparameter tuning
- final extraction-adapter selection
- G3/G4 numerical threshold selection or `PASS_usable` verdicts
- held-out building access or result inspection
- active P2/Fusion W1 execution, modification, or relabeling
- `R_ext` access or execution
- LoD2-derived LoD1, LoD2 roof geometry, roof type, semantic evaluation labels,
  or final roof model as honest-arm input
- mutation of raw inputs or canonical results
- scientific or phase approval by an agent

## Tasks

1. Verify the exact Git, artifact-root, Docker-image, and toolchain identities.
2. Publish the deterministic common image/camera ledger and explain all 25 exclusions.
3. Publish C1, C2, C4, and C5 identity/lineage/coordinate/coverage records.
4. Publish a machine-readable condition-readiness matrix with
   `READY/PARTIAL/MISSING/UNKNOWN` and evidence per field.
5. Produce outcome-free AOI candidates and stable-ID coverage joins.
6. Produce `U_target` and candidate `E_paired` manifests with exclusion reasons.
7. Measure or bound cost on non-held-out calibration units without producing baseline results.
8. Draft the split proposal and immutable-manifest schema.
9. State whether Gate S0 is decision-ready or blocked, without approving it.

## Required outputs

| Output | Proposed path | Required content |
|---|---|---|
| Gate S0 evidence report | `docs/research/preregistration/gate_s0/GATE_S0_EVIDENCE_REPORT_v1.md` | answer-first status, limitations, decision items |
| Exact input manifest | `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json` | URI, bytes, SHA-256, CRS/datum, lineage, role |
| Image/camera ledger | `docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv` | all 962 images, pose status, exclusion reason |
| Condition readiness | `docs/research/preregistration/gate_s0/gate_s0_condition_readiness_v1.csv` | C1–C5 field-level evidence and status |
| Eligibility funnel | `docs/research/preregistration/gate_s0/gate_s0_eligibility_funnel_v1.csv` | `U_target`, C1–C5 eligibility, `E_paired`, reasons |
| Cost evidence | `docs/research/preregistration/gate_s0/gate_s0_cost_bounds_v1.csv` | runtime, memory, bytes, retention assumptions |
| Split proposal | `docs/research/preregistration/gate_s0/gate_s0_split_proposal_v1.json` | mode, IDs/groups, seed/algorithm, rationale; not frozen |
| Issue log | `docs/research/preregistration/gate_s0/issues.md` | failures, unknowns, blockers, no hidden exclusions |
| Return Packet | `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md` | evidence index and proposed status only |

## Verification

- Run project tools and tests in Docker only.
- Bind every `READY` input claim to exact live bytes, not a filename-only match.
- Record Docker image digest, command, exit code, test module, pass/fail count,
  input hashes, and output hashes.
- Use bounded header/sample reads for large point clouds; do not hash the full store.
- Validate CRS, vertical datum, axis/unit, registration residual, class inventory,
  bounds, and coverage definitions.
- Add a cross-host line-ending check for repository instruction validation.
- Do not count known failing imports as passing tests; retain failures in the issue log.
- Required artifact verification level: `artifact_verified` for inputs proposed for
  Gate S0 freeze; otherwise retain `PARTIAL/MISSING/UNKNOWN`.

## Preflight

- [ ] User supplied the complete activation tuple.
- [ ] Packet status and user approval are `APPROVED_FOR_EXECUTION`.
- [ ] `source_commit` is a non-placeholder approved snapshot.
- [ ] The C1–C5 contract is authoritative and `EXPERIMENT_PLAN.md` is historical only.
- [ ] Experiment Host checkout is clean and `origin/main` matches the offered commit.
- [ ] Offered and accepted receipts pass the two-host validator.
- [ ] Active P2/Fusion W1, held-out, and `R_ext` protections are confirmed.
- [ ] Required external roots resolve at the declared verification level.

If any authorization or scope item fails, return `STALE_TASK_PACKET` without
executing. Missing scientific inputs discovered during the authorized audit are
findings, not permission to substitute another asset.

## Stop conditions

- authority, source, branch, or version mismatch
- protected-scope overlap
- held-out or `R_ext` access would be required
- a proposed `READY` input cannot be resolved to exact bytes
- LoD2 or evaluation information would enter an honest arm
- a scientific decision outside packet authority is required

## Done when

- every required output exists and is hash-indexed;
- each C1–C5 prerequisite is `READY/PARTIAL/MISSING/UNKNOWN` with evidence;
- the 962/937 ledger and C1 source decision evidence are complete;
- the LoD1 result is explicit and no leakage substitute is used;
- candidate `U_target`, `E_paired`, costs, AOIs, and split alternatives are auditable;
- the Return Packet proposes only `READY_FOR_GATE_S0_REVIEW` or
  `BLOCKED_FOR_GATE_S0_REVIEW`;
- `scientific_verdict` remains null;
- no scientific run, held-out access, active Fusion W1 mutation, or `R_ext` access occurred.

## Launcher prompt

```text
Use only the approved C1–C5 research contract in docs/research/00_*.md through
06_*.md and this packet. Do not use docs/research/EXPERIMENT_PLAN.md as an
execution authority.

Verify the complete activation tuple, clean checkout, exact origin/main SHA,
approved source snapshot, offered receipt, and accepted operational write ownership before
task action. If any preflight item fails, return STALE_TASK_PACKET.

Prepare Gate S0 evidence only. Do not run C1–C5 scientific baselines, train GS,
open held-out results, modify or run active P2/Fusion W1, access R_ext, design
prior losses, or set final G3/G4 thresholds. Verify proposed READY inputs against
live bytes. Preserve missing LoD1 or other absent inputs as explicit blockers;
never synthesize LoD1 from scored LoD2.

Produce the required evidence files and Return Packet. Propose only
READY_FOR_GATE_S0_REVIEW or BLOCKED_FOR_GATE_S0_REVIEW, keep
scientific_verdict null, and leave the Gate S0 decision to the user.
```
