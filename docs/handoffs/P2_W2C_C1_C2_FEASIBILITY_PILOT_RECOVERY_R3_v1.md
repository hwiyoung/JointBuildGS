# Work-to-Codex Task Packet — P2 C1/C2 feasibility pilot recovery R3 v1

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1`
- phase: `P2 / development baseline feasibility before C3 strategy freeze`
- direction: `Work→Codex`
- status: `APPROVED_FOR_EXECUTION`
- user_approval: `APPROVED_FOR_EXECUTION`
- packet_version: `v1`
- source_commit: `8346a1f40763a17b02f40e47dbe74c8102f0a76e`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-013`
- created_at: `2026-08-02`
- activated_at: `2026-08-02T12:02:05+09:00`
- scientific_verdict: `null`

This packet is activated only for the exact reviewed source and invocation bound
below. Experiment Host execution still requires the offered/accepted receipt chain.

## Answer first

R2 closed at `a7828af5380c5070de92526b5c82249cb7be8e25` before any
scientific input was opened. The pinned Roofer process exited `0`, but the zero-payload
fixture supplied only four class-6 points at each roofprint's vertices and four
surrounding class-2 points. Roofer classified all five fixtures as insufficient
coverage and emitted only LoD `0` placeholders. The downstream semantic-shape failure
was a consequence of absent LoD2.2 surfaces, not a C1/C2 result.

R3 changes only this synthetic fixture/tool contract and the new add-once identities
needed for an honest retry. It does not change the scientific population, inputs,
conditions, split, metrics, references, Stage-3 settings or retry policy.

## Frozen scientific contract

- Common current source remains exact `962 / 937 / 25`.
- `U_target=199`; technical independent-reference candidate remains 72 buildings in
  nine groups. Only the exact 51-building, five-group development split may open.
- Conditions remain only `C1_L_upper` and `C2_MVS`; the complete surface is 102 rows.
- C1 remains `SELF_REFERENCE_UPPER_BASELINE` and is not pooled as an independent-
  reference accuracy condition.
- C2 uses the common-base MVS derivative for reconstruction. Independent UAS may be
  used only for scoring after geometry and `R_derived` are frozen.
- Validation 11, held-out 10, C3–C5, LoD1/LoD2 scientific inputs, Fusion W1 and
  `R_ext` remain inaccessible.
- G2 remains canonically null; G3, G4 and `PASS_usable` remain unavailable.
- `scientific_verdict` remains `null`.

## Sole implementation remediation

1. Preserve the complete R2 packet, Return, 000/100/200/300 receipts and eight-file
   failed external namespace byte-for-byte. Never rerun or promote R2.
2. In a new R3 namespace, replace the vertex-only synthetic point fixture with a
   deterministic bounded fixture containing dense class-6 roof-interior support and
   class-2 ground context outside each roof polygon. No scientific file may be used to
   choose its spacing, density, height or extent.
3. Keep the five synthetic condition labels only as a zero-payload interface check;
   they are not C3–C5 scientific runs.
4. Add Work-Host tests that decode the generated LAS and prove exact point counts,
   classifications, finite coordinates, roof-interior placement, ground-context
   placement, repeatable bytes and unchanged zero-scientific access.
5. Keep the pinned Roofer image, command, LoD2.2/G0/G1 requirements and fail-closed
   no-rerun behavior unchanged. Correct only the internal CityJSON boundary exposed
   by the native Roofer output: a non-LoD2.2 parent footprint may omit the optional
   `semantics` member, while LoD2.2 must still provide valid semantics; malformed
   present semantics still fail, and only LoD2.2 surfaces may satisfy G0.
6. Update only R3 task/handoff/run/result/Return/namespace identities required to
   prevent collision with every closed predecessor.

The exact deterministic layout and counts become execution authority only after they
are committed, tested and independently reviewed in the later activation source.

## New add-once owners

```text
artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1
artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_recovery_r3_v1
docs/experiments/p2/c1_c2_feasibility_pilot_recovery_r3_v1
docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_RECOVERY_R3_RETURN_v1.md
```

External namespace:
`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/`.

