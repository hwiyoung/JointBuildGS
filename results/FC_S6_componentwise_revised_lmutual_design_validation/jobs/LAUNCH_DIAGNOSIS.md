# FC-S6 Launch Diagnosis

## Observed Failure

The first Phase 1 attempt used the plain `nohup` fallback:

- submitted_at: `2026-05-10T00:25:34+09:00`
- launcher: `nohup`
- sequence pid: `1743902`
- first arm: `A0_baseline_w0`

`A0_baseline_w0` reached data loading and the training progress bar, but stopped before the first completed TensorBoard scalar or checkpoint:

- last log state: `train: 0%| 0/12000`
- no `train_exit_status` was written to `A0_baseline_w0_job_record.txt`
- no `final.pt` was written
- `A1-A9` were not started

This means the wrapper process disappeared before it could record the train exit status. It was not a normal Python exception path from `src.stage2.train`.

## Cause Isolation

A foreground smoke run of the same A0 config with `max_iter=2` completed successfully. That ruled out an immediate config/training-code crash.

A detached background survivability test showed:

- plain `nohup`: did not survive
- `setsid`: survived
- `systemd-run --user`: survived

Conclusion: the first Phase 1 attempt was killed by the execution environment's handling of plain detached `nohup` children, not by FC-S6 loss code or Stage2 config.

## Fix Applied

The launch scripts now prefer:

1. `sbatch`
2. `tmux`
3. `setsid`
4. plain `nohup`

Phase 1 was relaunched with `setsid`:

- submitted_at: `2026-05-10T06:56:49+09:00`
- sequence pid: `2417451`
- active train pid at verification: `2417472`
- active arm: `A0_baseline_w0`

The A0 log advanced past the previous failure point, confirming the relaunch path is working.

## Current Policy

Do not treat the failed `nohup` attempt as experiment evidence. It is a launcher failure only.

Do not claim FC-S6 Phase 1 results until each arm writes a final checkpoint, rendered evidence, and Stage3Algo-v1 + Metric-v1 rows.
