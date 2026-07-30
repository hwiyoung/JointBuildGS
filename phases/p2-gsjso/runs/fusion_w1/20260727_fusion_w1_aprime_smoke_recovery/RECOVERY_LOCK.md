# FUS-W1-APRIME-SMOKE-RECOVERY-001 — 42364609 readout continuation lock

- Locked at: 2026-07-27 11:02 KST
- Branch: `exp/fusion-w1`
- Authorization: 김휘영, “그럼 42364609 나머지 진행하자.”
- Scope: `DEBY_LOD2_42364609 / arm_Aprime / r1 / attempt_004` only
- Source training: completed 30,000-update checkpoint from execution HEAD
  `de8852c00c737eced081f2627b49bcedddade652`
- Allowed work: primary TSDF fusion, Marching Cubes, class-6 surface sampling,
  original ALS class-2 join, Roofer, CityJSON, scoring, and the preregistered
  legacy-alpha comparison.
- Retraining: forbidden (`0` new optimizer updates).
- Other queue jobs: forbidden. The remaining 20 jobs are not started by this
  continuation.
- Source queue: the existing
  `STOPPED_SMOKE_BARRIER_NOT_MEASURED` receipt and attempts 001–003 remain
  immutable. This lock permits one append-only post-terminal attempt; it does
  not reopen or rewrite the stopped unattended queue.
- Reporting: measurements and artifacts only; scientific verdict remains
  reserved for human review.

The machine-readable contract, exact source artifact SHA-256 values, allowed
Git descendant paths, and failure signature are recorded in
`recovery_lock.json` beside this file.