All prior C1/C2 task packets, Returns, receipts, promoted reports and external
namespaces are protected. The eventual R3 offer must also protect the reviewed R3
packet/config/implementation/tests after offer.

## Required review before activation

- scientific scope/leakage: fixture is synthetic, bounded and cannot encode outcome,
  UAS, LoD2, stable ID, target bbox or condition-performance information;
- ownership/receipt chain: R2 is closed, R3 identities are unique, direct original
  five-record attestation reuse is preserved and writer transfer is serialized;
- reproducibility/no-repeat: deterministic bytes/counts pass, the R2 namespace is
  never reopened, and the R3 wrapper can enter science only after one exact smoke
  PASS ledger.

Activation also requires network-disabled Docker unit/repository tests, shell syntax
and executable-mode checks, the actual packet authority parser, and a zero-scientific
preflight reporting `scientific_payload_bytes_read_or_hashed=0`.

## Pre-activation zero-scientific integration evidence

The exact pinned Roofer image
`3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`
was run in a disposable Work-Host probe with no scientific mount. The first probe
proved all five fixtures were reconstructed as LoD2.2 but exposed the validator's
false rejection of the Roofer-native parent LoD0 footprint without semantics. After
the bounded validator correction, a fresh disposable probe passed exactly once:

- synthetic input: 1,620 points, 55,307 bytes,
  SHA-256 `318feaba986dc21282d7ec9a81b89a39b336364d70a333ef8efcff26100a1a20`;
- unchanged five-footprint GeoJSON: 872 bytes,
  SHA-256 `db7fffae05394cee8d17f022b24b2e4041706ac48f84236f38e3aeb268eda88b`;
- Roofer exit `0`, 10 CityObjects, 5 LoD2.2 geometries, 5 RoofSurface,
  20 WallSurface and 5 GroundSurface uses;
- `G0_generated=true`, `G1_schema_semantic=true`, no G1 failure reason;
- `scientific_payload_bytes_read_or_hashed=0`, `scientific_verdict=null`.

The disposable probe is implementation verification, not an R3 operational attempt;
the add-once R3 external namespace remains unopened until accepted execution.

## Eventual execution lifecycle

Exact activated invocation binding:

```bash
bash scripts/p2_baselines/c1_c2_feasibility_pilot_v1/run_pilot_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  8346a1f40763a17b02f40e47dbe74c8102f0a76e \
  P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-RUN-v1
```

The project-image argument must match the direct original attestation reuse, the
source argument must equal the exact `source_commit` metadata, and the run ID is a
fresh add-once R3 identity.

1. Work Host commits and independently reviews the exact implementation, then makes a
   separate activation commit. A later 000-offered event transfers writer ownership.
2. Experiment Host inspects remote packet/source/000 before a clean fast-forward-only
   pull and accepts using the direct original non-nested closed five-record attestation
   with zero acceptance-time payload rehashes.
3. The exact R3 wrapper runs once. Synthetic Roofer smoke must PASS before any
   scientific mount or stream opens.
4. On smoke PASS, process the exact 51 development buildings for C1 and C2 once and
   produce exactly 102 rows. On smoke failure, stop and close without rerun.
5. Promote only compact R3 evidence after complete independent review, then return
   writer ownership through verified/blocked 200 and direct-child 300.

## Stop conditions

- any authority, source, image, receipt, input, roster, reference or namespace drift;
- any R2 namespace reopen, repeated R3 smoke/scientific stream or duplicate Roofer
  operation;
- any validation/held-out/C3–C5/LoD1/LoD2/Fusion/`R_ext` scientific access;
- weakened G0/G1 screen, incomplete 102-row surface or cost-cap breach.

On a stop condition, preserve evidence, do not rerun or salvage, close the immutable
chain, return writer ownership and keep `scientific_verdict: null`.

## Work Host post-return deliverables

After a successful C1/C2 return, Work Host will independently produce:

1. the frozen-evidence `199→72` UAS-reference explainer with eligibility reasons,
   spatial/group limitations and pass/fail examples;
2. a C3 training-strategy DRAFT grounded in returned C1/C2 failure modes, without
   executing C3.
