# Work-to-Codex Task Packet — Gate S0 Evidence R2A v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-EVIDENCE-R2A-v1`
- task_id: `P2-GATE-S0-EVIDENCE-R2A-v1`
- phase: `P2 / pre-result Gate S0 evidence completion`
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- master_roadmap_version: `C1C5_CANON_v2`
- result_contract_version: `C1C5_CANON_v2`
- data_scope_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-011`
- supersedes: null
- follows: `P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- created_at: `2026-08-01`
- user_approval: `NOT_GRANTED`
- repository_effective_phase: `C1–C5 PROGRAM / GATE S0 FREEZE DRAFT / PERFORMANCE BLOCKED`
- scientific_verdict: null

This DRAFT is not execution authority. It becomes executable only through the exact
source/approval/offered/accepted sequence in `docs/research/05_HANDOFF_PROTOCOL.md`.
Approval of this bounded evidence task is not a Gate S0 or performance approval.

## Goal

Close the new `C1C5_CANON_v2` common-base evidence gap without repeating closed R1 work:

1. independently replay the compact `B_current` source candidate;
2. bind any already-existing exact-base SfM sparse/dense MVS/depth/normal/confidence
   derivatives, or return explicit missing generation requirements;
3. publish one idempotent shared preprocessing DAG instead of arm-specific work; and
4. materialize the user-authorized LoD2-derived LoD1 **diagnostic** with explicit
   self-conditioning lineage, without promoting it to primary C5.

No C1–C5 performance, GS training, Roofer quality comparison or held-out result is
authorized.

## Scientific context

`C3_GS_image` is no-external-prior GS, not RGB-only or sparse-only. C2–C5 must use one
exact current image/pose base. C2 sends same-base MVS directly to Roofer; C3
reoptimizes image-derived geometry through GS; C4/C5 add one external prior each.

Work Host has consolidated prior verified evidence into
`B_CURRENT_CANDIDATE_c205892c390997b5`. It binds 962 image members, 937 exact
image/pose pairs and 25 outcome-free exclusions without opening the external source
archives again. This is a candidate, not a human Gate freeze.

`DEC-P1-011` permits deterministic LoD2→LoD1 diagnostic preparation. When the same
LoD2 or production lineage is used for scoring, the result is
`REFERENCE_DERIVED_SELF_CONDITIONED`; it is excluded from primary C5,
`E_paired` and `Delta_N_pass(C5)`.

## Authoritative documents

