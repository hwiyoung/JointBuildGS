# FUS-W1 protocol amendment v3a — 06:30 hard cutoff removal

- Amendment ID: `FUS-W1-AMEND-V3A-20260725`
- Authorized by: 김휘영
- Authorization recorded: 2026-07-25 00:20:29 KST
- Applies to: `REMOTE_PROMPT_DISPATCH_V3_20260724.md` §7 only
- Pre-result state at authorization: Gate A measurements 0, learning runs 0, readout runs 0, scoring runs 0

## Locked change

The 2026-07-25 06:30 KST hard cutoff is removed. At 06:30 the unattended
driver records a status snapshot; it does not cancel an in-progress run, stop
the queue, or trigger scoring concurrently with learning.

The snapshot records, without interpretation or verdict:

- the last fully completed queue position;
- every completed building, arm, and repeat;
- the active building, arm, repeat, iteration, and latest checkpoint;
- elapsed time and measured throughput;
- incomplete stages and issues.

After the snapshot, execution continues in the original §7 priority order.
The minimum execution objective is the core group through arm A repeat 2.
The extension group continues after that objective and the queue may run to
exhaustion. Only an existing safety/catastrophe rule, a failed mandatory gate,
resource protection, queue exhaustion, or an explicit human stop may end it.

Point-cloud generation, readout, Roofer, and scoring remain serial and must not
run concurrently with learning. A partially trained run is never promoted to a
completed or judgeable run.

## Unchanged locks

- §0 preflight remains mandatory.
- §2 Gate A remains the learning-entry condition: per-building median residual
  at most 0.3 m and a negligible systematic offset, with at most one
  micro-registration attempt before fail-closed blocking.
- The §8 judgment scales, two-run rule, core/extension distinction, arm
  definitions, 30k iteration budget, and human-only judgment remain unchanged.
- All failure logging, RAM cgroup, serial execution, provenance, GT-separation,
  and fixed-artifact requirements remain unchanged.

This amendment takes precedence only over the 06:30 cutoff sentence in §7.
It does not convert elapsed time into an experimental acceptance criterion.
