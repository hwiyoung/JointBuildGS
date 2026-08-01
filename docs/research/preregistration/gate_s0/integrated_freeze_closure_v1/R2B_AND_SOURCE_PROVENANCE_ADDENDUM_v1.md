# Gate S0 integrated-freeze provenance and R2B addendum v1

Task: `P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`

Status: `BLOCKED`; scientific_verdict: `null`.

## Clerical source-SHA correction

The DRAFT packet and initial execution prompt transcribed a nonexistent source SHA,
`f3e0be62a67605727f0470c6373e0d78ea590ebb`. The immutable DRAFT commit is
`f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0`, which is the direct parent of approval
commit `58a3c2578cbb9aa91f982934bd75aa1ce1737bc2`. Approval commit
`58a3c2578cbb9aa91f982934bd75aa1ce1737bc2` and offered commit
`4d47fe3bf3f23aa631b9f9073ace4f2bf7572615` remain unchanged. No DRAFT packet,
approval, 000 receipt, earlier return, or canonical record was amended.

All ancestry/source attestations in this task use the actual DRAFT commit
`f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0`.

## R2B interpretation and accounting correction

The retained producer route remains `STRONGLY_CORROBORATED_PRODUCER_ROUTE / PARTIAL`,
not an exact run-script attestation. A completed no-repeat lookup reads and hashes the
completed ledger itself. Only external scientific payloads and non-ledger outputs are
zero-read/zero-hash on a completed-ledger reuse. The integrated runner and tests record
both actual ledger bytes read and actual ledger bytes hashed.

## Integrated-run interruption

The add-once run wrote its started marker, completed the one allowed pass across the
four selected retained paths (four logical paths, eight regular files, 986,484,109
bytes read and hashed), and advanced to C1. The digest values and sparse member ledger
existed only in process memory. `laspy.header.parse_crs()` then failed because `pyproj`
was not installed, before any C1 point chunk was decoded and before the Git manifests
were persisted.

The started marker and partial MVS derivative make the operation non-repeatable under
the packet guard. No selected retained path or partial output was reread after failure.
Exact-path metadata-only probes found the 530-byte started record and 5,464,707-byte
MVS derivative; their recovery SHA-256 values remain `null` because no recovery content
read was allowed. The code now handles missing `pyproj` by preserving frozen CRS
provenance, but that repair was not rerun.

## LoD2/C5 independence

The independent UAS reference was not constructed. No LoD2 geometry asset was opened,
and no LoD2 coordinates were used for reference construction, registration, cropping,
tuning, or stopping. The LoD2-derived coarse LoD1 remains C5 input provenance only;
it is not an evaluation reference, crop, tuning source, or primary evidence.

The pre-run static design restricted the historical candidate ledger to identity-only
stable-ID parsing after a pre-ID reference freeze. Because the run failed before that
freeze, no stable-ID join, `U_target`, `E_paired`, or spatial split was emitted.

## Receipt-schema limitation

The immutable 100-accepted receipt is already `artifact_verified`. Repository receipt
validation requires every successor to preserve its entire `artifacts` object exactly.
Therefore the partial task-output records live in
`artifacts/manifests/gate_s0/integrated_freeze_closure_v1/external_output_records_v1.json`;
200 verification cites this manifest and exact-path metadata commands without changing
the accepted artifact attestation.
