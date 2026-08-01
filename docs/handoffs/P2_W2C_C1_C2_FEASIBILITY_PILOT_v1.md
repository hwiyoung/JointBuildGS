# Work-to-Codex Task Packet — P2 C1/C2 development feasibility pilot v1

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-v1`
- phase: `P2 / development baseline feasibility before C3 strategy freeze`
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- master_roadmap_version: `C1C5_CANON_v2`
- result_contract_version: `C1C5_CANON_v2 / PROVISIONAL UNTIL P2 CRITERION FREEZE`
- data_scope_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-012`; a separate human pilot approval must be committed before activation
- created_at: `2026-08-02`
- user_approval: `NOT_GRANTED_IN_THIS_DRAFT`
- scientific_verdict: `null`

This DRAFT must be reviewed and committed before a separate activation revision. It
does not itself authorize performance, transfer writer ownership, or permit Experiment
Host execution.

## Answer first

The scientifically ordered next step is a bounded **development-only** C1/C2 run:

1. repair only the sealed Roofer runtime-interface permission defect in a new task
   namespace and pass a synthetic non-performance smoke;
2. run `C1_L_upper` and `C2_MVS` on the 51 preassigned development buildings with one
   fixed common Stage-3 protocol;
3. report continuous metrics, G0--G2 technical outcomes and outcome-free qualitative
   cases without setting G3/G4 or `PASS_usable` thresholds;
4. return evidence for the Work Host to design the first C3 training strategy.

The 11 validation and 10 held-out buildings remain unopened. C3--C5, Fusion W1 and
`R_ext` remain prohibited. The result is feasibility evidence, not a confirmatory or
population/generalization claim.

## Scientific context

The current technical freeze binds the exact common current source at 962 images,
937 image/pose pairs and 25 no-pose exclusions. The promoted outcome-free universe is
`U_target=199`, with 72 evaluation candidates in nine independent groups and an exact
51/11/10 development/validation/held-out building split (5/2/2 groups). This evidence
has claim scope `PILOT_ONLY_REFERENCE_SCOPE`.

The current roadmap already orders P2 as C1--C3 baseline and criterion development
before P3 prior development. C1 and C2 do not train GS. Running them first on the
development split tests the common Stage-3 and evaluation path and exposes the gap
that C3 must address. Validation is intentionally delayed until a C3 strategy and its
selection contract exist, so baseline outcomes cannot be used to redesign the
validation split or held-out protocol.

## Authoritative documents

1. root `AGENTS.md` and its byte-identical `CLAUDE.md` mirror;
2. `docs/research/00_RESEARCH_CHARTER.md` through
   `docs/research/06_DECISION_LOG.md` (`C1C5_CANON_v2`);
3. `docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v2.md` as historical
   technical draft only, superseded where later recovery evidence is exact;
4. `artifacts/manifests/gate_s0/freeze_recovery_v1/technical_freeze_manifest_v1.json`;
5. `docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/` promoted R1
   coverage, eligibility, group and split evidence;
6. the separate human C1/C2 feasibility-pilot approval document required before
   activation;
7. this packet only after it is revised to `APPROVED_FOR_EXECUTION` at an exact
   non-placeholder source commit and offered through a validated two-host receipt.

Legacy `EXPERIMENT_PLAN.md`, `RESEARCH_CONTEXT.md`, protected Fusion W1 outputs and
archived four-condition records are not execution authority.

## Frozen decisions

- Common source: `B_CURRENT_CANDIDATE_c205892c390997b5`, exact 962/937/25.
- `B_current`: camera/pose, sparse, dense MVS and gravity ON; depth, normal-map
  supervision, confidence and segmentation OFF.
- C1: current nadir UAS LiDAR direct Roofer branch; evaluation class
  `SELF_REFERENCE_UPPER_BASELINE`. It is a sensor upper/context baseline, not an
  independently scored accuracy claim.
- C2: exact common-base dense MVS direct Roofer branch; no GS optimization.
- C1 and C2 use the same non-GT `R_derived` derivation, Stage-3 adapter, Roofer image,
  parameters, writer and validators. No external roofprint is permitted.
