## FUS-W1-APRIME-READOUT-RUNTIME-FAILURE — preserved attempt

- timestamp_utc: `2026-07-27T02:31:29.538010+00:00`
- job: `DEBY_LOD2_42364609/arm_Aprime/r1/attempt_004`
- stage: `finalize`
- error_type: `ExternalStageError`
- message: `wrapper stage exited nonzero: status=1`
- action: attempt artifacts and failure receipt retained; no verdict emitted.

## FUS-W1-APRIME-SMOKE-RECOVERY-FINALIZE-LEDGER-001 — zero-byte scorer lock

- observed_attempt: `attempt_004`
- observed_stage: `finalize`
- measured_cause: original artifact ledger rejected the closed zero-byte `primary/engine/scores.csv.lock` synchronization file.
- permission_error: `false`
- preservation: attempt 004 retained unchanged as 47 files, 4,246,166 bytes, tree SHA `1be09fe5f59eb5852bff2afb667e27f69aa60284de6e4135960ad710ffddd358`.
- retry: `attempt_005`; no retraining and no other queue job.
- handling: after scorer close, a nonblocking exclusive lock was acquired and the exact zero-byte synchronization file was moved to the append-only recovery quarantine.
- scientific_artifacts_moved: `0`
- retry_technical_state: `COMPLETE`
- scientific_verdict: `null`
