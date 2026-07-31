# Codex-to-Work Return Packet — P2 Gate S0 Remediation R1 v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- task_id: `P2-GATE-S0-REMEDIATION-R1-v1`
- phase: `P2 / pre-result Gate S0 remediation`
- direction: `Codex→Work`
- status: `BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`
- source_commit: `0928201553ba414109ae1f547a8e18a0be38b3d4`
- approval_commit: `fae43f8875adbadb7c1bbba0a6d8402c06182566`
- offered_commit: `54f9a0f311bcc8c13a01f2b4b4fc3abd0afd19aa`
- accepted_commit: `7a16085c221ccf87d16f712332ac3c97eda193b1`
- input_commit: `7a16085c221ccf87d16f712332ac3c97eda193b1`
- output_commit: `SELF` — resolve to the introducing commit with
  `git log -1 --format=%H -- docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md`
- run_id: `P2-GATE-S0-REMEDIATION-R1-20260731`
- completed_at: `2026-07-31T22:19:00+09:00`
- artifact_verification_level: `artifact_verified`
- repository_effective_phase: `C1–C5 PROGRAM / GATE S0 REMEDIATION REVIEW PENDING`
- scientific_verdict: null

## Executive summary

The bounded R1–R6 remediation evidence task is technically complete and proposes
`BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`. It resolves the sparse-SfM source question:
the exact verified OPF archive contains a 4,131,648-point sparse reconstruction whose
937 camera UIDs exactly equal the 937 calibrated camera IDs. The descriptor and all
12 buffers are bound by decompressed member bytes and SHA-256.

Gate S0 and P2 performance remain blocked. Independent LoD1 is `MISSING`; the official
Bavarian LoD1 candidate derives from updated LoD2 and is inadmissible for honest C5.
Datum/registration/class derivatives/building coverage, `U_target`, `E_paired`, cost,
common `R_derived`, gravity and the complete Stage 3 toolchain are unresolved. This
packet contains no human Gate or scientific decision.

## Completed R1–R6 tasks

1. Reproduced the bounded local/Git/provider LoD1 search and classified provider
   candidates without acquiring data or accepting a license.
2. Rehashed OPF and every exact sparse/calibration/frame member; recorded producer,
   versions, coordinate frame, transforms and initialization-only role.
3. Published the C1–C5/reference coordinate matrix and separate geometry/structure
   reference lineage with C1 `SELF_REFERENCE` classification.
4. Published field-level C1/C2/C4 provenance. C2 is now source-confirmed as not the
   exact 937-image base and is frozen as a `sensor-processing-bundle baseline`.
5. Inventoried Roofer, CityJSON/CityGML, cjio/cjval/val3dity, gravity, non-GT
   `R_derived` and G0–G4 readiness without selecting an adapter or threshold.
6. Stream-parsed only stable IDs, external IDs and GroundSurface XY from score-only
   references and published one outcome-free row for each of 199 candidate IDs.

## Required output index

| Output | Path | Result |
|---|---|---|
| Evidence report | `docs/research/preregistration/gate_s0/remediation_r1/REMEDIATION_EVIDENCE_REPORT_v1.md` | complete |
| LoD1 discovery | `docs/research/preregistration/gate_s0/remediation_r1/lod1_discovery_v1.json` | independent asset `MISSING` |
| Sparse initialization | `docs/research/preregistration/gate_s0/remediation_r1/sfm_sparse_initialization_v1.json` | source `READY`; integration `PARTIAL` |
| Coordinate matrix | `docs/research/preregistration/gate_s0/remediation_r1/coordinate_reference_matrix_v1.csv` | C1–C5/reference evidence |
| Reference lineage | `docs/research/preregistration/gate_s0/remediation_r1/evaluation_reference_lineage_v1.json` | geometry/structure classes |
| Condition provenance | `docs/research/preregistration/gate_s0/remediation_r1/condition_provenance_matrix_v1.csv` | field-level status |
| Eligibility funnel | `docs/research/preregistration/gate_s0/remediation_r1/eligibility_funnel_v2.csv` | 199 candidate diagnostics |
| Stage 3 inventory | `docs/research/preregistration/gate_s0/remediation_r1/stage3_toolchain_inventory_v1.json` | blocked inventory |
| Issue log | `docs/research/preregistration/gate_s0/remediation_r1/remediation_issue_log_v1.md` | inherited/new blockers |
| Return Packet | `docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md` | this file |

The LF-canonical bytes/SHA-256 index for all ten files is
`artifacts/manifests/gate_s0/remediation_r1/remediation_output_manifest_v1.json`.
It intentionally contains no self-hash and uses `output_commit: SELF`.

