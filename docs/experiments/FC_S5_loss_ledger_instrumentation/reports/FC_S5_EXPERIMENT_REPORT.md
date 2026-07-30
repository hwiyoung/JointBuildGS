# FC-S5 Experiment Report

## Scope

This run implements FC-S5 loss ledger instrumentation and cheap mutual diagnostics. It does not run full G2 training, does not enable `L_structure`, does not implement relation hints, and does not modify Stage3 or Metric-v1.

## Baseline Context

- FC-S3 E1 all-10 mean F: 0.822
- FC-S3 E2 all-10 mean F: 0.803
- FC-S3 E1 easy/control mean F: 0.942
- FC-S3 E2 easy/control mean F: 0.944
- FC-S3 E1 hard diagnostic mean F: 0.702
- FC-S3 E2 hard diagnostic mean F: 0.663

## 1. Were the loss ledger logs successfully added?

Yes. `phase1_instrumentation/INSTRUMENTATION_REPORT.md` records the smoke pass, requested ledger tags, class stats, gradient diagnostics, and disabled placeholder records.

## 2. Did default-off behavior remain unchanged?

Yes for the direct mutual tensor equivalence check recorded in `phase1_instrumentation/default_off_equivalence.md`.

## Diagnostic Runs

| run | status | completed OK rows | mean F | mean ground_cov | note |
| --- | --- | ---: | ---: | ---: | --- |
| M3 | EVALUATED | 10/10 | 0.812 | 0.873 | Reduced mutual weight; tests whether original mutual was too strong. |
| M5 | EVALUATED | 10/10 | 0.828 | 0.884 | Terrain terms disabled; tests B104-like terrain drift. |
| M10 | EVALUATED | 10/10 | 0.821 | 0.904 | Ramped mutual; tests early-geometry disturbance. |

## 3. Did M3 restore baseline-like stability?

Evaluated. all-10 mean F=0.812, ground_cov=0.873.

## 4. Did M5 reduce B104 terrain drift or recover ground_cov?

Evaluated. all-10 mean F=0.828, ground_cov=0.884.

## 5. Did M10 improve stability?

Evaluated. all-10 mean F=0.821, ground_cov=0.904.

## 6. Which run is the best revised mutual candidate, if any?

M5 is the current candidate by all-10 mean F gate.

## 7. Is it safe to proceed to relation-hint prototype?

Not until a revised mutual candidate ties or beats the baseline gates without B104/support/topology regressions.

## 8. Is it safe to proceed to L_structure prototype?

No. `L_structure` should remain disabled until revised mutual is stable under final Stage3Algo-v1 + Metric-v1 read-out.

## 9. Should the next step be full retraining, more loss redesign, or Stage3/evaluator work?

Pending final diagnostic metrics. If no candidate ties or beats the baseline gates, the next step remains loss redesign rather than full retraining.
