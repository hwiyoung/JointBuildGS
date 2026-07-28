# A-prime overnight-v4 recovery lock

- Source control namespace `unattended_queue_continuation_v3_repair1` is terminal and immutable.
- Its three consecutive readout skips came from a shared cache-probe receipt whose recorded HEAD was `598eff…`, while the producer/current queue HEAD was `191b565…`.
- Readout now uses this namespace's independent continuation lock, cache-probe receipt, and quarantine paths.
- Four already-completed A-prime r1 trainings may be reused only when `191b565…` is an ancestor of the execution HEAD and every producer method file has the same current SHA and Git blob. Materialization, started, completed, step-30000 checkpoint, and final checkpoint bindings remain mandatory.
- Every other training is materialized and launched strictly at the execution HEAD.
- Quantitative readout remains globally serial on GPU1. Review publication uses the one-file panel-v4 hook. The target list, pair ordering, scientific recipe, failure thresholds, and no-verdict rule are unchanged.
- The queue is unattended, has no time cutoff, and never rewrites the old terminal namespace.
