# Codex-to-Work Return Packet — P1 Repository/Data Readiness Audit v2

## Handoff metadata

- handoff_id: `P1-W2C-REPO-AUDIT-R2`
- phase: `P1`
- direction: `Codex→Work`
- status: `READY_FOR_REVIEW`
- input_commit: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- source_commit: `939f0b97825eafb7e508239b9c5510938e30fa9f`
- approval_commit: `ac299052a1a6c8c9ebb10bdf328c5d773f28b5e3`
- offered_commit: `9e724b8740756cf128252d8c081d4882b43e5d67`
- accepted_commit: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- output_commit: `SELF` — resolve to the introducing commit with
  `git log -1 --format=%H -- docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md`
- output_commit_resolution_invariant: the command above must equal local
  `HEAD`, `origin/main`, and remote `main` after the audit commit is pushed
- run_ids: `P1-R2-READ-ONLY-AUDIT-20260731`
- completed_at: `2026-07-31T17:08:03+09:00`
- repository_effective_phase: `P2 / Fusion W1 ACTIVE`
- scientific_verdict: null

## Executive summary

R2 activation, accepted ownership, and P1 documentation are technically
complete. The repository contains a reusable gsplat core, renderer,
checkpoint, extraction, an exception-bound E5/C001 occupied-cell `R_derived`
candidate,
Roofer class-2/6,
CityJSON, val3dity wrappers, and continuous metric components. Twelve payload
candidates plus one pilot manifest were live-read and rehashed, 13 files total.

The new five-condition program is not data/P2-ready. Current UAS LiDAR needs a
class-2/6 and datum/registration contract; the 962-image archive and 937 poses
need reconciliation; the C4 ALS-prior interface and independence receipt are
not frozen; independent LoD1 was not found; `U_target`, `E_paired`, split and
cost are unknown; and the common C1–C5 `R_derived`, CityGML/cjval, Sheet A–D,
and G0–G4 aggregation paths are incomplete. These are valid P1 findings, not
handoff blockers. They block related READY claims, C1/C4 comparison, Gate S0
completion, and P2 entry.

P1 proposes only `READY_FOR_REVIEW`. Scientific and phase decisions remain
with the human reviewer.

## Completed tasks

- Verified the exact R2 activation tuple, ancestry, packet, roles, scope,
  protected paths, artifact semantics, and v1 supersession with two
  independent reviewers.
- Fast-forwarded only after remote validation; validated the offered event in
  Docker.
- Created, committed, pushed, and pre-/post-push validated immutable
  `100-accepted.json`.
- Audited repository ownership, Docker/tool paths, GS native artifacts,
  extraction, `R_derived`, Roofer, serialization, validation, result schema,
  and reproduction capability.
- Rehashed twelve exact live payload candidates plus one pilot manifest and
  inspected bounded metadata without computing a store-wide hash.
- Kept Current UAS/Drone LiDAR and Existing ALS as separate assets and roles.
- Produced all nine required audit documents.

## Artifacts

| Artifact | Resolver/path | Hash/config | Size/files | Verification level | Preview |
|---|---|---|---|---|---|
| P1 audit bundle | `docs/audit/*.md` | Git blobs in `output_commit` | 9 files | repository + independent cross-review | Nine status/evidence/gate documents |
| R2 accepted receipt | `artifacts/manifests/handoffs/P1-W2C-REPO-AUDIT-R2/100-accepted.json` | commit `130ff958ddaf33b663065dfb2dfa593645776fa2` | 1 file | Docker validator, pre-/post-push | Experiment Host ownership |
| Exact data candidates | canonical `/artifacts/JointBuildGS`; inventory in `docs/audit/DATA_AND_COORDINATE_AUDIT.md` | 12 payload candidates + 1 pilot manifest, 13 per-file SHA-256 records | 13 files | live bytes + bounded metadata | Images, OPF, ULS, MVS, ALS, LoD2, pilot PDF and pilot manifest |
| Qualitative pilot | `phase-payloads/p2-gsjso/runs/fusion_w1/20260728_fusion_w1_dense_baseline_qualitative_v5/` | PDF `2c85bf526d530c55ef227097d0caf5118f250587a618674bc4753043e3657049`; manifest `1bd34ba3f6d9ae5a762746cfe0df678c537d1605dfaa170a05354fcecc3f1d3e` | PDF 10,012,096 B; manifest 246,040 B | live bytes + tracked manifest | Frozen capability evidence only |

## Verification evidence

