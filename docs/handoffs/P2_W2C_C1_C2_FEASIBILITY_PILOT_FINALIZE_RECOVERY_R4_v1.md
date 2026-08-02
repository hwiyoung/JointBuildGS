# Work-to-Codex Task Packet — P2 C1/C2 finalize-only recovery R4 v1

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1`
- phase: `P2 / development baseline finalize-only recovery before C3 strategy freeze`
- direction: `Work→Codex`
- status: `APPROVED_FOR_EXECUTION`
- user_approval: `APPROVED_FOR_EXECUTION`
- packet_version: `v1`
- source_commit: `9a03711b3c4d4a61717ce7745741152dbc2152d4`
- project_image_id: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- run_id: `P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-RUN-v1`
- execution_mode: `FINALIZE_ONLY_REUSE`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-013`
- created_at: `2026-08-02`
- activated_at: `2026-08-02T13:08:58+09:00`
- scientific_verdict: `null`

This packet is activated only for the exact reviewed source and invocation bound
below. Experiment Host execution still requires the offered/accepted receipt chain.

## Answer first

R3 completed the zero-scientific smoke and all seven unique scientific Roofer
operations once, with no retry. It then failed before serializing any of the 102
building-method rows because the committed finalizer treated a valid CityJSONSeq
header as feature geometry: the header carries the inherited transform and an empty
`vertices: []`, while the next `CityJSONFeature` record carries the actual vertices.

R4 is a **finalize-only reuse recovery**. It may read the sealed R3 derived namespace
as a read-only source and write only a new R4 namespace. It must not run Roofer,
reconstruct condition geometry, reopen the five original scientific sources, repeat
the R3 smoke, or write into R3. Its sole scientific output is the previously frozen
102-row C1/C2 development surface and the compact report derived by the already
committed metrics/promotion contract after the header reader is corrected.

## Exact sealed source binding

- R3 reviewed source: `8346a1f40763a17b02f40e47dbe74c8102f0a76e`
- R3 activation: `59c6b7f42b9444bf1bf92fe5e8c88d60c56d7513`
- R3 000-offered: `f787a4220c9c77529eca519784e585f1e51b8b6f`
- R3 accepted commit: `7b96d0211777da26d2ff4bc79d1a1be407958433`
- R3 Return commit: `c0fdea30d5509ce1b36b7567cc37f8c2d315049d`
- R3 200-blocked: `bcbc51a6d6f9652b145fcf597326de43b34f1c4d`
- R3 300-closed: `551e633fb9b3f29418a5ba1620c10451b55ddcd6`
- R3 Return Git blob: `38d01b017c220f9ef5e23fd580f12ec06b2d1009`
- R3 300 Git blob: `b9f30ce49c452298193e34f7f89aa4fe290788ed`
- R3 300 SHA-256:
  `3ee8a87f0f3de322d5607121dfc39968f2a4c6496c73551e1c2b4ae720f5c9d0`
- R3 operation_id:
  `5c34f533655997f54e0321c7d3e72aa42054cbf6bf0a02abce1e7ef5669feea3`