1. root `AGENTS.md`
2. `docs/research/00_RESEARCH_CHARTER.md`
3. `docs/research/01_MASTER_ROADMAP.md`
4. `docs/research/03_DATA_AND_BASELINE_SCOPE.md`
5. `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
6. `docs/research/05_HANDOFF_PROTOCOL.md`
7. `docs/research/06_DECISION_LOG.md` through `DEC-P1-011`
8. this packet after exact approval

`docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v1.md` is read-only Gate
review context with `execution_authority: NONE`; it is not task authority.

Legacy `EXPERIMENT_PLAN.md`, `RESEARCH_CONTEXT.md`, completed R1 packets/returns and
Fusion W1 are read-only history, not execution authority.

## Current frozen decisions

- `B_current` source and image-derived components are shared once across C2–C5.
- Existing ALS, LoD1, UAS LiDAR, evaluation reference, scored LoD2 and external
  roofprints are excluded from `B_current`.
- The 1,104-image vendor MVS is context-only unless exact candidate binding is proven.
- C4 and primary C5 add one external prior each; no joint-prior arm is created.
- LoD2-derived LoD1 remains diagnostic throughout this task. An independent reference
  would only make later primary-candidate review possible; a separate human Gate decision
  is still required for any promotion.
- Human Gate S0 and all performance execution remain blocked.

## Inputs

| Input | Exact binding | Role | Verification/reuse rule |
|---|---|---|---|
| `b_current_source_candidate_v1.json` | `c205892c390997b57b13ee211bbc264c45800770bb84f0b2698c45d3c656fd74` | source candidate | Rebuild from Git compact evidence; no external rehash |
| R1 accepted receipt | `7a16085c221ccf87d16f712332ac3c97eda193b1` | immutable prior artifact attestation | Validate Git chain; do not call predecessor validator with `--artifact-root` |
| Images archive | 5,906,891,973 bytes / `078056d1…34d` | candidate source | Do not full-rehash; prior attestation and member inventory only |
| OPF archive | 1,936,493,976 bytes / `ae83a054…daa` | poses/sparse candidate | Do not full-rehash; prior member evidence and bounded metadata only |
| SfM sparse evidence | `sfm_sparse_initialization_v1.json` | derivative source fact | Reuse exact member hashes; do not repeat R1 member hashing |
| LoD2 tile `690_5334` | 156,656,509 bytes / `61d29e46…314` | diagnostic source and score-reference lineage | While parsing once, compute source digest in the same stream |
| LoD2 tile `690_5336` | 147,865,939 bytes / `494282ee…674` | diagnostic source and score-reference lineage | While parsing once, compute source digest in the same stream |

The technical offered receipt must set `required_for_task: false`. Missing mount access is
an explicit `BLOCKED` finding, not permission to substitute or re-download data. If new
external diagnostic outputs are promoted at `200`, include only those new outputs in the
live records and apply the required pre-push/post-push safety passes.

## In scope

### R2A-1 — duplicate-work preflight

- Build `reuse_ledger_v1.json` before any payload operation.
- Derive an operation identity from source-candidate hash, component, producer/version,
  code commit, config hash, coordinate frame and scientific role.
- Search prior manifests/receipts first. Exact completed identities are `REUSED`; do not
  schedule them again.
- Record planned/read/hashed bytes by operation and enforce the byte budget below.

### R2A-2 — source candidate replay

- Run the Work Host source-candidate generator in `--check` mode.
- Independently verify the 962/937/25 counts, exact basename sets, camera-ID uniqueness,
  pose-member hashes and prior attestation identity from Git compact evidence.
- Archive central-directory or bounded metadata reads are allowed only if a contradiction
  must be resolved; do not decompress/hash all images again.

### R2A-3 — existing derivative binding

- Resolve manifest-named candidates before any bounded filesystem discovery.
- For SfM sparse, dense MVS, depth, normal and image-derived confidence, record exact
  source-member relation, producer/version, code/config, frame, role, URI, bytes/hash
  and status: `REUSED_EXACT`, `MISSING`, `INELIGIBLE` or `AMBIGUOUS`.
- Reuse the R1 sparse member evidence. Do not redo the closed sparse hash pass.
- Keep the 1,104-image vendor MVS context-only unless all exact-base fields are proven.
- Do not generate a missing dense MVS/depth/normal/confidence artifact in this task.

### R2A-4 — one shared preprocessing DAG

- Publish dependency order, exact operation identities, inputs/outputs, producer/version,
  config placeholder requirements, coordinate frame, resume rule and bounded cost fields.
- A component may be scheduled once under a `B_current` namespace and referenced by
  C2–C5. Arm-specific duplicate generation is invalid.
- Missing decisions stay null/`MISSING`; do not choose final component enablement,
  MVS algorithm, GS loss, adapter or threshold.

### R2A-5 — LoD2-derived LoD1 diagnostic

- Implement one deterministic, scripted simplification for the two exact LoD2 source
  tiles. Preserve stable building ID and footprint rings; reduce height to documented
  scalar ground/top envelope; discard roof slope, ridge, face adjacency, roof type and
  semantic evaluation labels from the diagnostic prior.
- Compute each source SHA-256 while the parser reads that source once. A separate pre- or
  post-processing full-file hash pass is prohibited.
- Write a neutral per-building prism record and a standards-oriented CityJSON/CityJSONSeq
  candidate only if the existing pinned library can serialize and parse it reproducibly.
- Store large outputs only below the exact add-once namespace
  `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/common_base_r2a/P2-GATE-S0-EVIDENCE-R2A-v1/`.
  Raw input paths are read-only. Never overwrite or delete an existing path. If the
  namespace already contains byte-identical records, mark them `REUSED`; any conflicting
  record is `BLOCKED_NAMESPACE_CONFLICT`. Git receives compact lineage, hashes, counts,
  coverage and validation summaries only.
- Set `prior_role=REFERENCE_DERIVED_DIAGNOSTIC_ONLY`,
  `evaluation_class=REFERENCE_DERIVED_SELF_CONDITIONED` and
  `primary_c5_eligible=false` for every derived record.
- Do not score the diagnostic, promote it to `E_paired`, or inspect performance.

## Byte and repetition budget

| Operation | Maximum repeated full-byte passes |
|---|---:|
| closed R1 15.7GB source bundle | `0` |
| Images.zip / OPF.zip in this task | `0` full rehash passes |
| each LoD2 diagnostic source | `1` processing stream including digest |
| each new LoD1 output at first artifact receipt | `2`; one pre-push and one post-push safety pass |
| receipts after the first artifact promotion (normally `300`) | `0` |

If a command would exceed this budget, stop that command, record `DUPLICATE_WORK_GUARD`,
and complete the remaining safe evidence outputs.

## Out of scope

- C1–C5 performance, GS training, rendering evaluation, Roofer comparison or PASS verdict
- generation of missing common-base dense MVS/depth/normal/confidence
- primary C5 promotion or claim from LoD2-derived diagnostic
- `U_target`, `E_paired`, AOI/split/cost freeze
- C1/C4 production derivatives, registration or Stage 3 completion
- held-out building/result access, Fusion W1 or `R_ext`
- purchase, download, license acceptance, external message or raw input mutation
- modification of prior task packets, returns, receipts, archived evidence or canon docs
- scientific or phase approval by an agent

## Exact Git write scope

Only these paths may be added or changed after Experiment Host acceptance:

- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-EVIDENCE-R2A-v1`
- `artifacts/manifests/gate_s0/common_base_r2a`
- `configs/input_and_alignment/gate_s0/common_base_r2a`
- `docs/handoffs/returns/P2_C2W_GATE_S0_EVIDENCE_R2A_RETURN_v1.md`
- `docs/research/preregistration/gate_s0/common_base_r2a`
- `scripts/input_and_alignment/gate_s0/common_base_r2a`
- `tests/input_and_alignment/gate_s0/common_base_r2a`

