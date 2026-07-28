# FUS-W1 A-prime overnight-v4 repair1 lock

- Control namespace: `unattended_queue_overnight_v4_repair1`.
- The terminal `unattended_queue_overnight_v4` namespace is evidence-only and must not be rewritten.
- The original overnight recovery gate remains structurally unchanged: it still binds the terminal v3-repair1 source, the four producer-HEAD trainings, and the 20-job schedule.
- The additional `v4_readout_head_failure` section in `RECOVERY_LOCK.json` freezes the later v4 stop, its three identical `RUN_READOUTExternalError` receipts, and absence of canonical readout completion for all four historical jobs.
- Historical jobs are processed in this order: `42364663`, `4907182`, `4907510`, `4908050`. Their training artifacts are reused only after ancestor and identical-method proof.
- New training remains 15 jobs and requires the strict repair1 execution HEAD.
- Readout compatibility may relax only the training receipt HEAD equality for those four allowlisted, hash-bound jobs. It may not alter the checkpoint, preprocessing, TSDF, Roofer, scoring, panel, target list, or scientific recipe.
- The cache-fixed readout config, repair continuation lock, and historical-readout recovery lock are SHA/byte-bound before queue verification.
- Scientific interpretation and verdict are reserved for human review.
