# FC-S2 Phase A E1 Recovery Report

## Decision

- Final status: `REGENERATED_AND_ACCEPTED`
- Initial inventory status: `NOT_FOUND`
- Final E1 path: `results/footprint_conditioned_readout/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/E1_Baseline_rendered.npz`
- Accepted for Stage3 matrix: `True`
- Acceptance reason: E1 has non-empty roof/wall evidence for most target buildings and coordinate range matches E2.

## Search Result

No compatible pre-existing `E1_Baseline_rendered` NPZ was found. FC-S1 registered `results/stage3_rendered_evidence/baseline_rendered_evidence_NOT_AVAILABLE.npz`, exists=False.

## Regeneration Config

| Condition | E1 Baseline | E2 Mutual | Match |
| --- | --- | --- | --- |
| checkpoint | `results/phase2_ablation_citygml/baseline/ckpt/final.pt` | `results/phase2_ablation_citygml/mutual/ckpt/final.pt` | different by design |
| camera set | 56 views | 56 views | True |
| render downscale | 0.25 | 0.25 | True |
| pixel stride | 2 | 2 | True |
| depth convention | expected_z | expected_z | True |
| fusion | F2_class_normal_aware_voxel_0p05 | F2_class_normal_aware_voxel_0p05 | True |
| voxel size | 0.05 | 0.05 | True |
| gravity | [0, 1, 0] | [0, 1, 0] | True |

## Evidence Summary

| Source | nonempty_bids | roof_wall_nonzero_bids | ground_nonzero_bids | mean_n_points | mean_n_roof | mean_n_wall | mean_n_ground | normal_consistency | semantic_entropy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E1_Baseline_rendered | 10 | 10 | 10 | 9669.600 | 6969.000 | 2408.600 | 292.000 | 0.899 | 0.057 |
| E2_Mutual_rendered | 10 | 10 | 10 | 9688.600 | 6995.500 | 2433.000 | 260.100 | 0.897 | 0.044 |

## Sanity Gate

- Non-empty E1 target buildings: 10/10
- E1 roof/wall non-zero target buildings: 10/10
- E1 ground non-zero target buildings: 10/10
- Total invalid E1 coordinates after footprint crops: 0
- Mean E1/E2 coordinate range overlap: 0.966

## Files

- `e1_search_log.txt`
- `e1_candidate_artifacts.csv`
- `e1_inventory_decision.json`
- `E1_Baseline_rendered.npz`
- `baseline_rendered_regeneration_status.json`
- `e1_render_config.json`
- `e1_sanity_by_bid.csv`
- `e1_evidence_summary.csv`
- `e1_vs_e2_evidence_summary.csv`
- `e1_acceptance_decision.json`

No Stage3 algorithm changes were made. Track B was not started.
