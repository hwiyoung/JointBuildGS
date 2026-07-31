# P1 Test and Reproduction Plan

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- environment rule: Docker only
- audit disposition: `READY_FOR_REVIEW`
- scientific_verdict: null

This plan separates P1 read-only verification from future Gate S0/P2
execution. P1 does not authorize GPU, training, download, installation,
held-out access, or mutation of active Fusion W1.

## P1 verification levels

| Level | Purpose | Allowed actions | Expected evidence |
|---|---|---|---|
| T0 | Repository/handoff integrity | Git reads, Docker validators | exact commits, clean scope, validator PASS |
| T1 | Contract/document integrity | read-only parsers and repository tests | required documents, statuses, null verdict, no forbidden paths |
| T2 | Reusable component tests | CPU/unit/contract tests in existing images | named test counts and exit codes |
| T3 | Exact artifact identity | targeted stat/hash/header reads | URI, bytes, SHA-256, CRS/datum evidence, lineage |
| S0 | Future data/split freeze | bounded non-held-out calibration after approval | AOI/split manifest, eligibility funnel, cost, common method locks |
| P2+ | Scientific execution | separately approved packet only | immutable run and result receipts |

## Reproduction commands

Run from the repository root in the existing project image. Do not install
missing software during P1.

```bash
python scripts/repository/validate_agent_instructions.py
python -m unittest tests.repository.test_agent_instruction_sync
python -m unittest tests.repository.test_two_host_handoff
```

The R2 offered and accepted receipt validators must use the ref appropriate to
their lifecycle event. The accepted event was already validated before push
against `HEAD` and after push against `origin/main`.

Component-level CPU/contract tests should include:

```bash
python -m unittest tests.stage2.test_rv1_pipeline
python -m unittest tests.fusion_w1.test_fusion_w1_dense_baseline_qualitative_v5_20260728
```

Add the discovered depth/normal-prior, schedule, seed-lineage, E5 occupied-cell
adapter, CityJSON, and metric modules to the bounded test manifest before Gate
S0. Record exact module names and counts rather than relying on test discovery
order.

## Artifact verification procedure

For every candidate promoted to `READY`:

1. Resolve through the checked-in manifest and canonical
   `JBGS_ARTIFACT_ROOT`.
2. Require one exact path; fail on ambiguity or basename substitution.
3. Record stat bytes and SHA-256. For large collections, use a deterministic
   per-file inventory and hash that inventory.
4. Inspect only headers or bounded samples needed for format, point count,
   bounds, class inventory, CRS, and datum claims.
5. Cross-check lineage receipt/config and survey identity.
6. Record which bytes were actually rehashed. A manifest-only match remains
   `PARTIAL`.

Do not compute an artifact-store directory hash. Do not open held-out outputs.

## P1 verification observations

| Check | Result | Interpretation |
|---|---|---|
| R2 pre-pull tuple and ancestry | PASS by two independent reviewers | Exact source, approval, offered, scope, and protected paths matched. |
| Offered validator in Docker | PASS | R2 technical handoff was valid. |
| Accepted pre-/post-push validator | PASS | Experiment Host acquired serialized-main write ownership. |
| Targeted artifact hashing | PASS for 12 payload candidates plus 1 pilot manifest, 13 files total | Bytes and hashes are recorded in `DATA_AND_COORDINATE_AUDIT.md`; fitness remains separate. |
| Qualitative v5 contract tests | 10/10 PASS in independent read-only review | Reproduces the frozen pilot contract, not the new C1–C5 program. |
| R_v1 metric tests | 8/8 PASS in independent read-only review | Supports component metrics, not unified G0–G4. |
| Prior/schedule/seed-lineage tests | 21/21 PASS in independent read-only review | Shows reusable primitives, not an approved C4/C5 method. |
| Pilot external verifier | 45 declared outputs and 11 receipts rehashed | `canonical_evidence_claim=false`; no scientific promotion. |
| E5 occupied-cell adapter contract test | FAIL before tests: missing `tests/e5_c001/e5_c001_s3ap_phase3.py` | Test path drift; implementation/lock remain present, readiness is PARTIAL. |
| LAS CRS parse in main image | FAIL: `ModuleNotFoundError: pyproj` | Reproduction/environment gap; no install attempted and P1 continued with VLR/datum evidence. |
| Live main CLI availability | Roofer/val3dity/cjval/ogr2ogr/PDAL absent | Separate pinned tools/routes are required. |

## Gate S0 reproduction bundle required

Before the first P2 baseline result, publish and human-freeze:

- exact AOI polygon and hash;
- `U_target` and `E_paired` building manifests with stable IDs, spatial groups,
  coverage flags, and exclusion reasons;
- the selected `EXHAUSTIVE_PARTITION` or approved fallback
  `STRATIFIED_SAMPLE`, seed/algorithm, and split IDs;
- one common C1–C5 image/camera ledger resolving the 962/937 discrepancy;
- C1 ULS class-2/6, vertical-datum, ground, registration, and coverage receipt;
- C4 ALS prior encoding, independence, registration, confidence, and derivative
  receipt;
- independent C5 LoD1 URI/hash/lineage and leakage guard;
- common `R_derived` code/config/image hashes and non-GT building association;
- extraction adapter choice, coordinate/gravity contract, and failure policy;
- per-condition bounded runtime, peak memory, output bytes, and retained-file
  estimate;
- result schema writer, CityJSON/CityGML policy, val3dity/cjval tooling, metric
  versions, and still-deferred criteria.

## Phase execution order

- P2 and P3 use the same development+validation building pool.
- P2 freezes C1–C3 baseline and criterion candidates without held-out access.
- P3 develops/freezes C4/C5 on that same pool and completes its final C1–C5
  matrix using exact-compatible results.
- P4 opens the isolated held-out set for the first time and runs frozen C1–C5
  on every held-out building.

Any path that requires GT geometry to assign, crop, or derive the honest-arm
surface is a failing test, not an implementation convenience.
