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

### Resume disposition — 2026-07-25 00:40 KST

- The document is still absent; the provenance issue is not erased or represented as resolved.
- 김휘영 explicitly authorized continuation from the recorded blocker using the committed dispatch-v3 lock. This is recorded as `user_resume_override`, not as reconstruction or substitution of the missing document.
- The committed resume harness at `71e1a38ce88bbda7a448508cc95942b60402807e` reran all five pins: 5/5 passed or passed with the disclosed caveat; additional coordinate/class/datum, no-active-training, and serial-24g plan guards passed.
- The original BLOCKED manifest remained byte-identical (`sha256=1fff804ea6e30ef2d18f702fb67f4a38c0e225d561840311e685f15d5b4a5c38`).
- Resume preflight receipt: `preflight_resume.json`, `sha256=a38fbaf03999d3d6738dab72ce40024fcad15d608cf52d09bd9cee486c9c1b78`.
- Continuation scope: target resolution and Gate A only. Learning remains forbidden until the per-building LiDAR–image alignment gate passes.
- Counters remain `learning_runs_started=0`, `gate_a_measurements_started=0`, `readout_runs_started=0`.