- C2 uses the independent UAS reference. C1 self-reference metrics are explicitly
  separated and may not be presented as independent G3/G4 evidence.
- Development membership is exactly the 51 rows labeled `development` in
  `split_candidate_v1.csv`; whole groups remain intact.
- Validation 11 and held-out 10 buildings, their condition outputs and all prior
  performance remain inaccessible in this task.
- The LoD2-derived LoD1 stays diagnostic/self-conditioned under `DEC-P1-011`; it is
  not read or used by this C1/C2 task.
- Numerical G3/G4 and `PASS_usable` thresholds remain unset. No threshold is selected
  from this run.
- `scientific_verdict` remains `null`.

## Inputs

| Input | Exact binding | Role | Access rule |
|---|---|---|---|
| technical freeze | `technical_freeze_manifest_v1.json`; common 962/937/25, four consumers 807,030,928 bytes | source/component contract | reuse manifest and existing derivatives; no large-input rehash |
| C1 derivative | freeze-recovery C1 current-nadir UAS class-2/6 derivative and external compact record | direct C1 input | one task read stream; no source LAZ full hash |
| C2 dense MVS | retained exact-937 `dim_dense.ply` bound by freeze manifest | direct C2 input | reuse existing digest/attestation; no regeneration |
| evaluation candidates | promoted `eligibility_candidate_v1.csv` | exact 72 candidate IDs and attemptability | select only exact development rows |
| group/split | promoted `group_graph_v1.csv` and `split_candidate_v1.csv` | exact 51 development buildings in five groups | validation and held-out IDs may be checked as membership metadata only; no outputs/outcomes |
| independent reference | promoted R1 patch/cell evidence, 177 patches and 20,520 score cells | C2 score-only reference | read only cells associated with development IDs; never an input to reconstruction/registration |
| gravity/alignment | frozen gravity and terrain-only alignment receipt | shared Stage-3 frame | no hard-coded gravity; no UAS roof registration for C2 |
| Roofer | `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2` | common Stage 3 | exact digest only; new writable work directory, no algorithm change during pilot |

Before activation, the approval revision must bind the exact Git blob/SHA-256 of all
Git-owned input manifests and the exact external artifact URIs needed by the runner.

## In scope

1. Add a new, task-owned Roofer launcher/wrapper that mounts or selects a writable
   working directory for `roofer.log.json`; do not modify any past orchestrator,
   receipt or evidence file.
2. Run one synthetic five-label interface smoke using zero scientific payload. It
   must pass before any development building is opened.
3. Materialize an add-once 51-building development roster from the promoted split and
   verify that its five group IDs, stable-ID set digest and count match the promoted
   evidence.
4. Run C1 and C2 through one fixed common Stage-3 configuration for all 51 development
   buildings. A method/process failure remains a row-level G0 failure; do not remove
   the building or alter membership.
5. Permit at most one retry per building only for a recorded infrastructure failure
   that occurs before a valid condition output is produced. Parameter changes,
   condition-specific retries and quality-driven reruns are prohibited.
6. Produce complete run, input, output, runtime, resource, failure and digest ledgers.
7. Compute descriptive continuous metrics and G0--G2 technical fields using the
   provisional result schema. Keep G3, G4 and `PASS_usable` nullable with reason
   `THRESHOLD_NOT_FROZEN`.
8. Report C1 self-reference/upper-baseline results separately from C2 independent
   reference metrics. Do not rank C1 and C2 as if both were independently evaluated.
9. Produce outcome-free qualitative case sheets for all 51 lightweight rows plus one
   preselected representative per development group, chosen by the lowest
   `SHA256(task_id|group_id|stable_id)` before condition results are opened.
10. Produce a compact C1/C2 development report answering what failed, where the MVS
    gap appears, whether Stage 3 is stable, and what evidence a C3 strategy must
    address. Do not prescribe or execute the final C3 loss/schedule in this task.

## Out of scope