| Check | Command/method | Result | Evidence path |
|---|---|---|---|
| R2 remote tuple and ancestry | independent Git object/tree review | PASS | R2 packet and `000-offered.json` |
| Offered receipt | Docker handoff validator against exact offered HEAD/origin | PASS | `000-offered.json` |
| Accepted receipt before push | Docker handoff validator with `--origin-ref HEAD` | PASS | `100-accepted.json` |
| Accepted receipt after push | Docker handoff validator with `--origin-ref origin/main` | PASS | `100-accepted.json` |
| Artifact contract | JSON review by two agents | PASS: false / manifest_only / empty / git_only | R2 receipts |
| Exact candidate bytes | targeted `stat` + SHA-256, no directory hash | PASS for 12 payload candidates + 1 manifest, 13 files | `docs/audit/DATA_AND_COORDINATE_AUDIT.md` |
| LAS headers/bounded class samples | `laspy` header reads and bounded sampling | PARTIAL | data audit; datum/class gaps retained |
| Qualitative v5 contract | Docker unit tests | PASS 10/10 | test/config paths in reproduction plan |
| R_v1 metric components | Docker unit tests | PASS 8/8 | test/code paths in reproduction plan |
| Prior/schedule/seed lineage | Docker unit tests | PASS 21/21 | test/code paths in reproduction plan |
| E5 occupied-cell adapter test entry | Docker unit-test import | FAIL before tests: expected sibling implementation missing | `tests/e5_c001/test_e5_c001_s3ap_phase3.py:21-26` |
| Pilot declared outputs | read-only external verifier | PASS: 45 outputs and 11 receipts rehashed | Git pilot manifest |
| CRS parser | main Docker image | FAIL: missing `pyproj` | recorded environment gap; no install attempted |
| Main-image CLI availability | read-only executable search | MISSING: Roofer, val3dity, cjval, ogr2ogr, PDAL | repository map |

## Findings

### Finding 1 — Repository and core GS

- status: `PARTIAL`
- evidence: `src/stage2/model.py:86-200`,
  `src/stage2/renderer.py:23-151`, checkpoint and unit-test paths in the audit;
  model/renderer core components are `READY`
- interpretation limit: prior confidence, view support, conflict fields, CRS,
  datum, gravity, and common campaign bindings are incomplete
- recommended follow-up: freeze the campaign artifact/receipt schema at Gate S0

### Finding 2 — Current UAS/Drone LiDAR and Existing ALS

- status: `PARTIAL`
- evidence: separate 2024 ULS and 2022 ALS files, hashes, headers, platform,
  point density/class observations, and roles in the data audit
- interpretation limit: ULS vertical datum/class adapter and UAS↔ALS
  registration residual are unresolved; ALS is a prior, not truth
- recommended follow-up: publish separate C1 and C4 identity, transform,
  coverage, independence, and derivative receipts

### Finding 3 — MVS and image base

- status: `PARTIAL`
- evidence: live Pix4D point cloud and Images/OPF archives
- interpretation limit: 962 images versus 937 poses; class/transform and
  per-building support are not frozen
- recommended follow-up: issue a deterministic common-image ledger and C2
  adapter

### Finding 4 — LoD1/LoD2 and leakage

- status: `PARTIAL`
- evidence: two live LoD2 tiles and fixed Git/artifact search
- interpretation limit: LoD2 exact reference bytes are `READY`, independent
  LoD1 is `MISSING`, 199 is a candidate reference intersection count rather
  than `U_target`, and LoD2 may not be converted into an honest C5 prior
- recommended follow-up: obtain an independent LoD1 asset or keep C5/Gate S0
  blocked

### Finding 5 — `R_derived` and extraction

- status: `PARTIAL`
- evidence: exception-bound occupied-cell/class-2/6 implementation, lock, and
  static test intent; separate TSDF/mesh capability under protected Fusion W1
- interpretation limit: common C1–C5 association, crop, gravity, method hash,
  and failure policy are not frozen; upstream ground masks use the C001/E5
  GroundSurface-XY exception and the E5 test imports a missing sibling
- recommended follow-up: repair/validate the E5 test in a separately
  authorized source task, then freeze one common non-GT adapter without
  changing active Fusion W1

### Finding 6 — Roofer, CityJSON, CityGML, validators

- status: `PARTIAL`
- evidence: digest-pinned invocation/receipt paths, custom CityJSON writer,
  val3dity wrappers, fixed repository/live-image search; Roofer and CityJSON
  components are `READY`, while CityGML/cjval are `MISSING`
- interpretation limit: do not label CityJSON as CityGML or claim G1 without
  the required validators
- recommended follow-up: pin and test the conversion/validation toolchain

### Finding 7 — Result contract

- status: `PARTIAL`
- evidence: artifact chain, Sheet A–D, building×method, transitions, and G0–G4
  definitions are `READY`; component metrics exist, but executable aggregation
  is `PARTIAL` and unified writers are `MISSING`
