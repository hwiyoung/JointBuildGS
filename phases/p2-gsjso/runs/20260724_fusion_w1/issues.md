# FUS-W1 issues

## FUS-W1-PF-001 — canonical source document missing

- Recorded: 2026-07-24 23:28 KST
- Stage: §0 preflight, pin 5 mount freshness
- Status: BLOCKED
- Repetition count: 1
- Required path: `docs/W_면담정리_생성축재개·시드prior·문헌재조사_20260724.md`
- Evidence: absent from the host checkout, the live `/workspace/JointBuildGS` bind mount, every local Git ref/history path, and searched sibling checkouts.
- Controls: the committed dispatch, `boundary_map_v4_1_ladder.csv`, and the approved quality-axis preregistration have identical host/container SHA-256 values, so the bind mount is live for files that exist; the named 07-24 canonical source itself is unavailable.
- Action taken: stopped before target-queue generation, Gate A, seed preparation, P0′, learning, readout, Roofer, or scoring. No detached/background driver was launched.
- Recovery: supply the named canonical document with a verifiable hash/mtime, then rerun all five pins. Resolve the W1 datum value from that source before Gate A; do not substitute another document without 김휘영's direction.
- Counters: `learning_runs_started=0`, `gate_a_measurements_started=0`, `readout_runs_started=0`, `background_driver_launched=false`.