- validation or held-out building output access, scoring or qualitative inspection;
- C3, C4 or C5 training, inference, loss tuning, ablation or performance;
- final adapter selection, G3/G4 thresholds, `PASS_usable`, multiplicity or a
  confirmatory scientific claim;
- using C1 UAS roof geometry to register, crop or reconstruct C2;
- LoD1/LoD2 geometry input, C4 ALS, external roofprint, `R_ext` or Fusion W1;
- regeneration or full rehash of current imagery, OPF, R1 15.7 GB inputs,
  `Images.zip`, `OPF.zip`, SfM or MVS;
- modifying any past packet, Return, receipt, evidence, promoted R1 table or failed
  task namespace;
- non-null `scientific_verdict`.

## Required implementation and outputs

All paths are new/add-once unless explicitly named as code scope in the activated
packet.

| Output | Proposed path | Required content |
|---|---|---|
| task config | `configs/p2_baselines/c1_c2_feasibility_pilot_v1/` | exact inputs, development IDs/groups, Stage-3 config, caps, seed/rules |
| reusable runner | `scripts/p2_baselines/c1_c2_feasibility_pilot_v1/` | preflight, writable Roofer launcher, C1/C2 orchestration, ledger, resume/fail-closed behavior |
| focused tests | `tests/p2_baselines/c1_c2_feasibility_pilot_v1/` | scope, membership, leakage, permission fix, restart, no-held-out and result-schema tests |
| Git manifest | `artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_v1/` | exact external input/output URIs, bytes/hashes, run IDs, tool/container identities |
| promoted report | `docs/experiments/p2/c1_c2_feasibility_pilot_v1/C1_C2_DEVELOPMENT_REPORT_v1.md` | answer-first quantitative/qualitative findings and limitations |
| metrics | same report directory | 51×2 building-method table, gate table, runtime/failure table, group summaries |
| cases | same report directory | deterministic case index and compact source-linked case summaries |
| Return | `docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_RETURN_v1.md` | exact status/commit, artifacts, verification, blockers, C3-relevant evidence, `scientific_verdict: null` |
| external payload | `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_v1/P2-C1-C2-FEASIBILITY-PILOT-v1/` | immutable full outputs, logs, CityJSON/CityGML, images and compact checkpoints |

The activated packet may narrow these paths after implementation review; it may not
broaden them into C3--C5, validation or held-out scope.

## Quantitative and qualitative report contract

The report must show at minimum:

- attempted/completed/G0/G1/G2 counts and denominators by condition and development
  group;
- failure reason counts without post-hoc exclusions;
- runtime, peak memory, output bytes and retry counts;
- available continuous roof/geometry residuals with units, denominator and null
  reasons; C1 self-reference and C2 independent-reference panels must be separate;
- common Stage-3 input/output point counts and information-loss diagnostics;
- one page/table summarizing the exact 51-building input definition;
- deterministic qualitative cases with top/oblique/section views when renderable;
- explicit limitations: development-only, five groups, no numerical G3/G4 threshold,
  no held-out, no C3--C5 conclusion and no population/generalization claim.

## Reproducibility, cost and no-repeat contract

- Docker-only project execution in the accepted immutable image; Roofer uses the exact
  pinned image digest.
- One RTX-3090-class GPU maximum if any GPU helper is needed, 24 GB VRAM, 12 h total
  wall-clock target, 100 GB new output ceiling and at most one infrastructure retry.
- Every operation identity binds task/handoff, accepted commit, config blob/hash,
  container image, artifact root and exact development roster digest.
- Checkpoint before every scientific open. A completed checkpoint takes a zero-write
  fast path; a partial output without a matching ledger blocks before rereading.
- Reuse prior attestations. Do not repeat large hashes or source preprocessing.
- The first duplicate calculation or repeated hash must stop that operation, record
  cause and add a regression/no-repeat guard before continuing.

## Verification

- root instruction sync and focused repository tests pass in Docker;
- new runner/config/tests pass with network disabled;
- exact synthetic Roofer smoke passes in the task-owned writable namespace;
- roster assertions: 51 unique development IDs, five groups, zero validation or
  held-out result access;
