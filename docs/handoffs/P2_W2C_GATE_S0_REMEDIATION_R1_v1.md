# Work-to-Codex Task Packet — P2 Gate S0 Remediation R1 v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- task_id: `P2-GATE-S0-REMEDIATION-R1-v1`
- phase: `P2 / pre-result Gate S0 remediation`
- direction: `Work→Codex`
- status: `APPROVED_FOR_EXECUTION`
- packet_version: `v1`
- source_commit: `0928201553ba414109ae1f547a8e18a0be38b3d4`
- evidence_output_commit: `380cc8916e739702206a65cdd9318b2014c81030`
- prior_closed_commit: `1cf0db33ecfe4305477735806912992eea3325d8`
- cross_review_commit: `51e3ebfb06f894123ce6fdc77a70d56bdfbfe646`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v1`
- master_roadmap_version: `C1C5_CANON_v1`
- result_contract_version: `C1C5_CANON_v1`
- data_scope_version: `C1C5_CANON_v1`
- decision_log_through: `DEC-P1-009`
- supersedes: null
- follows: `P2-W2C-GATE-S0-PREP-v1`
- created_at: `2026-07-31T21:20:58+09:00`
- approved_at: `2026-07-31T21:27:42+09:00`
- user_approval: `GRANTED — bounded technical remediation with subagent verification`
- approval_basis: `user instruction on 2026-07-31 to proceed without human interruption; scientific verdict remains reserved`
- repository_effective_phase: `C1–C5 PROGRAM / GATE S0 REMEDIATION PREPARATION`
- scientific_verdict: null

This packet is approved for the bounded technical remediation defined below. Execution
remains blocked until an immutable offered receipt and Experiment Host acceptance pass.
Write ownership is only the serialized Git writer turn defined by
`docs/research/05_HANDOFF_PROTOCOL.md`; it does not change either host's filesystem
permissions. This approval is not a Gate S0 or scientific verdict.

## Goal

Resolve or sharply bound the evidence gaps that prevent a human Gate S0 decision for
the five-condition program:

| ID | Condition |
|---|---|
| `C1_L_upper` | current UAS LiDAR → Roofer |
| `C2_MVS` | current-image MVS → Roofer |
| `C3_GS_image` | current images → image-only GS → extraction → Roofer |
| `C4_GS_lidar_prior` | current images + existing ALS/LiDAR prior → GS → extraction → Roofer |
| `C5_GS_lod1_prior` | current images + independent LoD1 prior → GS → extraction → Roofer |

The scientific objective is to expand the set of buildings for which automatic LoD2
generation is feasible by combining the structural stability of reusable existing 3D
assets with the currency and detailed observation of current aerial imagery. C4 and C5
are compared through rescue sets and failure modes; this packet does not create or claim
a joint-prior synergy arm.

The historical `docs/research/EXPERIMENT_PLAN.md` is not execution authority.

## Starting evidence

- Gate S0 preparation Return Packet:
  `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md`
- immutable Gate S0 evidence under `docs/research/preregistration/gate_s0/`
- output manifest at
  `artifacts/manifests/gate_s0/gate_s0_output_manifest_v1.json`
- Work Host review:
  `docs/research/preregistration/gate_s0/WORK_HOST_CROSS_REVIEW_v1.md`
- portability validator commit:
  `4027991abd2a049fea28fcbad1cf3f707dda2cb5`

The previous evidence reports 962 images, 937 calibrated poses, 25 deterministic
exclusions, 11 exact target payload records totaling 15,743,666,051 bytes, and a
proposed state of `BLOCKED_FOR_GATE_S0_REVIEW` with `scientific_verdict: null`.
These facts are inputs, not a human Gate decision.

## Frozen interpretation rules

- The 937 included images and 25 excluded images are the current deterministic
  image/camera ledger; do not reopen the exclusion rule without contradictory evidence.
- Dense MVS is C2 input only and must not initialize or supervise C3–C5.
- C3–C5 may share a sparse SfM/camera initialization only after its exact provenance,
  coordinate frame, producer/version, and initialization-only role are recorded.
- C1 current UAS LiDAR and C4 existing ALS are different assets and roles.
- C5 requires a prior independent of the scored LoD2 reference. Do not simplify scored
  LoD2 Z, `RoofSurface`, roof type, semantics, or final models into an honest-arm prior.
- `R_derived` remains primary. Do not access or run `R_ext`.
- Evaluation reference overlap with a condition input must be classified explicitly.
  If C1 input and its geometry reference share the same source, report a
  self-reference/conditional evaluation class rather than independent accuracy.
- `U_target`, `E_paired`, split IDs, cost ceilings, adapters, and G3/G4 thresholds remain
  unknown or deferred unless this task produces outcome-free evidence that directly
  supports them. An agent does not approve those decisions.
- Legacy Fusion W1, held-out results, and approved quality-axis exception files remain
  protected and are not evidence sources for this task.

## In scope

### R1 — independent LoD1 viability

- Search the canonical artifact root, Git-owned manifests, and official provider or
  cadastral metadata already within the program's geographic/data scope.
- Record exact candidate identity, provider, acquisition/production date, license,
  spatial coverage, CRS/datum, level of detail, independence from scored LoD2, and
  whether bytes already exist in the approved artifact root.
- A cadastral footprint+height construction may be listed only as a candidate requiring
  a later scientific decision; do not create it or treat it as the adopted C5 prior.
- If no admissible candidate is found, preserve `MISSING` and state the exact search
  boundary. Do not claim worldwide or provider-wide absence.

### R2 — C3–C5 sparse SfM initialization provenance

- Inspect the verified OPF/image payloads and their archive metadata read-only.
- Identify the exact archive member or external artifact intended to supply sparse
  points/cameras for C3–C5. Record URI/member, bytes, SHA-256, producer/version,
  coordinate frame, transforms, and role.
- If the verified OPF contains poses but no admissible sparse point artifact, record the
  initialization as `MISSING` or `PARTIAL`; do not substitute dense MVS.

### R3 — coordinate, datum, registration, and evaluation-reference foundation

- Extract source CRS, axis/unit, vertical datum evidence, LAZ/GML metadata, and known
  transformations from verified payload headers and official metadata.
- Write a reproducible transformation/registration plan with required residual checks;
  do not create a transformed canonical payload in this task.
- Record geometry/structure reference ID, version, provider, uncertainty, production
  lineage, and overlap with C1/C2/C4 inputs or shared footprint sources.
- Classify reference use per condition as independent, partially shared, self-reference,
  or unknown. Do not inspect held-out outcomes or move evaluation geometry into inputs.

### R4 — condition input provenance

- C1: bound manual/nadir selection evidence, class inventory, proposed class-2/6
  derivative recipe, datum/registration requirements, and coverage evidence.
- C2: determine whether the Pix4D product is hash-bound to the exact 937-image base.
  If not provable, freeze the honest label `sensor-processing bundle baseline` and list
  the interpretation limit.
- C4: establish ALS identity, temporal independence from C1, overlap, coordinate
  transform requirements, confidence metadata availability, and the future prior
  interface boundary. Do not design a prior loss.
- C3–C5: bind the common image/camera ledger and R2 sparse initialization status.

### R5 — Stage 3 and common-toolchain inventory

- Inventory executable Roofer, CityJSON/CityGML writer, cjval/val3dity validation,
  gravity, non-GT `R_derived`, and G0–G4 reporting paths with version and replay status.
- Distinguish existing production code, partial prototype, test-only code, and missing
  capability. Do not choose the final adapter or numerical acceptance thresholds.

### R6 — outcome-free readiness update

- Update the C1–C5 readiness matrix and blocker order from R1–R5 evidence.
- Rebuild the outcome-free stable-ID eligibility evidence by joining candidate AOI,
  the frozen image/camera inclusion ledger, condition input coverage, and C5 candidate
  availability. Record one row per candidate stable ID with C1–C5 eligibility and an
  explicit exclusion reason. Evaluation-reference IDs/footprint coverage may support
  selection only where the canon permits; no roof geometry, label, or method outcome may
  enter a condition input or selection rule.
- Keep 199 reference intersections as a candidate diagnostic only. Do not promote it to
  `U_target` or `E_paired` without the complete stable-ID eligibility funnel.
- Publish the resulting funnel even if `U_target` and `E_paired` remain `UNKNOWN`; state
  exactly which missing join or eligibility field prevents their definition.
- Do not run cost calibration. State the minimum additional evidence required before a
  separately approved bounded non-held-out calibration task could be safe.

## Allowed external activity

- Read-only access to the canonical `JBGS_ARTIFACT_ROOT`.
- Read-only official provider/cadastral metadata lookup within the fixed program scope.
- Bounded archive member listing, header parsing, and hashing of exact candidate files.
- Temporary extraction inside a disposable container is allowed only for metadata
  inspection and must not be promoted as a canonical derivative.

Do not purchase data, accept new license terms, send messages, upload payloads, or
download a new large raw dataset. Record a candidate URL and acquisition requirement
instead.

## Out of scope

- C1–C5 performance baselines, GS training, rendering evaluation, or comparison results
- prior-loss implementation, confidence schedules, or hyperparameter tuning
- transformed/classified production payload creation
- final adapter selection, G3/G4 thresholds, or `PASS_usable` verdicts
- held-out access, legacy Fusion W1 execution/modification, or `R_ext` access
- LoD2-derived LoD1 or any scored evaluation attribute as honest-arm input
- `U_target`, `E_paired`, split, or cost freeze without complete outcome-free evidence
- mutation/deletion of raw inputs, canonical results, or previous immutable evidence
- scientific or phase approval by any agent

## Exact Git write scope

Only these paths may be added or changed after Experiment Host acceptance:

- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- `artifacts/manifests/gate_s0/remediation_r1`
- `configs/input_and_alignment/gate_s0/remediation_r1`
- `docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md`
- `docs/research/preregistration/gate_s0/remediation_r1`
- `scripts/input_and_alignment/gate_s0/remediation_r1`
- `tests/input_and_alignment/gate_s0/remediation_r1`

The following paths are protected explicitly. Parent `gate_s0` directories are not
listed as protected because they contain the allowed `remediation_r1` child; all
pre-existing files in those parents are enumerated instead.

- `AGENTS.md`
- `CLAUDE.md`
- `artifacts/manifests/handoffs/P1-W2C-REPO-AUDIT-R2`
- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-PREP-v1`
- `artifacts/manifests/local_workspace_20260730.yaml`
- `artifacts/manifests/gate_s0/gate_s0_candidate_aoi_v1.geojson`
- `artifacts/manifests/gate_s0/gate_s0_image_member_inventory_v1.csv`
- `artifacts/manifests/gate_s0/gate_s0_live_artifact_records_v1.json`
- `artifacts/manifests/gate_s0/gate_s0_lod1_search_v1.json`
- `artifacts/manifests/gate_s0/gate_s0_output_manifest_v1.json`
- `configs/input_and_alignment/gate_s0/gate_s0_evidence_v1.json`
- `configs/repository`
- `docs/evidence`
- `docs/experiments/pilots/fusion_w1`
- `docs/handoffs/HANDOFF_INDEX.md`
- `docs/handoffs/P2_W2C_GATE_S0_PREPARATION_v1.md`
- `docs/handoffs/P2_W2C_GATE_S0_REMEDIATION_R1_v1.md`
- `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md`
- `docs/research/00_RESEARCH_CHARTER.md`
- `docs/research/01_MASTER_ROADMAP.md`
- `docs/research/02_NOVELTY_MAP.md`
- `docs/research/03_DATA_AND_BASELINE_SCOPE.md`
- `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- `docs/research/05_HANDOFF_PROTOCOL.md`
- `docs/research/06_DECISION_LOG.md`
- `docs/research/EXPERIMENT_PLAN.md`
- `docs/research/RESEARCH_CONTEXT.md`
- `docs/research/WORK_START_HERE.md`
- `docs/research/preregistration/fusion_w1`
- `docs/research/preregistration/quality_axis`
- `docs/research/preregistration/gate_s0/GATE_S0_EVIDENCE_REPORT_v1.md`
- `docs/research/preregistration/gate_s0/WORK_HOST_CROSS_REVIEW_v1.md`
- `docs/research/preregistration/gate_s0/gate_s0_condition_readiness_v1.csv`
- `docs/research/preregistration/gate_s0/gate_s0_cost_bounds_v1.csv`
- `docs/research/preregistration/gate_s0/gate_s0_eligibility_funnel_v1.csv`
- `docs/research/preregistration/gate_s0/gate_s0_image_camera_ledger_v1.csv`
- `docs/research/preregistration/gate_s0/gate_s0_input_manifest_v1.json`
- `docs/research/preregistration/gate_s0/gate_s0_split_proposal_v1.json`
- `docs/research/preregistration/gate_s0/issues.md`
- `phases/p2-gsjso`
- `scripts/input_and_alignment/gate_s0/prepare_gate_s0_evidence.py`
- `scripts/input_and_alignment/gate_s0/validate_gate_s0_evidence.py`
- `scripts/repository`
- `tests/fusion_w1`
- `tests/input_and_alignment/gate_s0/test_gate_s0_evidence.py`
- `tests/repository`

## Required outputs

All new scientific evidence files live under
`docs/research/preregistration/gate_s0/remediation_r1/`. The output manifest lives at
`artifacts/manifests/gate_s0/remediation_r1/remediation_output_manifest_v1.json`, and
the Return Packet lives under `docs/handoffs/returns/`.

| Output | Required content |
|---|---|
| `REMEDIATION_EVIDENCE_REPORT_v1.md` | answer-first findings, resolved/remaining blockers, next safe step |
| `lod1_discovery_v1.json` | bounded search ledger and candidate/admissibility evidence |
| `sfm_sparse_initialization_v1.json` | exact artifact/member, hash, frame, version, role, or explicit gap |
| `coordinate_reference_matrix_v1.csv` | C1–C5/reference CRS, datum, transform, registration status |
| `evaluation_reference_lineage_v1.json` | identity, provider/version, uncertainty, production lineage, overlap class |
| `condition_provenance_matrix_v1.csv` | field-level C1–C5 `READY/PARTIAL/MISSING/UNKNOWN` evidence |
| `eligibility_funnel_v2.csv` | stable-ID candidate, coverage joins, C1–C5 eligibility, exclusions, `U_target/E_paired` status |
| `stage3_toolchain_inventory_v1.json` | component, version, replay path, readiness, missing dependency |
| `remediation_issue_log_v1.md` | inherited and new issues with resolution evidence and priority |
| `remediation_output_manifest_v1.json` | Git LF bytes/SHA-256 for every other required evidence output and Return Packet; no self-hash |
| Return Packet | `docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md` |

Reusable validators/configs may be added only under the matching `remediation_r1`
allowed paths. Large or derived payloads must not be committed to Git.

## Required verification

- Use Docker for project scripts and tests.
- Revalidate the immutable predecessor output manifest and handoff chain without
  modifying them.
- Bind every new `READY` claim to exact bytes or executable replay evidence. Metadata
  alone supports `PARTIAL`, not `READY`, unless the field itself is metadata-only.
- Hash archive members from their decompressed bytes and record the archive/member
  relationship; do not confuse archive SHA-256 with member SHA-256.
- Validate `scientific_verdict: null`, protected-path non-modification, and no
  performance/held-out outputs.
- Add targeted tests for any new reusable validator and run the applicable repository
  and Gate S0 regression suites.
- Record image digest, commands, exit codes, test counts, inputs, outputs, and limits.

## Preflight

- [ ] Complete activation tuple supplied.
- [ ] Packet status and user approval are `APPROVED_FOR_EXECUTION`.
- [ ] `source_commit` is an exact non-placeholder DRAFT snapshot.
- [ ] Experiment Host checkout is clean and remote `main` equals the offered commit.
- [ ] Offered receipt validates and accepted receipt transfers the writer turn.
- [ ] Prior Gate S0 evidence/receipts and all protected paths are unchanged.
- [ ] Legacy Fusion W1, held-out, `R_ext`, and scored-input leakage guards confirmed.

If the activation tuple is missing or this packet remains DRAFT/unapproved, return
`DRAFT_OR_UNAUTHORIZED_HANDOFF` without task commands. If the tuple, source, packet,
branch, scope, or remote SHA has drifted, return `STALE_TASK_PACKET` without execution.
A missing scientific input found after valid acceptance is an evidence result, not a
reason to substitute another asset or leave the technical handoff unclosed.

## Stop conditions

- authority, source, packet, branch, or scope mismatch
- protected-path overlap or non-clean serialized-main state
- held-out/Fusion W1/`R_ext` access would be required
- scored LoD2 or evaluation attributes would enter an honest input arm
- a new large download, purchase, license acceptance, or external write is required
- a scientific choice rather than evidence classification would be required

When a stop condition is scientific rather than technical, record the blocker and
still complete the authorized evidence outputs and technical receipt chain when safe.

## Done when

- all required outputs exist and are hash-indexed;
- R1–R6 findings are evidence-backed and each gap is resolved or explicitly bounded;
- C1–C5 readiness changes are traceable to new evidence, with no silent substitution;
- the Return Packet proposes only `READY_FOR_GATE_S0_REMEDIATION_REVIEW` or
  `BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`;
- `scientific_verdict` remains null;
- no performance run, training, held-out access, protected mutation, or leakage occurred;
- verified and closed receipts return the serialized writer turn to the Work Host.

## Launcher prompt

```text
Use only the current C1–C5 canon in docs/research/00_*.md through 06_*.md,
the immutable Gate S0 evidence, the Work Host cross-review, and this packet.
docs/research/EXPERIMENT_PLAN.md is historical and is not execution authority.

Before task commands, require the complete activation tuple and verify the approved
packet, exact source snapshot, clean checkout, origin/main == offered commit, offered
receipt, protected scope, and accepted writer turn. Otherwise return
DRAFT_OR_UNAUTHORIZED_HANDOFF or STALE_TASK_PACKET as specified.

Perform bounded Gate S0 remediation evidence work only. Resolve or bound independent
LoD1 viability, C3-C5 sparse SfM initialization provenance, coordinate/datum/
registration and evaluation-reference lineage, C1/C2/C4 condition provenance, and
Stage 3 toolchain readiness. Do not run performance baselines or GS training, create
production derivatives, inspect held-out/Fusion W1/R_ext, derive LoD1 from scored LoD2,
or make a scientific decision.

Produce all required outputs and Return Packet. Propose only
READY_FOR_GATE_S0_REMEDIATION_REVIEW or
BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW, keep scientific_verdict null, verify and close
the technical handoff even when scientific blockers remain, and return the serialized
writer turn to the Work Host.
```