## Exact technical evidence

- Accepted artifact contract: 11/11 exact records, 15,743,666,051 total bytes,
  `artifact_verified`; records remain unchanged in later receipts.
- OPF archive: 1,936,493,976 bytes,
  SHA-256 `ae83a054cf2f338874ff7bac7b3e17895b8e4405d429674790da3801a0352daa`.
- OPF sparse members: 13 files, 469,147,486 decompressed bytes; 4,131,648 points;
  937/937 exact sparse/calibrated camera-ID set equality.
- LoD1 local scope: 13 files, no filename match; inventory SHA-256
  `fdf6e30400394cbb8b35e78609b407dc8a07ad1f95d71d8cbfc00d617c78d6f5`.
- Reference population: 12,049 unique stable/external IDs; 199 AOI intersections
  (`35 + 164`).
- Candidate stable-ID SHA-256:
  `047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5`.
- Candidate stable/external-ID pair SHA-256:
  `330598a07840972e1371aa77b21ee42f19065c8c401fa8f1b78b3bb82f6f44da`.
- Unregistered numeric full-containment diagnostics: C1 187, C2 197, C4 199;
  none is promoted to eligibility.

## Verification evidence

- Activation tuple, offered receipt and accepted artifact receipt: `PASS`
- Independent accepted-receipt review: `PASS`
- Independent R1–R4 evidence review: `PASS_WITH_BLOCKERS_RETAINED`
- Independent R5–R6/funnel review: `PASS_WITH_BLOCKERS_RETAINED`
- Previous Gate S0 output manifest/validator: `PASS`
- New generator and exact live artifact/member verification: `PASS`
- Targeted remediation unit tests: 11/11 `PASS`
- Prior Gate S0 regression tests: 9/9 `PASS`
- Repository contract tests: 63/63 `PASS`
- Agent instruction contract: `PASS`
- Protected-path/scope and no-held-out/no-performance guards: `PASS`
- Receipt-chain validators are recorded in the immutable 200/300 events after push.

## Resolved or narrowed

- `S0-R13`: sparse source identity and camera binding are `READY`; callable conversion
  and integration remain `PARTIAL`.
- `S0-I04`: exact-937 relation is resolved as a mismatch, not an unknown. C2 remains a
  sensor-processing bundle and cannot support a method-only C2-vs-C3 inference.
- `S0-I06`: C1 current UAS LiDAR and C4 existing ALS are separate assets/sensor roles;
  registration/overlap/interface are still partial.
- Stable-ID candidate evidence is no longer aggregate-only: 199 exact rows exist, but
  building-level current-image coverage is still absent.

## Remaining blockers

1. No admissible independent C5 LoD1 bytes.
2. C1 vertical datum, class-2/6 derivative, registration residual and per-ID coverage.
3. C2 target transform, class derivative, coverage and interpretation guard.
4. C4 exact acquisition/version, registration, overlap, confidence semantics and
   future prior interface.
5. Geometry/structure reference version, uncertainty and per-building production
   overlap; structure overlap remains C2/C3 `UNKNOWN` and C4
   `UNKNOWN_OR_PARTIALLY_SHARED`.
6. Current-image building coverage, hence `U_target`, all-condition eligibility,
   `E_paired` and split.
7. Canonical terrain-MVS gravity, non-GT `R_derived`, Roofer/CityGML/validation and
   G0–G4/PASS_usable writers.
8. Cost ceilings, which require a later separately approved non-held-out calibration.

## Scope and leakage compliance

- Current UAS/Drone LiDAR and existing ALS remain separate assets and roles.
- Dense MVS did not initialize or supervise C3–C5.
- LoD2-derived LoD1 and all scored Z/RoofSurface/roof type/semantics were excluded.
- Only stable ID, provider external ID and GroundSurface XY supported the candidate
  diagnostic; no candidate was promoted to `U_target` or `E_paired`.
- No joint-prior synergy claim was made.
- No performance baseline, GS training, prior loss, production derivative, held-out,
  Fusion W1 or `R_ext` was run, modified or used.
- `scientific_verdict: null` is preserved.

## Proposed status and next action

`BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`

After the immutable 300-closed event returns the serialized writer turn, Work Host
should fast-forward to that exact commit and cross-review this output manifest and
receipt chain. The next authorized packet should bind an independent LoD1 and make
datum/registration/classification/coverage plus the common toolchain executable. P2
performance remains prohibited until a human Gate S0 freeze.
