# FC-S5 Phase 2 Job Preparation Report

## Launcher Selection

- Slurm `sbatch`: not available.
- `tmux`: not available.
- `nohup`: available at `/usr/bin/nohup`.

Diagnostics were submitted once as a sequential nohup chain so the runs would not compete for the same default CUDA device. The first sequence started M3 but exited before a checkpoint was produced. The launch scripts were then updated to use `setsid` plus `nohup`, and the sequence was resubmitted on CUDA-visible GPU 1.

## Current Submission

- M3 Stage2 status: completed, `final.pt` produced.
- M3 evaluation status: completed after fixing the FC-S5 adapter call to the existing Stage3-v1 signature.
- M5/M10 remaining-chain PID: `882191`
- Active job: M5
- Active job PID: `882197`
- Active train PID: `882216`
- Remaining chain submitted at: `2026-05-09T16:03:41+09:00`
- M5 verification: running on CUDA-visible GPU 1.
- M10 status: queued after M5.
- Finalization watcher PID: `887259`

## Prepared Jobs

| job | config | launcher | log |
| --- | --- | --- | --- |
| M3 | `configs/fc_s5/M3_reduced_mutual.yaml` | `launch_M3.sh` | `logs/M3.log` |
| M5 | `configs/fc_s5/M5_terrain_off.yaml` | `launch_M5.sh` | `logs/M5.log` |
| M10 | `configs/fc_s5/M10_ramped_mutual.yaml` | `launch_M10.sh` | `logs/M10.log` |

## Manifest

Prepared job metadata is recorded in `job_manifest.csv`. Each job record includes command used, git commit, config path, output directory, seed, checkpoint path, log path, and an FC-S5 Stage3Algo-v1 + Metric-v1 evaluation guard command. The guard refuses to substitute the older checkpoint-to-CityJSON evaluator when rendered evidence has not been exported.

Phase 6 evaluation is prepared and active:
- adapter: `scripts/phase2_synthesis/fc_s5_stage3_metric_v1_eval.py`
- batch script: `evaluate_completed.sh`
- detached launcher: `launch_evaluate_completed.sh`
- watcher: `watch_remaining_then_finalize.sh`
- verification: `python -m py_compile` passed. M3 rendered evidence export and Stage3Algo-v1 + Metric-v1 evaluation completed; M5/M10 evaluation will run after their checkpoints are produced.

## Run Policy

These jobs are Stage2 cheap diagnostics only. They do not run G2 training, do not enable `L_structure`, and do not modify Stage3 or Metric-v1.
