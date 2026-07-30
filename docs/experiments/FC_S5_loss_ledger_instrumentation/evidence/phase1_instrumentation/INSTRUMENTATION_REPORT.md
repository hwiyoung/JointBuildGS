# FC-S5 Phase 1 Instrumentation Report

## Result

Status: PASS for implementation smoke.

The trainer produced the requested FC-S5 mutual ledger tags, class stats, gradient diagnostics, and explicit disabled records for relation/calibration placeholders.

## Smoke Run

- Config: `configs/fc_s5/smoke_audit.yaml`
- Log: `results/FC_S5_loss_ledger_instrumentation/phase1_instrumentation/smoke_log.txt`
- TensorBoard event: `results/FC_S5_loss_ledger_instrumentation/phase1_instrumentation/smoke_run/tb/events.out.tfevents.1778249083.innopam-AI.3315587.0`
- Tag check: `results/FC_S5_loss_ledger_instrumentation/phase1_instrumentation/log_tag_check.csv`
- All requested smoke tags present: `True`

## Default-Off Behavior

Default-off equivalence is recorded in `default_off_equivalence.md`. Audit logging is disabled by default, gradient diagnostics are disabled by default, class stats are disabled by default, and evidence snapshots remain offline-only by default.

## Disabled Placeholders

The following are not active loss terms in FC-S5 and are logged as disabled placeholders when audit logging is enabled:

- `loss/mutual_sem_geom_calib`
- `loss/mutual_roof_wall_relation`
- `loss/mutual_terrain_wall_relation`

Each receives a NaN scalar tag plus a text status tag with `disabled`, so it is not reported as a zero-valued active term.

## Stage3 and Metric-v1

No Stage3 or Metric-v1 code was modified in this phase.
