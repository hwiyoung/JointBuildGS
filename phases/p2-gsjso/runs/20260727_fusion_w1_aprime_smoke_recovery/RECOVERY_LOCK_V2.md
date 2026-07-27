# FUS-W1-APRIME-SMOKE-RECOVERY-LOCK-002 — dedicated adapter layout

The v1 recovery lock remains immutable and retains the scientific/runtime
scope.  This v2 lock narrows the implementation layout after a read-only audit:

- keep the stopped unattended queue, original readout driver/wrapper/config,
  and immutable partial report unchanged;
- add a dedicated one-job continuation adapter/config/wrapper/test;
- publish all new runtime artifacts below
  `phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/`;
- allow only `DEBY_LOD2_42364609 / Aprime / r1 / attempt_004`;
- reuse the SHA-pinned 30k checkpoint without materialization or training;
- use the exact writable non-root cache paths already exercised by T2;
- leave the other 20 queue jobs unstarted.

The exact v1 binding and expanded Git descendant allowlist are stored in
`recovery_lock_v2.json`.