- R3 external source namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/`

The closed source contains 521 regular files, 55,170,598 content bytes and zero
symlinks by the R3 metadata-only inventory. That whole namespace is not an R4 input
surface. R4 must resolve and bind only the exact required records from the existing
R3 add-once control/freeze/operation ledgers.

The R3 `300-closed` receipt proves lifecycle closure and the original five scientific
input attestations; it does **not** attest the 521-file R3 execution namespace as an
R4 reuse surface. R4 therefore must not claim `closed_attestation_reuse` for those
derived files. The R4 offer/acceptance must instead carry an exact allowlist of the
required R3 derived files, and Experiment Host must independently verify each listed
file with `sha256_rehash` before and after the R4 event push. Files outside that
allowlist remain unopened and unhashed.

The reviewed exact derived-file manifest contains 22 files and 12,920,322 bytes,
with full manifest-record identity
`a5193175b466585417d49fb20e2ab8e3880feb19f6689c31ea9195c2fd0dcf34`.
The corresponding canonical accepted artifact identity over only sorted
`{uri,bytes,sha256}` fields is
`46e2da58e177d0aaaba453e316cc8a5d64a24d67b2edc1504299fe22d9ea261f`.
It contains the four compact control/checkpoint records, four freeze ledgers, seven
terminal operation ledgers and seven native CityJSONSeq outputs. It contains no LAS
and no original scientific source.

## Frozen scientific contract

- Common current source remains exact `962 / 937 / 25`.
- `U_target=199`; independent-reference candidate remains 72 in nine groups.
- Only the exact development 51 buildings in five groups may appear.
- Conditions remain exactly `C1_L_upper` and `C2_MVS`; expected output is 102 unique
  `(building_id, method_id)` rows.
- C1 remains `SELF_REFERENCE_UPPER_BASELINE` and cannot be pooled or ranked as an
  independent-reference condition.
- Independent UAS remains score-only after frozen condition geometry and
  `R_derived`; it cannot enter reconstruction, registration or cropping.
- Validation 11, held-out 10, C3–C5, LoD1/LoD2 scientific inputs, Fusion W1 and
  `R_ext` remain inaccessible.
- Canonical G2, G3, G4 and `PASS_usable` remain `null`/unavailable.
- No C3 execution is authorized. A C3 strategy DRAFT may be prepared only after a
  complete and independently reviewed 102-row R4 Return.
- `scientific_verdict` remains `null`.

## Sole implementation remediation

1. Preserve R3 packet, Return, 000/100/200/300 receipts and all 521 external files
   byte-for-byte. Never reopen, rename, hard-link as writable, or add a finalized
   ledger to the R3 namespace.
2. Correct the reusable CityJSONSeq reader so a `CityJSON` header with a valid
   three-element `scale`/`translate` and empty `vertices` is an inheritance record,
   not feature geometry. A feature record with malformed transform/vertices must
   still fail closed.
3. Add an exact native-Roofer multi-record regression: transform-bearing empty header
   followed by a `CityJSONFeature` with LoD2.2 Solid and Roof/Wall/Ground semantics.
   Also retain negative tests for malformed header transform, empty feature vertices,
   invalid indices and missing/malformed LoD2.2 semantics.
4. Separate source and destination stores in the finalization API. Read only from a
   read-only R3 mount; write metrics/finalized ledgers only to a new R4 output mount.
   Unit and integration tests must prove zero writes under the source root.
5. Resolve the exact 102 associations, seven execution units, seven terminal operation
   ledgers, seven native CityJSONSeq outputs and only the required frozen
   score/component/control ledgers from R3. Process and digest each of the exact 22
   derived records in one stream; do not comprehensively hash the 521-file namespace.
   Derive each Roofer input point count from its already-bound LAS 1.2 point-format-3
   byte record `(bytes - 227) / 34`; do not reopen or hash an operation LAS.
6. Do not mount or open the five original R3 scientific sources or any operation LAS.
   Do not mount or hash R1, `Images.zip`, `OPF.zip`, raw UAS LAZ or raw `dim_dense`.
7. Do not invoke Roofer, condition-source preparation, synthetic preparation/smoke,
   scientific preparation, `next-attempt`, `record-attempt`, or the R3 wrapper. R4
   Roofer attempts and source-reconstruction operations must both be exactly zero.
8. Preserve the R3 row mapping exactly: 101 associations reuse seven operation units;
   `DEBY_LOD2_4907183 / C2_MVS` remains the one frozen unassociated row and must
   receive only the precommitted no-operation failure state, never fabricated
   geometry or metrics.
9. Run the corrected finalization exactly once into the new namespace, require the
   exact 102-row uniqueness contract, then run the existing compact promotion logic
   once. Any partial destination state is terminal and must not be retried.

## New add-once owners

```text
artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1
artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1
docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1
docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_FINALIZE_RECOVERY_R4_RETURN_v1.md
```

New external output namespace:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1/`

All source and predecessor namespaces, packet/Return/receipt chains, configs,
implementations, tests and promoted evidence become protected after offer.

## Required review before activation

- scientific scope/leakage: exact development-only row mapping, C1 self-reference,
  score-only UAS role and zero prohibited-workstream access;
- ownership/receipt chain: R3 is closed, R3 mount is read-only, R4 owners are unique,
  and no source/destination overlap exists;
- reproducibility/no-repeat: exact native CityJSONSeq regression, required-record
  resolver, single-stream derived reads, zero Roofer/reconstruction work and terminal
  add-once destination behavior;
- Docker tests: source-root write denial, R3-like fixture → exact 102 rows, promotion
  fast path, authority parser, two-host validator, shell syntax and instruction sync.

Activation must bind the exact reviewed source, project image, source namespace,
fresh R4 run/result identity and a bounded path/size/SHA-256 allowlist of required R3
derived records. R4 result envelopes must also preserve the immutable R3 run,
operation, accepted-commit and source-commit lineage. Acceptance must independently
rehash only that allowlist and must not mount or rehash the five original R3
scientific sources.

## Eventual lifecycle

Exact activated invocation binding:

```bash
bash scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_finalize_recovery_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  9a03711b3c4d4a61717ce7745741152dbc2152d4 \
  P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-RUN-v1
```

1. Work Host commits this DRAFT only, then implements and tests the bounded recovery.
2. Three independent exact-source reviews must pass before a separate activation
   commit and 000-offered event.
3. Experiment Host inspects remote source/packet/000 and local sealed R3 namespace
   before a fast-forward-only pull and a `sha256_rehash`-bound exact-manifest
   100-accepted. The exact 22 records are checked once before and once after the
   acceptance push; the execution wrapper does not repeat that acceptance hash.
4. The finalize-only wrapper runs exactly once with R3 mounted read-only and R4 mounted
   read-write. No Roofer image or original scientific source is mounted.
5. On complete 102-row finalization, independently review and promote compact R4
   results, write Return, then close through 200-verified and direct-child 300.
6. On any source drift, source write, parser failure, incomplete row surface or
   destination collision, preserve evidence without retry and close blocked.

## Stop conditions

- any write or metadata mutation under the sealed R3 namespace;
- any Roofer, source preparation, smoke, original-source stream or prohibited-input
  access;
- any R3 required-record identity drift, malformed CityJSONSeq record, repeated
  derived-record stream or duplicate finalization;
- any roster/split/reference/condition/metric/parameter change;
- any result other than exact 102 unique rows, or any non-null scientific verdict.

`scientific_verdict` remains `null`.