Protected paths include all pre-existing files outside the exact children above,
especially:

- `AGENTS.md`, `CLAUDE.md`
- `artifacts/manifests/handoffs/P1-W2C-REPO-AUDIT-R2`
- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-PREP-v1`
- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- `artifacts/manifests/gate_s0/b_current_source_candidate_v1.json`
- `artifacts/manifests/gate_s0/remediation_r1`
- `docs/evidence`, `docs/experiments/pilots/fusion_w1`
- `docs/handoffs/HANDOFF_INDEX.md`
- `docs/handoffs/P2_W2C_GATE_S0_EVIDENCE_R2A_v1.md`
- all prior Task/Return Packets
- `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`
- `docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v1.md`
- `docs/research/preregistration/gate_s0/B_CURRENT_SOURCE_CANDIDATE_v1.md`
- all pre-existing Gate S0 evidence and `remediation_r1`
- `docs/research/preregistration/fusion_w1`, `quality_axis`, `phases/p2-gsjso`
- `scripts/input_and_alignment/gate_s0/build_b_current_source_candidate.py`
- `scripts/repository`, `tests/repository`

## Required outputs

| Output | Required content |
|---|---|
| `B_CURRENT_EVIDENCE_R2A_REPORT_v1.md` | answer first, resolved/remaining gaps, next safe task |
| `source_candidate_replay_v1.json` | exact replay result and contradictions |
| `derivative_provenance_matrix_v1.json` | five components with status/evidence/next requirement |
| `reuse_ledger_v1.json` | operation identities, reused/skipped/executed state, byte counts |
| `preprocessing_dag_v1.json` | one shared dependency DAG and resume contract |
| `lod2_derived_lod1_diagnostic_manifest_v1.json` | source/output hashes, rule, counts, coverage, diagnostic labels |
| `lod2_derived_lod1_lineage_v1.csv` | per-building source ID/tile/output record and self-conditioning class |
| `issue_log_v1.md` | inherited/new blockers and duplicate-work guard events |
| `output_manifest_v1.json` | LF-canonical Git output hashes; external output records if any |
| Return Packet | `docs/handoffs/returns/P2_C2W_GATE_S0_EVIDENCE_R2A_RETURN_v1.md` |

Large diagnostic payloads remain outside Git. Every required output must preserve
`scientific_verdict: null` and must not claim Gate or performance readiness.

## Verification

- Use the repository Docker image. GPU is not required for this task.
- Run source-candidate `--check`, targeted R2A tests, repository instruction/inventory/
  two-host tests and protected-scope checks.
- Test duplicate identities are no-op/reuse and cannot write a second namespace.
- Test 962/937/25 joins and that no derivative is silently invented.
- Test LoD2 simplification determinism, source-stream digest, building-ID preservation,
  absence of roof topology/type/semantic fields and diagnostic-only labels.
- Test no held-out/performance/Fusion/`R_ext` path was read or written.
- The first `artifact_verified` receipt must pass once pre-push with
  `--origin-ref HEAD --artifact-root` and once post-push against exact `origin/main`
  with `--artifact-root`. This deliberate two-pass safety check applies only to new
  output records in that receipt, never to the inherited 15.7GB R1 input bundle.
- Do not call predecessor receipt validators separately with `--artifact-root`.

## Preflight

- [ ] Complete activation tuple supplied
- [ ] packet status/user approval are `APPROVED_FOR_EXECUTION`
- [ ] source commit is an exact non-placeholder DRAFT snapshot
- [ ] clean Experiment Host checkout; fetched `origin/main` equals offered commit
- [ ] remote packet/receipt read-only precheck passed before ff-only pull
- [ ] offered receipt validated and accepted receipt transferred writer turn
- [ ] previous R1 closed chain and Work source candidate validate without live source rehash
- [ ] protected paths, no-held-out and no-performance guards pass

If activation is missing, return `DRAFT_OR_UNAUTHORIZED_HANDOFF`. If source, packet,
branch, scope or remote SHA drifted, return `STALE_TASK_PACKET` without task action.

## Stop conditions

- authority/source/scope mismatch or dirty serialized-main state
- source digest differs while the one-pass LoD2 parser reads it
- a primary/scientific choice is required
- a new large download, purchase, license acceptance or raw mutation is required
- manual per-building geometry repair or outcome inspection would be required
- diagnostic LoD1 cannot remain explicitly separated from primary C5
- byte/repetition budget would be exceeded

Scientific gaps are findings. Complete safe outputs and close the technical handoff
instead of substituting an asset or leaving writer ownership ambiguous.

## Done when

- source replay and five-component provenance are complete or explicitly missing;
- reuse ledger proves closed R1 work was not rerun;
- one shared preprocessing DAG specifies the next generation task;
- LoD2-derived LoD1 diagnostic is deterministically produced or an exact technical
  blocker is recorded, with no primary promotion;
- all outputs are hash-indexed and tests pass;
- no performance/held-out/Fusion/`R_ext` activity occurred;
- Return proposes only `READY_FOR_GATE_S0_EVIDENCE_REVIEW` or
  `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`;
- `scientific_verdict` remains null; verified/blocked and closed receipts return the
  writer turn to Work Host.

## Launcher prompt

```text
Use only root AGENTS.md, current C1C5_CANON_v2 documents through DEC-P1-011,
the immutable Gate S0/R1 evidence, B_CURRENT_CANDIDATE_c205892c390997b5,
and this exact approved packet. Legacy EXPERIMENT_PLAN/RESEARCH_CONTEXT and Fusion W1
are not execution authority.

Require the complete activation tuple. Confirm clean state, fetch origin/main, inspect
the remote packet and offered receipt before pull, then ff-only pull the exact offered
commit. Validate the offered receipt and create/push accepted ownership before task work.
Return DRAFT_OR_UNAUTHORIZED_HANDOFF or STALE_TASK_PACKET on any mismatch.

Run only bounded common-base/LoD1-diagnostic evidence completion. Build the reuse ledger
first. Do not rehash the closed R1 15.7GB bundle, redo the R1 LoD1 search, or regenerate
missing common derivatives. Bind existing derivatives or report MISSING, and publish one
idempotent shared preprocessing DAG. Produce LoD2-derived LoD1 only as
REFERENCE_DERIVED_DIAGNOSTIC_ONLY / REFERENCE_DERIVED_SELF_CONDITIONED, never as primary C5.

Do not run C1-C5 performance, GS training, Roofer comparison, held-out, Fusion W1 or
R_ext. Produce all required outputs and Return Packet, keep scientific_verdict null,
and close the technical handoff even when scientific blockers remain.
```
