# Codex-to-Work Return — Gate S0 integrated freeze closure v1

## Identity

- task_id: `P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
- handoff_id: `P2-W2C-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
- accepted_commit: `9044993edb020732baae0a8b8e81591fa32d083c`
- offered_commit: `4d47fe3bf3f23aa631b9f9073ace4f2bf7572615`
- approval_commit: `58a3c2578cbb9aa91f982934bd75aa1ce1737bc2`
- actual_source_commit: `f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0`
- clerical_nonexistent_source_sha: `f3e0be62a67605727f0470c6373e0d78ea590ebb`
- technical_state: `BLOCKED`
- gate_decision: `null`
- scientific_verdict: `null`

## Answer first

Technical Gate S0 closure and P2 entry are **not supportable**. The integrated run
honored its one-pass ceiling, but the digest values were lost when C1 header parsing
failed on absent `pyproj`. The add-once marker prohibits a retry. C1/C4 derivatives,
the independent reference, per-ID eligibility and splits are therefore MISSING.

## Provenance correction

The immutable DRAFT packet contains a clerical nonexistent SHA. The actual immutable
DRAFT is `f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0`, proven as the direct parent of
approval commit `58a3c2578cbb9aa91f982934bd75aa1ce1737bc2`. Approval and offered ancestry are
otherwise exact. This Return and the new addendum record the correction; no prior
packet, approval, receipt, return, or canonical research document was amended.

## What completed

- Exact Experiment Host root/host/image acceptance and immutable 100 receipt.
- Common source choice 962/937/25 and component defaults.
- One pass across exactly four retained paths/eight files/986,484,109 bytes; no stereo
  enumeration. Hash values were computed in memory but not persisted.
- MVS terrain grid/derivative generation in process; gravity computed from terrain MVS
  normals in memory but value not persisted.
- EPSG:32632→25832 implementation and three-point PROJ 9.3.1 cross-check contract.
- Shared non-GT Stage-3 interface for all five labels, external-roofprint rejection,
  Docker tests, in-memory synthetic smoke, and exact cost caps.
- R2B lookup-accounting correction and source-SHA clerical addendum.
- Independent subagent reviews for leakage, artifact/reproducibility, and
  eligibility/splits/Stage-3.

## Failure and no-repeat accounting

Command:

```text
docker exec -u 1000:1000 jointbuildgs-dev bash -lc 'cd /workspace/JointBuildGS && python scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1/run_integrated_freeze.py --artifact-root /artifacts/JointBuildGS'
```

Operation ID: `58f1f62d461d5a45c0d740094ff5042701c6cae27a0278e3235ccc60a9f709d9`.
The selected byte assertion passed at 986,484,109 before C1. Then
`laspy.header.parse_crs()` raised `ModuleNotFoundError: No module named 'pyproj'`
before any C1 point chunk. Actual C1 header bytes read are unknown. C4 and all later
scientific sections were not accessed.

After failure, only six exact-path metadata probes were made: zero artifact content
bytes read/hashed and zero directory enumerations. They confirmed a 530-byte started
record and 5,464,707-byte MVS derivative. Content hashes are deliberately null.

The runner was repaired to tolerate missing `pyproj` by using frozen CRS provenance,
but was not rerun. The failed namespace and four retained paths must not be reread by
this task.

## Component state

| Component | State |
|---|---|
| source ancestry / 962-937-25 / defaults / cost caps | `READY` |
| retained producer route | `PARTIAL` |
| persisted selected-path/member hashes | `MISSING` |
| horizontal frame contract | `READY` |
| C1 vertical datum / persisted gravity | `MISSING` |
| C1 and C4 derivatives | `MISSING` |
| independent UAS reference | `MISSING` |
| C5 input provenance/leakage exclusion | `READY` |
| 199-row eligibility, `U_target`, `E_paired`, split | `MISSING` |
| Stage-3 common interface/smoke | `PARTIAL` |
| prohibited-access guard | `READY` |

## Independence statement

No LoD2 geometry asset was opened. The LoD2-derived coarse LoD1 is C5 input only and
was never an evaluation reference, crop, tuning source, or primary evidence. No
stable-ID join occurred because the independent reference was not frozen. No held-out,
Fusion W1, `R_ext`, C1-C5 performance, quality score, SfM/MVS regeneration, depth,
normal, confidence, segmentation, or GS run occurred.

## Receipt protocol

Because 100-accepted is already `artifact_verified`, the receipt validator requires
successor `artifacts` objects to remain byte-identical. The partial live output records
are explicit in
`artifacts/manifests/gate_s0/integrated_freeze_closure_v1/external_output_records_v1.json`.
The 200 receipt preserves the accepted preflight record and verifies this failure state
through Git records, tests and exact-path metadata only. The 300 close performs no
external artifact reread and returns writer ownership to Work Host.

## One next bounded action and needed user information

Human decision required: either keep Gate S0 blocked, or explicitly authorize a new
replacement task/namespace. A replacement would need, before acceptance, (1) approval
to make a new one-pass hash operation because the present task exhausted its pass,
(2) an admissible independent stable-ID spatial crosswalk, and (3) the C1 vertical
datum contract. No other user information is needed to close this failed handoff.

scientific_verdict: `null`