- condition matrix assertions: exactly one final row for every 51×2 combination;
- all output and metric rows trace to exact input/output hashes and run IDs;
- C1 self-reference fields and C2 independent-reference fields cannot be conflated;
- G3/G4/`PASS_usable` are null with `THRESHOLD_NOT_FROZEN`;
- second invocation proves completed fast path with zero scientific reread and zero
  write;
- three independent reviews cover scientific scope/leakage, two-host ownership and
  reproducibility/no-repeat behavior;
- artifact-verified `200-verified` followed by direct-child `300-closed`, with no
  external payload reread at close.

## Proposed Git write scope after activation

- `artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-v1`
- `artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_v1`
- `configs/p2_baselines/c1_c2_feasibility_pilot_v1`
- `docs/experiments/p2/c1_c2_feasibility_pilot_v1`
- `docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_RETURN_v1.md`
- `scripts/p2_baselines/c1_c2_feasibility_pilot_v1`
- `tests/p2_baselines/c1_c2_feasibility_pilot_v1`

The DRAFT/activation packet, separate human approval, decision-log entry and root
instruction/roadmap status update are Work Host-owned pre-offer changes and are not
Experiment Host write scope.

## Stop conditions

- activation tuple, writer ownership, source commit, input manifest or development
  roster mismatch;
- any validation or held-out performance/output access;
- Roofer synthetic smoke still fails after the single code-level writable-workdir
  fix; do not open development scientific payload;
- condition-specific parameter divergence or need to tune from quality outcomes;
- C1/C2 reconstruction/reference leakage or external roofprint use;
- missing exact input/output identity that prevents per-row traceability;
- need to rehash/regenerate protected large inputs;
- overwrite, deletion or mutation of historical evidence/payload;
- output ceiling or unrecoverable infrastructure failure.

Independent buildings may continue after an isolated recorded row failure; the task
must not hide failures or shrink the denominator.

## Done when

- the synthetic Stage-3 permission blocker is resolved or honestly returned as the
  sole pre-scientific blocker;
- if smoke passes, all 51×2 development attempts have one final traceable row and all
  required quantitative/qualitative outputs are promoted;
- validation and held-out access counters remain zero;
- Return states exactly what C3 must improve but does not execute or finalize C3;
- `scientific_verdict` remains null and writer ownership returns to Work Host.

## Return packet path

`docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_RETURN_v1.md`

## Launcher prompt

```text
먼저 사용자가 handoff_id, exact offered-receipt SHA, packet path,
non-placeholder source_commit,
explicit_user_authorization: APPROVED_FOR_EXECUTION을 모두 제공했는지 확인하라.
하나라도 없으면 어떤 command도 실행하지 말고
DRAFT_OR_UNAUTHORIZED_HANDOFF를 반환하라.

승인 tuple이 완전할 때만 Experiment Host clean state와 writer ownership을 확인하고
origin/main을 fetch하라. pull 전에 exact remote packet, human pilot approval,
decision-log entry와 000-offered receipt를 read-only로 검사하라. packet/approval/root
status가 C1/C2 development-only pilot을 허용하고, source_commit과 receipt base_main이
activation tuple에 결속되며, validation/held-out/C3--C5가 금지된 경우에만
fast-forward-only pull하라. offered receipt 검증과 immutable 100-accepted push 전에는
scientific payload를 열지 마라.

root AGENTS.md와 승인된 packet을 전부 읽고 preflight를 적용하라. 먼저 새 writable
Roofer namespace에서 synthetic smoke를 통과시켜라. 실패하면 development input을
열지 말고 blocked Return/receipt로 writer를 반환하라. 통과하면 정확한 development
51동에서 C1/C2만 실행하고, validation 11동과 held-out 10동의 결과는 열지 마라.
G3/G4/PASS threshold를 정하거나 C3--C5를 실행하지 마라. required evidence와
Return을 작성하고 독립 검토 뒤 200/300으로 writer를 Work Host에 반환하라.
scientific_verdict는 null로 유지하라.
```
