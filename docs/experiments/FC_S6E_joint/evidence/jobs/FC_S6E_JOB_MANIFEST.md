# FC-S6E Job Manifest

## Scope
- Arm launched/prepared: `A8_v2_joint_2pct` only.
- `A8_v2_joint_5pct`, Lmu7, Lmu8, L_structure, and G2 are not run.
- Stage3 and Metric-v1 are called only after the Stage2 checkpoint exists.

## Backend
- `setsid` detached shell is used for persistence.

## A8_v2_joint_2pct
- config_path: `results/FC_S6E_joint/configs/A8_v2_joint_2pct.yaml`
- seed: `0`
- checkpoint_path: `results/FC_S6E_joint/checkpoints/A8_v2_joint_2pct/ckpt/final.pt`
- train_log_path: `results/FC_S6E_joint/logs/A8_v2_joint_2pct.train_eval.log`
- render_evidence_path: `results/FC_S6E_joint/evidence_exports/A8_v2_joint_2pct`
- output_directory: `results/FC_S6E_joint/checkpoints/A8_v2_joint_2pct`
- stage3_evaluation_command: `python scripts/phase2_synthesis/fc_s6_stage3_metric_v1_eval.py --run-name A8_v2_joint_2pct --config results/FC_S6E_joint/configs/A8_v2_joint_2pct.yaml --checkpoint results/FC_S6E_joint/checkpoints/A8_v2_joint_2pct/ckpt/final.pt --rendered-evidence-root results/FC_S6E_joint/evidence_exports/A8_v2_joint_2pct --out-csv results/FC_S6E_joint/phase3_eval/a8_v2_joint_metrics_by_bid.csv --split-summary-csv results/FC_S6E_joint/phase3_eval/a8_v2_joint_split_summary.csv --win-loss-csv results/FC_S6E_joint/phase3_eval/a8_v2_joint_vs_a8_vs_geo_win_loss.csv`
- run_script: `results/FC_S6E_joint/jobs/run_A8_v2_joint_2pct.sh`
- launch_script: `results/FC_S6E_joint/jobs/launch_A8_v2_joint_2pct.sh`

## Status
- launch_status: prepared

## Launch Record
- launched_at: 2026-05-13T19:24:46+09:00
- launch_backend: setsid_detached
- process_id: 2860314
- nohup_log: results/FC_S6E_joint/logs/A8_v2_joint_2pct.nohup.out
