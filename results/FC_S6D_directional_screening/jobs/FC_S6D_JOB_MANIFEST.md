# FC-S6D-2 Job Manifest

## Scope
- Arm launched/prepared: `A8_v2_geo` only.
- `A8_v2_joint`, `Lmu7`, `L_structure`, and G2 are not run.
- Stage3 and Metric-v1 are called only after the Stage2 checkpoint exists.

## Backend
- `sbatch`: unavailable in this environment.
- `tmux`: unavailable in this environment.
- `nohup`: available; launch script uses direct nohup.

## A8_v2_geo
- config_path: `results/FC_S6D_directional_screening/configs/A8_v2_geo.yaml`
- seed: `0`
- checkpoint_path: `results/FC_S6D_directional_screening/checkpoints/A8_v2_geo/ckpt/final.pt`
- train_log_path: `results/FC_S6D_directional_screening/logs/A8_v2_geo.train_eval.log`
- render_evidence_path: `results/FC_S6D_directional_screening/evidence_exports/A8_v2_geo`
- output_directory: `results/FC_S6D_directional_screening/checkpoints/A8_v2_geo`
- stage3_evaluation_command: `python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name A8_v2_geo --config results/FC_S6D_directional_screening/configs/A8_v2_geo.yaml --checkpoint results/FC_S6D_directional_screening/checkpoints/A8_v2_geo/ckpt/final.pt --rendered-evidence-root results/FC_S6D_directional_screening/evidence_exports/A8_v2_geo --out-csv results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_metrics_by_bid.csv --split-summary-csv results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_split_summary.csv --win-loss-csv results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_vs_a8_win_loss.csv`
- run_script: `results/FC_S6D_directional_screening/jobs/run_A8_v2_geo.sh`
- launch_script: `results/FC_S6D_directional_screening/jobs/launch_A8_v2_geo.sh`

## Status
- launch_status: prepared

## Launch Record
- launched_at: 2026-05-13T13:46:40+09:00
- launch_backend: direct_nohup
- process_id: 2122622
- nohup_log: results/FC_S6D_directional_screening/logs/A8_v2_geo.nohup.out

## Relaunch Record
- launched_at: 2026-05-13T13:47:51+09:00
- launch_backend: direct_nohup_manual
- process_id: 2125384
- nohup_log: results/FC_S6D_directional_screening/logs/A8_v2_geo.nohup.out
- note: restarted after foreground debug run was stopped and partial output cleaned

## Relaunch Record
- launched_at: 2026-05-13T13:48:56+09:00
- launch_backend: setsid_detached
- process_id: see A8_v2_geo_job_record and ps
- nohup_log: results/FC_S6D_directional_screening/logs/A8_v2_geo.nohup.out
- note: simple nohup was not persistent in this tool session; relaunched with setsid
- active_parent_pid: 2127785
- active_train_pid: 2127800
- current_status: running Stage2 training
