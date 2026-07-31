# Work-to-Codex Task Packet — Gate S0 Common-Base Lineage R2B v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- task_id: `P2-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- phase: `P2 / pre-result Gate S0 evidence completion`
- direction: `Work→Codex`
- status: `APPROVED_FOR_EXECUTION`
- packet_version: `v1`
- source_commit: `150796bc7e928fc108082b2048878e86d5820981`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-012`
- follows: `P2-W2C-GATE-S0-EVIDENCE-R2A-v1`
- created_at: `2026-08-01`
- approved_at: `2026-08-01T02:56:50+09:00`
- user_approval: `GRANTED — commit, push and Experiment Host handoff; freeze exact 962/937/25 source set; use LoD2-derived LoD1 with an independent evaluation reference`
- repository_effective_phase: `C1–C5 PROGRAM / GATE S0 FREEZE DRAFT / PERFORMANCE BLOCKED`
- scientific_verdict: null

This packet authorizes only the bounded R2B lineage/no-repeat task after its exact
offered/accepted receipt sequence passes. It is not Gate S0 approval as a whole and
grants no performance authority.

## Goal

Resolve or reject the already-existing exact-937-image P0 common-base derivative
lineage before any new preprocessing is considered, and harden the reusable resolver
so a closed operation cannot be reinitialized or rehashed accidentally.

The task is lineage resolution and no-repeat contract repair, not dense-MVS
generation and not a performance run.

## Why this task is needed

R2A correctly replayed the 962/937/25 source candidate and found an unbound
`scene.mvs`, but its discovery and resume implementation are not sufficient execution
authority for a new shared preprocessing run:

1. Git retention evidence already names a larger retained P0 chain:
   `colmap_dense/images` (937 files), `colmap_dense/sparse`,
   `colmap_dense/stereo`, `openmvs/scene.mvs`, `openmvs/dim_dense.ply` and
   `dim/dim_v1.laz`.
2. `docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md`
   records 937 poses and 4,131,648 sparse points, while
   `phases/p0-audit/scripts/03_mvs.sh` records the OPF/COLMAP/OpenMVS production
   route and exact parameters.
3. R2A matched candidate basenames with incomplete tokens. Its tracked derivative
   matrix says dense MVS is `AMBIGUOUS`, but a clean run of the tracked generator
   would classify `scene.mvs` as `MISSING` and would miss `dim_dense.ply` and the
   retained dense tree.
4. R2A `--initialize-ledger` can overwrite a completed ledger. A subsequent execute
   would reread both LoD2 sources and rehash existing outputs before returning
   `REUSED`, contrary to the closed-task byte budget.
5. R2A operation identities use the accepted commit even though the implementation
   first appears in the later output commit. Future identities must bind the actual
   executable blob/containing commit.
6. The compact scope validator needs an explicit LF/CRLF-portable Git comparison on
   a Windows Work Host.
7. The R2A 200 receipt records the pre-push live-output check, while the claimed
   post-push exact-`origin/main` check is not durably enumerated in a Git receipt.
   Future first-attestation events must record both sides explicitly.

Past R2A files are immutable evidence and must not be edited to repair these issues.

## User-approved decisions carried into this packet

- The exact 962 image members, 937 calibrated image/pose pairs and 25
  `NO_CALIBRATED_CAMERA_POSE_IN_OPF` exclusions are the user-selected common-source
  set. This task verifies lineage against that set; it does not substitute a
  different set.
- Existing OPF sparse members should be consumed directly if an exact consumption
  contract is sufficient; do not generate a duplicate sparse derivative merely to
  obtain a new path.
- Dense MVS is required for the C2 direct-MVS condition, but existing P0 derivatives
  must be resolved before generation is proposed.
- Depth, normal, confidence and segmentation are not to be generated merely because
  their current enablement is unresolved. Their `ON/OFF` state remains a human Gate
  decision. Gravity remains governed by the root requirement to estimate it once
  from terrain MVS normals.
- The R2A LoD2-derived LoD1 is the selected C5 input candidate, conditional on an
  exact independent evaluation reference. Until that reference is bound it remains
  `REFERENCE_DERIVED_DIAGNOSTIC_ONLY` /
  `REFERENCE_DERIVED_SELF_CONDITIONED`, with `primary_c5_eligible=false`, unless an
  independent evaluation reference is recorded. Past R2A labels remain immutable.

## Authoritative documents

1. root `AGENTS.md`
2. `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`
3. `DEC-P1-010` and `DEC-P1-011`
4. R2A task, Return and closed receipt chain as immutable evidence
5. this packet only after a future exact user approval

Legacy `EXPERIMENT_PLAN.md`, `RESEARCH_CONTEXT.md`, Fusion W1 and protected held-out
results are not execution authority.

## Inputs to resolve before artifact reads

- `B_CURRENT_CANDIDATE_c205892c390997b5`
- R1 exact OPF sparse member evidence and inherited attestation
- R2A replay, derivative matrix, reuse ledger, DAG, Return and 300-closed receipt
- `artifacts/manifests/local_artifact_retention_pass2_plan_20260730.json`
- `artifacts/manifests/local_artifact_retention_pass2_receipt_20260730.json`
- `docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md`
- `phases/p0-audit/env/versions.md`
- `phases/p0-audit/scripts/02_opf2colmap.py`
- `phases/p0-audit/scripts/03_mvs.sh`
- compact P0 run configs, logs and receipts named by those records

## In scope

### R2B-1 — manifest-first retained-derivative inventory

- Search Git manifests, run receipts, configs and logs before filesystem discovery.
- Inventory `colmap_dense/images`, `colmap_dense/sparse`, `colmap_dense/stereo`,
  `openmvs/scene.mvs`, `openmvs/dim_dense.ply` and `dim/dim_v1.laz` as one possible
  producer chain.
- Compare the retained 937 image basenames and camera IDs with the exact source
  candidate using directory/member metadata and prior compact hashes first.
- Record producer/version, exact parameters, implementation commit, input member-set
  hash, frame/shift, vertical datum status, output URI/bytes/existing digest and
  downstream scientific role.
- Classify each component as `REUSED_EXACT`, `PARTIAL`, `AMBIGUOUS`, `MISSING` or
  `INELIGIBLE`; a filename is never sufficient evidence.

### R2B-2 — bounded live metadata confirmation

- The Work Host artifact backend is manifest-only for the R2A namespace. Perform live
  checks only on the host that holds the canonical payload.
- Stat and read bounded headers/sidecars/config/logs only after manifest resolution.
- Do not full-hash Images.zip, OPF.zip, the R1 15.7 GB bundle, the retained dense tree
  or R2A diagnostic outputs.
- If no durable digest exists for an otherwise exact candidate, return one proposed
  future single-pass hash requirement with an exact byte ceiling; do not perform that
  pass in this task.

### R2B-3 — no-repeat resolver hardening

- Implement a new R2B namespace; do not modify R2A scripts, configs, manifests,
  reports, Return or receipts.
- Make ledger initialization add-once: an existing completed ledger must cause an
  exact operation-ID lookup and a zero-payload-byte early return, never overwrite.
- Resolve completed operation identities before any source parsing or output hashing.
- Make candidate matching use manifest paths and component-aware rules, not basename
  substring tokens alone.
- Bind operation identity to the actual executable Git blob/containing commit and
  config hash.
- Add LF/CRLF-portable protected-scope validation.
- Test an exact second invocation reads/hashes zero external payload bytes and a
  conflict blocks before payload access.

### R2B-4 — Gate evidence return

- Return one component table covering source membership, SfM sparse, dense MVS,
  depth, normal, confidence, segmentation and gravity.
- Separate existence from Gate readiness and component enablement.
- Propose the minimum remaining human decisions; do not freeze them in this task.
- State explicitly whether a new dense/depth/normal preprocessing run is unnecessary,
  still required or not yet decidable.

## Out of scope

- any C1–C5 performance, GS training, rendering or Roofer quality comparison
- any new dense MVS, depth, normal, confidence, segmentation or gravity generation
- any rerun of R2A LoD2→LoD1 processing
- any full hash of R1, Images.zip, OPF.zip, retained dense payloads or R2A outputs
- primary C5 promotion or use of the LoD2-derived LoD1 in `E_paired`
- AOI, `U_target`, `E_paired`, split, threshold, adapter, loss or cost freeze
- held-out, Fusion W1 or `R_ext` access
- modification of past packets, returns, receipts, R2A outputs or research canon
- scientific or phase approval by an agent

## Proposed Git write scope after future approval

- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- `artifacts/manifests/gate_s0/common_base_r2b`
- `configs/input_and_alignment/gate_s0/common_base_r2b`
- `docs/handoffs/returns/P2_C2W_GATE_S0_COMMON_BASE_LINEAGE_R2B_RETURN_v1.md`
- `docs/research/preregistration/gate_s0/common_base_r2b`
- `scripts/input_and_alignment/gate_s0/common_base_r2b`
- `tests/input_and_alignment/gate_s0/common_base_r2b`

Everything else is protected unless a later approved version explicitly narrows and
adds an exact path. In particular, all R1/R2A packets, returns, receipts, reports,
manifests and scripts are immutable.

## Required outputs after future approval

- `existing_common_base_derivative_lineage_v1.json`
- `exact_937_member_crosswalk_v1.json`
- `component_readiness_v1.csv`
- `no_repeat_operation_ledger_v1.json`
- `reuse_or_generation_decision_v1.md`
- `issue_log_v1.md`
- compact output manifest
- Return Packet with `scientific_verdict: null`

## Verification after future approval

- repository Docker image, GPU not required
- exact second-run zero-payload-byte/no-op test
- completed-ledger overwrite refusal test
- basename-token regression covering `scene.mvs`, `dim_dense.ply`, `dim_v1.laz` and
  directory candidates
- 937 member/camera-ID crosswalk tests
- LF/CRLF scope validation from a Windows-compatible checkout
- protected-path and no-performance/no-held-out/no-Fusion/no-`R_ext` tests
- immutable receipt evidence that distinguishes any required pre-push and post-push
  exact-`origin/main` attestation; never infer the second pass from the first
- two-host receipt validators without `--artifact-root` except for a separately
  approved first attestation that has no prior reusable digest

## Stop conditions

- exact source/member lineage contradicts 962/937/25
- a prior payload must be rehashed to continue
- existing payload would be overwritten, moved or deleted
- a primary C5, reference, component-enablement or other scientific choice is required
- performance or protected-result access would be required
- current writer ownership, remote SHA or scope is ambiguous

## Done when

- all retained P0 common-base candidates are resolved from manifests and bounded
  metadata before any generation proposal;
- the 937 member relation is proven, disproven or left explicitly ambiguous;
- a second invocation cannot reread a completed operation's payload;
- each Stage-1 component has a separate existence/readiness/enablement state;
- the Return identifies the next human Gate decision and does not imply performance
  authority;
- `scientific_verdict` remains null and writer ownership is returned through a future
  verified/closed receipt chain.