- interpretation limit: no unified writer/evaluator and thresholds are
  intentionally deferred
- recommended follow-up: implement CPU-tested schema and gate writers before
  any held-out access

### Finding 8 — AOI, funnel, split, and cost

- status: `UNKNOWN`
- evidence: one 177,753.3 m² candidate AOI and 199 provisional LoD2
  intersections; live input bounds
- interpretation limit: `U_target`, `E_paired`, exact coverage, split mode,
  sample size, and full cost are not frozen
- recommended follow-up: bounded Gate S0 preparation; do not reuse
  outcome-selected historical sets

### Finding 9 — Qualitative pilot

- status: `PARTIAL`
- evidence: PDF/manifest hashes, 45 output rehashes, pinned config/wrapper
- interpretation limit: its frozen lineage is `READY`, but it uses P0 DIM and
  a supplied footprint; `canonical_evidence_claim=false`
- recommended follow-up: retain as capability/visual evidence only

### Finding 10 — Program authority/status

- status: `PARTIAL`
- evidence: root durable definitions, Decision Log pending relationship, stale
  handoff index/roadmap status
- interpretation limit: not an R2 activation mismatch and not editable in P1
  scope
- recommended follow-up: reconcile the long-term four-/five-condition canon
  and live indexes in a later authorized documentation packet

## Changes made

- Added `docs/audit/REPOSITORY_MAP.md`.
- Added `docs/audit/DATA_AND_COORDINATE_AUDIT.md`.
- Added `docs/audit/BASELINE_PIPELINE_STATUS.md`.
- Added `docs/audit/GS_NATIVE_ARTIFACT_AUDIT.md`.
- Added `docs/audit/SURFACE_EXTRACTION_AUDIT.md`.
- Added `docs/audit/ROOFER_AND_EVALUATION_AUDIT.md`.
- Added `docs/audit/RESULT_OUTPUT_FEASIBILITY_MATRIX.md`.
- Added `docs/audit/TEST_AND_REPRODUCTION_PLAN.md`.
- Added `docs/audit/OPEN_QUESTIONS.md`.
- Added this exact v2 Return Packet.
- No source, config, dependency, data, result, active Fusion W1, held-out, or
  `R_ext` mutation was made.

## Deviations

None. The missing `pyproj`/CLI tools and missing/unknown assets were retained
as findings; no download or installation was attempted.

## Frozen-decision compliance

| Decision | Compliant | Evidence |
|---|---:|---|
| Active P2/Fusion W1 protected | yes | Git scope and read-only inspection |
| Docker-based verification | yes | validators/tests/header reads used existing containers |
| No external roofprint | yes | `R_ext` not opened or executed |
| `R_derived` primary | yes | campaign gap and exception-bound E5 occupied-cell candidate recorded |
| Current UAS and Existing ALS separate | yes | separate identity/role table |
| P2/P3 same development+validation pool | yes | reproduction and result plans |
| P4 first opens all held-out buildings | yes | no held-out access in P1 |
| GT separation | yes | GT/LoD2-dependent historical routes marked ineligible |
| CRS/gravity/gsplat/Stage 3 invariants | yes | unresolved bindings block downstream readiness |
| No threshold/split/sample decision | yes | all retained for Gate S0/human freeze |
| Technical scientific verdict null | yes | this packet and all audit documents |

## Unresolved issues

See `docs/audit/OPEN_QUESTIONS.md`. Q01–Q11 block related Gate S0/P2
readiness; Q12–Q15 require Work Host/human governance follow-up but do not
invalidate this P1 audit.

## Proposed phase status

`READY_FOR_REVIEW`

This is an audit-document status only. It is not `APPROVED`, `CLOSED`,
data-ready, P2-ready, or a scientific verdict.

## Recommended next action

Work Host should independently cross-review the nine audit documents, preserve
active Fusion W1, reconcile the durable-canon/status-index findings in a new
authorized documentation packet, and prepare a bounded Gate S0 packet for
Q01–Q11. The human reviewer should freeze AOI/split/mode/criteria only after
that evidence is available.

## Launcher prompt for Work

```text
Read docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md and all nine
docs/audit/*.md files at the output commit. Cross-check each READY/PARTIAL/
MISSING/UNKNOWN claim against the cited repository path and exact artifact
record. Preserve active P2/Fusion W1 and do not open held-out results.
Treat READY_FOR_REVIEW as audit completeness only. Reconcile the durable
four-condition/five-condition canon relationship and stale live indexes in a
new authorized packet, then prepare Gate S0 evidence for Q01-Q11. Keep
scientific_verdict null until a separate human approval document.
```
