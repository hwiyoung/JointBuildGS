# Repository catalog issues

> Generated report. It records review work; it does not authorize cleanup or make scientific verdicts.

## Snapshot

| Measure | Count |
|---|---|
| Cataloged indexed files | 1853 |
| Files directly under docs/ | 2 |
| Distinct inferred families | 231 |
| Local Markdown links/embeds that do not resolve | 215 |
| Run directories | 177 |
| Run directories with one or more record gaps | 177 |

### Catalog document statuses

| Status | Files |
|---|---|
| canonical | 27 |
| canonical_candidate | 8 |
| orphan_candidate | 432 |
| superseded | 50 |
| superseded_candidate | 12 |
| supporting | 1323 |
| temporary | 1 |

### Run Git states

| Git state | Runs |
|---|---|
| ignored_no_tracked_record | 86 |
| indexed_record_present | 2 |
| tracked_record_present | 83 |
| untracked_no_tracked_record | 6 |

## Issue 1: docs-root sprawl

`docs/` currently has 2 indexed files directly at its root. The target architecture gives each experiment family one owner directory; no file is moved by this task.

| Inferred family | Root files |
|---|---|
| boundary_map | 1 |
| regression_input_snapshot | 1 |

## Issue 2: unresolved local Markdown links

| Source | Line | Raw target | Resolved target |
|---|---|---|---|
| `docs/archive/handoffs/P2_index_legacy.md` | 19 | GSJSO_loss_audit.md | `docs/archive/handoffs/GSJSO_loss_audit.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 25 | TUM_transfer_check.md | `docs/archive/handoffs/TUM_transfer_check.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 26 | TUM_quality_coverage.md | `docs/archive/handoffs/TUM_quality_coverage.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 27 | TUM_tsdf_roofer_probe.md | `docs/archive/handoffs/TUM_tsdf_roofer_probe.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 28 | TUM_noise_check.md | `docs/archive/handoffs/TUM_noise_check.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 38 | P2_makeorbreak_clean.md | `docs/archive/handoffs/P2_makeorbreak_clean.md` |
| `docs/archive/handoffs/P2_index_legacy.md` | 38 | experiments/p2_mob_past_results.md | `docs/archive/handoffs/experiments/p2_mob_past_results.md` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 10 | ../phase2_ablation_citygml/figures/fig_polyfit_steps_large.png | `docs/archive/pre_tum_results/phase2_ablation_citygml/figures/fig_polyfit_steps_large.png` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 6 | ../phase2_ablation_citygml/_gt_polyfit_test/summary.json | `docs/archive/pre_tum_results/phase2_ablation_citygml/_gt_polyfit_test/summary.json` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 7 | ../../src/stage3/polyfit_cli.cpp | `docs/archive/src/stage3/polyfit_cli.cpp` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 8 | ../../scripts/stage3_readout/gt_polyfit_test.py | `docs/archive/scripts/stage3_readout/gt_polyfit_test.py` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 9 | ../phase2_ablation_citygml/REPORT.md | `docs/archive/pre_tum_results/phase2_ablation_citygml/REPORT.md` |
| `docs/experiments/pilots/p2_makeorbreak/reports/P2_makeorbreak_clean.md` | 3 | ../../../P2_index.md | `docs/P2_index.md` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 113 | figures/phase1_visual_check_maxdiff/v2597_panel.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/phase1_visual_check_maxdiff/v2597_panel.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 121 | figures/phase1_visual_check_maxdiff/v3984_panel.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/phase1_visual_check_maxdiff/v3984_panel.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 122 | figures/phase1_visual_check_maxdiff/v4008_panel.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/phase1_visual_check_maxdiff/v4008_panel.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 199 | figures/structure_4way_bars.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/structure_4way_bars.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 231 | figures/contribution_decomposition.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/contribution_decomposition.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 259 | ../../tools/gs3d_4way_viewer/ | `docs/experiments/tools/gs3d_4way_viewer` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 56 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 73 | figures/render_compare_4way/render_compare_4way.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/render_compare_4way/render_compare_4way.png` |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | 95 | figures/wall_normal_distribution.png | `docs/experiments/joint-optimization/phase1_ablation/reports/figures/wall_normal_distribution.png` |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | 14 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_depth_normal/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | 74 | figures/comparison_4views.png | `docs/experiments/joint-optimization/phase1_depth_normal/reports/figures/comparison_4views.png` |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | 88 | figures/comparison_4views.png | `docs/experiments/joint-optimization/phase1_depth_normal/reports/figures/comparison_4views.png` |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | 89 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_depth_normal/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | 94 | run/tb/ | `docs/experiments/joint-optimization/phase1_depth_normal/reports/run/tb` |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | 114 | figures/mutual_effect.png | `docs/experiments/joint-optimization/phase1_mutual/reports/figures/mutual_effect.png` |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | 143 | figures/normal_distribution_all.png | `docs/experiments/joint-optimization/phase1_mutual/reports/figures/normal_distribution_all.png` |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | 177 | figures/render_compare_step13_step14.png | `docs/experiments/joint-optimization/phase1_mutual/reports/figures/render_compare_step13_step14.png` |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | 206 | figures/sem_compare_step13_step14.png | `docs/experiments/joint-optimization/phase1_mutual/reports/figures/sem_compare_step13_step14.png` |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | 71 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_mutual/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 116 | figures/semantic_diagnostic.png | `docs/experiments/joint-optimization/phase1_semantic/reports/figures/semantic_diagnostic.png` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 154 | figures/semantic_comparison.png | `docs/experiments/joint-optimization/phase1_semantic/reports/figures/semantic_comparison.png` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 154 | run/sem_views/ | `docs/experiments/joint-optimization/phase1_semantic/reports/run/sem_views` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 157 | figures/comparison_4views.png | `docs/experiments/joint-optimization/phase1_semantic/reports/figures/comparison_4views.png` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 158 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_semantic/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_semantic/reports/REPORT.md` | 16 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_semantic/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_structure/reports/REPORT.md` | 117 | figures/render_compare_step13_step15.png | `docs/experiments/joint-optimization/phase1_structure/reports/figures/render_compare_step13_step15.png` |
| `docs/experiments/joint-optimization/phase1_structure/reports/REPORT.md` | 125 | figures/sem_compare_step13_step15.png | `docs/experiments/joint-optimization/phase1_structure/reports/figures/sem_compare_step13_step15.png` |
| `docs/experiments/joint-optimization/phase1_structure/reports/REPORT.md` | 82 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_structure/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_structure/reports/REPORT.md` | 97 | figures/structure_histograms.png | `docs/experiments/joint-optimization/phase1_structure/reports/figures/structure_histograms.png` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 105 | figures/comparison_4views.png | `docs/experiments/joint-optimization/phase1_vanilla/reports/figures/comparison_4views.png` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 139 | run/renders_final/ | `docs/experiments/joint-optimization/phase1_vanilla/reports/run/renders_final` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 14 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_vanilla/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 142 | run/primitives.ply | `docs/experiments/joint-optimization/phase1_vanilla/reports/run/primitives.ply` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 143 | run/coverage/ | `docs/experiments/joint-optimization/phase1_vanilla/reports/run/coverage` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 144 | figures/comparison_4views.png | `docs/experiments/joint-optimization/phase1_vanilla/reports/figures/comparison_4views.png` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 145 | figures/training_curves.png | `docs/experiments/joint-optimization/phase1_vanilla/reports/figures/training_curves.png` |
| `docs/experiments/joint-optimization/phase1_vanilla/reports/REPORT.md` | 147 | run/tb/ | `docs/experiments/joint-optimization/phase1_vanilla/reports/run/tb` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 111 | figures/fig_d4_baseline_wall_tilt.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig_d4_baseline_wall_tilt.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 158 | figures/fig_d3_bid002_steps.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig_d3_bid002_steps.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 170 | figures/fig_d3_bid022_steps.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig_d3_bid022_steps.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 195 | figures/fig2_val3dity_bars.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig2_val3dity_bars.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 208 | figures/fig7_type_vs_condition.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig7_type_vs_condition.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 233 | figures/fig3_error_heatmap.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig3_error_heatmap.png` |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/REPORT.md` | 350 | figures/fig_polyfit_steps_large.png | `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/figures/fig_polyfit_steps_large.png` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 121 | figures/texture_before_after.png | `docs/experiments/input-and-alignment/phase2_synthesis/reports/figures/texture_before_after.png` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 16 | ../../scripts/stage3_readout/render_scene.py | `docs/experiments/scripts/stage3_readout/render_scene.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 17 | ../../src/stage2/train.py | `docs/experiments/src/stage2/train.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 170 | figures/render_samples.png | `docs/experiments/input-and-alignment/phase2_synthesis/reports/figures/render_samples.png` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 201 | ../../scripts/mutual_loss/benchmark_iter_speed.py | `docs/experiments/scripts/mutual_loss/benchmark_iter_speed.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 213 | ../../configs/mutual_loss/core_ablation/phase2_smoke.yaml | `docs/experiments/configs/mutual_loss/core_ablation/phase2_smoke.yaml` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 215 | ../../scripts/mutual_loss/fc3_diagnose.py | `docs/experiments/scripts/mutual_loss/fc3_diagnose.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 23 | ../../scripts/stage3_readout/select_block.py | `docs/experiments/scripts/stage3_readout/select_block.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 30 | block_3d.png | `docs/experiments/input-and-alignment/phase2_synthesis/reports/block_3d.png` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 36 | ../../scripts/stage3_readout/compose_scene.py | `docs/experiments/scripts/stage3_readout/compose_scene.py` |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | 96 | figures/flight_plan.png | `docs/experiments/input-and-alignment/phase2_synthesis/reports/figures/flight_plan.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 66 | figs/W_assembly/42364659.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/42364659.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 67 | figs/W_assembly/42364663.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/42364663.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 68 | figs/W_assembly/4907510.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/4907510.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 69 | figs/W_assembly/4906969.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/4906969.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 69 | figs/W_assembly/4906972.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/4906972.png` |
| `docs/experiments/evaluation/primary4_assembly_validation/reports/W_assembly_fidelity.md` | 69 | figs/W_assembly/4908023.png | `docs/experiments/evaluation/primary4_assembly_validation/reports/figs/W_assembly/4908023.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 154 | stageA/ | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/stageA` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 155 | stageB/ | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/stageB` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 42 | bid3_diag/ | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/bid3_diag` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 50 | figures/ | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 52 | figures/stageA_flat_b1.png | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures/stageA_flat_b1.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 53 | figures/stageA_gable_b8.png | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures/stageA_gable_b8.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 54 | figures/stageA_tri-slope_b0.png | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures/stageA_tri-slope_b0.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 55 | figures/stageA_hip_b5.png | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures/stageA_hip_b5.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 56 | figures/stageA_complex_b7.png | `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/figures/stageA_complex_b7.png` |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | 7 | ../../src/stage3/polyfit_cli.cpp | `docs/experiments/src/stage3/polyfit_cli.cpp` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 39 | B1/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B1/selected_surfaces.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 40 | B2/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B2/selected_surfaces.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 41 | B8/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B8/selected_surfaces.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 42 | B6/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B6/selected_surfaces.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 43 | B0/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B0/selected_surfaces.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/evidence_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/evidence_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/footprint_graph.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/footprint_graph.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/metrics.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/metrics.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/optional_roof_archetype.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/optional_roof_archetype.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/relation_readout.city.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/relation_readout.city.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/roof_surface_candidates.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/roof_surface_candidates.json` |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | 44 | B3/selected_surfaces.json | `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/B3/selected_surfaces.json` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 56 | B1/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B1/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 57 | B2/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B2/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 58 | B6/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B6/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 59 | B8/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B8/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 60 | B0/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B0/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/audit_report.md | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/audit_report.md` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/gt_mesh_with_plane_groups.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/gt_mesh_with_plane_groups.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/input_points_by_class.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/input_points_by_class.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/input_points_by_plane.ply | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/input_points_by_plane.ply` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/input_vs_gt_overlay_oblique_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/input_vs_gt_overlay_oblique_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/input_vs_gt_overlay_side_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/input_vs_gt_overlay_side_by_plane.png` |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | 61 | B3/input_vs_gt_overlay_top_by_plane.png | `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/B3/input_vs_gt_overlay_top_by_plane.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 111 | images/noise_quality_cross.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/noise_quality_cross.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 128 | images/sensitivity_ranking.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/sensitivity_ranking.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 143 | images/combined_vs_single.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/combined_vs_single.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 158 | images/roof_type_comparison.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/roof_type_comparison.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 160 | images/roof_type_heatmap.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/roof_type_heatmap.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 174 | images/structure_vs_semantic.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/structure_vs_semantic.png` |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | 226 | images/gt_vs_result_comparison.png | `docs/experiments/citygml-readout/synthetic_a/reports/images/gt_vs_result_comparison.png` |
| `docs/experiments/input-and-alignment/tum_transfer_preflight/reports/TUM_noise_check.md` | 3 | ../../../P2_index.md | `docs/P2_index.md` |
| `docs/experiments/input-and-alignment/tum_transfer_preflight/reports/TUM_quality_coverage.md` | 3 | ../../../P2_index.md | `docs/P2_index.md` |
| `docs/experiments/input-and-alignment/tum_transfer_preflight/reports/TUM_transfer_check.md` | 3 | ../../../P2_index.md | `docs/P2_index.md` |
| `docs/experiments/input-and-alignment/tum_transfer_preflight/reports/TUM_tsdf_roofer_probe.md` | 3 | ../../../P2_index.md | `docs/P2_index.md` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 17 | figs/W_D6_shape/42364659.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/42364659.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 17 | figs/W_D6_shape/42364663.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/42364663.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 17 | figs/W_D6_shape/4906969.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4906969.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 17 | figs/W_D6_shape/4906972.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4906972.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 17 | figs/W_D6_shape/4908023.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4908023.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/42364609.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/42364609.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/4907182.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4907182.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/4907510.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4907510.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/4908050.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4908050.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/4908166.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4908166.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 18 | figs/W_D6_shape/4908176.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4908176.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_shape_audit.md` | 19 | figs/W_D6_shape/4906969_yslice.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4906969_yslice.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_survey.md` | 85 | figs/W_D6/survey_overseg.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6/survey_overseg.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_textureless_fidelity.md` | 29 | figs/W_D6_textureless/4907182.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_textureless/4907182.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_textureless_fidelity.md` | 30 | figs/W_D6_textureless/42364609.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_textureless/42364609.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_textureless_fidelity.md` | 30 | figs/W_D6_textureless/4908050.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_textureless/4908050.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_D6_textureless_fidelity.md` | 30 | figs/W_D6_textureless/4908166.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_textureless/4908166.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 28 | figs/W_D6_shape/4906969_yslice.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_D6_shape/4906969_yslice.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 28 | figs/W_faithful/4906969_uav.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/4906969_uav.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 65 | figs/W_faithful/42364659.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/42364659.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 65 | figs/W_faithful/4906969.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/4906969.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 65 | figs/W_faithful/4906972.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/4906972.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 65 | figs/W_faithful/4907510.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/4907510.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_overseg_faithfulness.md` | 66 | figs/W_faithful/42364659_uav.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_faithful/42364659_uav.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 65 | figs/W_overseg/scatter.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/scatter.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/42364659.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/42364659.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/42364663.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/42364663.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/4906969.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/4906969.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/4906972.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/4906972.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/4907510.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/4907510.png` |
| `docs/experiments/evaluation/w_d6_overseg_diag/reports/W_oversegmentation_lever.md` | 66 | figs/W_overseg/4908023.png | `docs/experiments/evaluation/w_d6_overseg_diag/reports/figs/W_overseg/4908023.png` |
| `docs/research/status/REPORT_FOR_ADVISOR.md` | 254 | ../results/phase1_ablation/figures/semantic_compare_4way/semantic_compare_4way.png | `docs/research/results/phase1_ablation/figures/semantic_compare_4way/semantic_compare_4way.png` |
| `docs/research/status/REPORT_FOR_ADVISOR.md` | 275 | ../results/phase1_ablation/figures/structure_4way_bars.png | `docs/research/results/phase1_ablation/figures/structure_4way_bars.png` |
| `docs/research/status/REPORT_FOR_ADVISOR.md` | 298 | ../results/phase1_ablation/figures/render_compare_4way/render_compare_4way.png | `docs/research/results/phase1_ablation/figures/render_compare_4way/render_compare_4way.png` |
| `docs/research/status/REPORT_FOR_ADVISOR.md` | 310 | ../results/phase1_ablation/figures/contribution_decomposition.png | `docs/research/results/phase1_ablation/figures/contribution_decomposition.png` |
| `docs/research/status/REPORT_FOR_ADVISOR.md` | 417 | ../results/phase2_ablation_citygml/figures/fig7_type_vs_condition.png | `docs/research/results/phase2_ablation_citygml/figures/fig7_type_vs_condition.png` |

## Issue 3: run receipt gaps

These are gaps against the target run contract, not claims that a historical run violated the rules in force when it was created.

| Phase | Run ID | Git state | Issues |
|---|---|---|---|
| P0 | _d6_density | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | _d6_sweep | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_3b_s1_20260708_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_405_repair_20260709_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P0 | e5p_baseline_acmp_20260706_001813 | tracked_record_present | missing_tracked_manifest |
| P0 | e5p_baseline_sparse_20260706_002300 | tracked_record_present | missing_tracked_manifest |
| P0 | e5p_corrected_s1_20260709_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_corrected_s1_recheck_20260709_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_gate_20260707_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P0 | e5p_readout_ablation_20260708_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P0 | e5p_s1_full_factor_20260709_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s2_405_repair_20260710_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s2_direction_position_20260710_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s2p_405_repair_20260710_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s2p_interaction_20260710_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s3a_405_repair_20260713_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | e5p_s3a_semantic_guided_20260713_C001 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | mob_eval | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | mob_eval_density | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | mob_eval_v6sem | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t10_survivor_texture_gap_20260615_204851 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t11_survivor_texture_refine_20260615_212951 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t11_survivor_texture_refine_20260615_213358 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t12_figure_failure_story_20260615_223248 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t12_figure_failure_story_20260615_223346 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t12_figure_failure_story_20260615_223458 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t13_validity_error_breakdown_20260616_214359 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260616_231601 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_102137 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_102345 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_102858 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_103026 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_103904 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_104912 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_20260617_105027 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_final | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_fix | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_figures_v2 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t14_qualitative_model_render_20260616_220529 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t15_input_output_compare_20260616_224915 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t2_opf2colmap_20260611_133634 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t2_opf2colmap_20260611_133906 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_225241 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_230138 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_230936 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_231056 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_233132 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_233524 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_233721 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t3_mvs_20260611_233859 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t4_classify_20260612_114812 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t4_classify_20260612_114903 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t4_classify_20260612_120320 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t4_classify_20260612_130152 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t5_footprints_20260612_130959 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t6_diagnose_20260612_133308 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t6_diagnose_20260612_133533 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t6_diagnose_20260612_133811 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t6_diagnose_20260612_134108 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_failure_diagnosis_20260615_133845 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_failure_diagnosis_20260615_133921 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_failure_diagnosis_20260615_134149 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_vertical_20260612_141031 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_vertical_20260612_141401 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t7_vertical_20260612_141617 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t8_population_profile_20260615_142538 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t8_population_profile_20260615_143004 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t9_failure_surface_cause_20260615_202222 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t9_failure_surface_cause_20260615_203200 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | t9_failure_surface_cause_20260615_204200 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | tum_e2e | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | tum_e2e_proper | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | tum_floor | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | tum_floor_test | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | v6c_no_points | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_1_roofer_default_20260612_152729 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_1b_pair_analysis_20260612_154832 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_1c_quality_paired_20260612_161842 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_1d_bucket_relabel_20260612_173612 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_1d_bucket_relabel_20260612_final | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_2_city3d_default_20260612_175449 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_2b_city3d_diagnosis_20260612_191242 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_3a_roofer_tuning_20260612_202013 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_3b_dim_variants_20260612_204135 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_3b_dim_variants_20260612_205207 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w2_3b_dim_variants_20260612_205412 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w3_1_roofer_quality_20260612_210850 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w3_1b_roofer_quality_20260612_212501 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w3_1b_roofer_quality_20260612_212536 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w3_2b_roofer_repeatability_20260612_220747 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P0 | w3_2c_canonical_closeout_20260612_222618 | ignored_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260702_A0_projection_fix | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260702_A1_zeta_ls | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260702_A2_projection_gate_v2 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_aux_v4a | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_aux_v4b | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_cards_v4_kit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_datum_tie_overlay | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_datum_tie_v3 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_recipe_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260704_attr_v1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_2 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_3 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_regression_v1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_regression_v1_1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260707_e5_c001_8way | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260707_e5_c001_gsdiag | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260707_e5_pilot_attr_v1_3_append | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260707_e5_pilot_subst | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260708_d4_config_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260708_e5_c001_3b_s1 | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260708_e5_c001_3b_s1_render | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260708_e5_c001_readout_ablation | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260708_e5_c001_render_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260708_e5_c001_s1_cause_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260709_e5_c001_corrected_s1 | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260709_e5_c001_corrected_s1_recheck | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260709_e5_c001_s1_full_factor | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260710_e5_c001_s2_direction_position | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260710_e5_c001_s2p_interaction | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260713_e5_c001_s3_semantic_guided | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260713_e5_c001_s3_track0 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260714_e5_c001_s3ap_anchor_inventory | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260714_e5_c001_s3ap_fm_env | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260714_e5_c001_s3ap_fm_rescore | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260714_e5_c001_s3ap_fm_retriangulation | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_fm_retri_rescore | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase0_baselines | tracked_record_present | missing_tracked_versions |
| P2 | 20260715_e5_c001_s3ap_phase0_fm_dense | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase0_mononormal | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase1_seedprep | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase2_prepare | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase2_smoke | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase2_smoke_v2 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase2_smoke_v3 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260715_e5_c001_s3ap_phase3_archives | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260716_boundary_map | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260716_e5_c001_s3b0_measurements | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260716_genclose_flat_density | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260716_overnight_abc | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260716_qs_rescore | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260717_qs_cheap_refine_pilot | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260717_qs_rescore_fixed_conditions | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_boundary_map_v2 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_baseline178_rescore | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_cheap_refine_sweep | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_rescore_completeness_panel | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_repair_waves | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260719_boundary_map_v3 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260719_boundary_map_v3_driver | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260720_anchor_census | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260720_anchor_census_driver | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260720_anchor_census_supplement | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260720_anchor_census_supplement_driver | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260721_degradation_curve | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260721_degradation_curve_driver | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | 20260721_pilot_1wave | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260721_primary4_assembly_validation | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260721_primary4_assembly_validation_driver | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260722_pilot_1wave_readout | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260724_fusion_w1 | tracked_record_present | missing_tracked_versions |
| P2 | 20260724_pilot_1wave_report | tracked_record_present | missing_tracked_manifest;missing_tracked_versions |
| P2 | 20260726_fusion_w1_aprime | indexed_record_present | missing_tracked_versions |
| P2 | 20260727_fusion_w1_aprime_smoke_recovery | tracked_record_present | missing_tracked_manifest;missing_tracked_versions |
| P2 | 20260728_fusion_w1_dense_baseline_qualitative_v1 | indexed_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260728_fusion_w1_dense_baseline_qualitative_v5 | untracked_no_tracked_record | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index;no_tracked_run_receipt |
| P2 | e5p_const_20260706_235710 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_prep_20260706_235306 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_sparse_config_20260706_000204 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_train_20260707_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S5_loss_ledger_instrumentation | tracked_record_present | missing_tracked_versions |
| P2 | legacy-results-FC_S6C_lmutual_completion | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6D_directional_screening | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6E_joint | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6_componentwise_revised_lmutual_design_validation | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-footprint_conditioned_readout | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |

## Issue 4: orphan candidates

A file is an orphan candidate only when it has no parsed inbound path reference and is not an explicit canonical seed, guide, manifest, or figure. This is a triage signal, not proof that the file is unnecessary.

| Path | Family | Type |
|---|---|---|
| `docs/catalog/migrations/DOCS_ROOT_FINAL_PATHS.csv` | docs_root_final_paths | evidence_table |
| `docs/catalog/migrations/STORAGE_IA_01_20260730.md` | storage_ia_01 | document |
| `docs/evidence/evidence_cards_v2/evidence_cards_v2_qA.md` | evidence_cards | document |
| `docs/evidence/judgment_kit_v4/judgment_kit_v4_report.md` | judgment_kit | report |
| `docs/evidence/p0_g1_20260613/W3_failure_diagnosis.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_failure_surface_cause.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_overseg_diagnosis.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_qualitative_compare.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_survivor_texture_gap.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_survivor_texture_refine.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W3_validity_error_breakdown.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W4b_population_profile.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W4c_no_points_breakdown.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/W4c_no_points_breakdown.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W4d_coacquired_crosscheck.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/W_D6_gen_status.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_prior_provenance.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_shape_audit.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_shape_audit.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_survey.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_survey_by_type.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_survey_per_building.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_textureless_fidelity.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_D6_textureless_fidelity.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_assembly_fidelity.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_assembly_fidelity.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_observability_test.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_opacity_diag.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_overseg_faithfulness.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_overseg_faithfulness.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_oversegmentation_lever.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/W_oversegmentation_lever.md` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/captions.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/mcnemar_assembly.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/mcnemar_assembly.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/source_mapping.md` | p0_g1_20260613 | document |
| `docs/evidence/p0_g1_20260613/t10_survivor_texture_gap_building_metrics.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t10_survivor_texture_gap_correlations.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t10_survivor_texture_gap_strata.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t11_survivor_texture_refine_correlations.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t11_survivor_texture_refine_strata.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t11_survivor_texture_refine_thresholds.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t12_figure_failure_story_metadata.json` | p0_g1_20260613 | structured_record |
| `docs/evidence/p0_g1_20260613/t13_validity_error_breakdown_building_errors.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t13_validity_error_breakdown_quality_attribution.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t7_failure_diagnosis_building_metrics.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t7_failure_diagnosis_control_summary.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/t7_failure_diagnosis_thresholds.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/t9_failure_surface_cause_control_summary.csv` | p0_g1_20260613 | report |
| `docs/evidence/p0_g1_20260613/t9_failure_surface_cause_thresholds.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/w4b_population_profile_building_metrics.csv` | p0_g1_20260613 | evidence_table |
| `docs/evidence/p0_g1_20260613/w4b_population_profile_summary.csv` | p0_g1_20260613 | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/FC_S5_EXPERIMENT_REPORT.md` | fc_s5_loss_ledger_instrumentation | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase1_instrumentation/INSTRUMENTATION_REPORT.md` | fc_s5_loss_ledger_instrumentation | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase1_instrumentation/default_off_equivalence.md` | fc_s5_loss_ledger_instrumentation | document |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase2_diagnostics/LOSS_DIAGNOSTIC_REPORT.md` | fc_s5_loss_ledger_instrumentation | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase1_instrumentation/log_tag_check.csv` | fc_s5_loss_ledger_instrumentation | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/B104_terrain_drift_summary.csv` | fc_s5_loss_ledger_instrumentation | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/M10_metrics_by_bid.csv` | fc_s5_loss_ledger_instrumentation | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/M3_metrics_by_bid.csv` | fc_s5_loss_ledger_instrumentation | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/M5_metrics_by_bid.csv` | fc_s5_loss_ledger_instrumentation | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/diagnostic_split_summary.csv` | fc_s5_loss_ledger_instrumentation | report |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_completion/reports/phase0_design_freeze/FC_S6C_LMU5_8_DESIGN_FREEZE.md` | fc_s6c_lmutual_completion | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_completion/reports/phase1_proxy_audit/LMU5_8_SMOKE_RECOMMENDATION.md` | fc_s6c_lmutual_completion | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_completion/reports/phase1_proxy_audit/lmu5_8_proxy_metric_alignment.md` | fc_s6c_lmutual_completion | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_completion/tables/phase1_proxy_audit/lmu5_8_proxy_by_bid.csv` | fc_s6c_lmutual_completion | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/manifests/audit_boundary.json` | fc_s6c_lmutual_design_to_formula_audit | structured_record |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/reports/LMU_DESIGN_TO_FORMULA_AUDIT.md` | fc_s6c_lmutual_design_to_formula_audit | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/reports/lmu_next_step_decision.md` | fc_s6c_lmutual_design_to_formula_audit | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/reports/lmu_revision_recommendations.md` | fc_s6c_lmutual_design_to_formula_audit | document |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_expected_metric_table.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_gate_validity_table.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_gradient_path_table.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_precondition_table.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_proxy_readiness_table.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6C_lmutual_design_to_formula_audit/tables/lmu_target_formula_alignment.csv` | fc_s6c_lmutual_design_to_formula_audit | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/FC_S6D_DIRECTIONAL_SCREENING_REPORT.md` | fc_s6d_directional_screening | report |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/FC_S6D_NEXT_STEP_DECISION.md` | fc_s6d_directional_screening | document |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase0_config/A8_VS_GEO_CONFIG_CHECK.md` | fc_s6d_directional_screening | document |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase1_equivalence/default_off_equivalence.md` | fc_s6d_directional_screening | document |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase1_equivalence/gradient_scale_check.md` | fc_s6d_directional_screening | document |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase3_eval/B104_guard_report.md` | fc_s6d_directional_screening | report |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase3_eval/support_topology_report.md` | fc_s6d_directional_screening | report |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/reports/phase4_viewer/viewer_qa_notes.md` | fc_s6d_directional_screening | document |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/tables/phase0_config/a8_vs_geo_config_table.csv` | fc_s6d_directional_screening | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/tables/phase1_equivalence/formula_gradient_check.csv` | fc_s6d_directional_screening | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/tables/phase3_eval/a8_v2_geo_metrics_by_bid.csv` | fc_s6d_directional_screening | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/tables/phase3_eval/a8_v2_geo_split_summary.csv` | fc_s6d_directional_screening | report |
| `docs/experiments/joint-optimization/FC_S6D_directional_screening/tables/phase3_eval/a8_v2_geo_vs_a8_win_loss.csv` | fc_s6d_directional_screening | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/reports/phase0_inventory/A8_ACTIVE_TERMS.md` | fc_s6d_lmutual_directionality | document |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/reports/phase1_scale_audit/recommended_initial_weights.md` | fc_s6d_lmutual_directionality | document |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/reports/phase2_screening/FC_S6D_DIRECTIONAL_DECISION.md` | fc_s6d_lmutual_directionality | document |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/tables/phase0_inventory/directional_formula_table.csv` | fc_s6d_lmutual_directionality | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/tables/phase0_inventory/lbase_weight_table.csv` | fc_s6d_lmutual_directionality | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/tables/phase1_scale_audit/gradient_scale_audit.csv` | fc_s6d_lmutual_directionality | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/tables/phase2_screening/directional_metrics_by_bid.csv` | fc_s6d_lmutual_directionality | evidence_table |
| `docs/experiments/joint-optimization/FC_S6D_lmutual_directionality/tables/phase2_screening/directional_split_summary.csv` | fc_s6d_lmutual_directionality | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/FC_S6E_JOINT_SCREENING_REPORT.md` | fc_s6e_joint | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/FC_S6E_NEXT_STEP_DECISION.md` | fc_s6e_joint | document |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase0_implementation/L_SEMCAL_IMPLEMENTATION.md` | fc_s6e_joint | document |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase0_implementation/default_off_equivalence.md` | fc_s6e_joint | document |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase1_gradient_audit/gradient_cosine_report.md` | fc_s6e_joint | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase1_gradient_audit/recommended_joint_weights.md` | fc_s6e_joint | document |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase3_eval/B104_guard_report.md` | fc_s6e_joint | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase3_eval/support_topology_report.md` | fc_s6e_joint | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/reports/phase4_viewer/viewer_qa_notes.md` | fc_s6e_joint | document |
| `docs/experiments/joint-optimization/FC_S6E_joint/tables/phase0_implementation/semcal_formula_table.csv` | fc_s6e_joint | evidence_table |
| `docs/experiments/joint-optimization/FC_S6E_joint/tables/phase1_gradient_audit/gradient_scale_audit.csv` | fc_s6e_joint | evidence_table |
| `docs/experiments/joint-optimization/FC_S6E_joint/tables/phase3_eval/a8_v2_joint_metrics_by_bid.csv` | fc_s6e_joint | evidence_table |
| `docs/experiments/joint-optimization/FC_S6E_joint/tables/phase3_eval/a8_v2_joint_split_summary.csv` | fc_s6e_joint | report |
| `docs/experiments/joint-optimization/FC_S6E_joint/tables/phase3_eval/a8_v2_joint_vs_a8_vs_geo_win_loss.csv` | fc_s6e_joint | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase0_controls/IMPLEMENTATION_CONTROL_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase0_controls/default_off_equivalence.md` | fc_s6_componentwise_revised_lmutual_design_validation | document |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase1_existing_terms/TERM_DECOMPOSITION_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase2_terrain_safe/B104_TERRAIN_DRIFT_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase2_terrain_safe/TERRAIN_SAFE_REDESIGN_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase3_nonterrain_priors/NONTERRAIN_PRIOR_VALIDATION_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase4_revised_terms/REVISED_TERM_PROTOTYPE_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase5_candidate_selection/FC_S6_FINAL_DECISION.md` | fc_s6_componentwise_revised_lmutual_design_validation | document |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase_s6b_acceptance/FC_S6B_CANDIDATE_ACCEPTANCE_REPORT.md` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase_s6b_acceptance/viewer_qa_notes.md` | fc_s6_componentwise_revised_lmutual_design_validation | document |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/reports/phase_triage/FC_S6_ACTION_DECISION.md` | fc_s6_componentwise_revised_lmutual_design_validation | document |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase0_controls/lmutual_term_control_matrix.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase0_controls/logging_tags_available.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase1_existing_terms/term_ablation_metrics_by_bid.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase1_existing_terms/term_ablation_split_summary.csv` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase1_existing_terms/term_ablation_win_loss.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase2_terrain_safe/terrain_safe_metrics_by_bid.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase2_terrain_safe/terrain_safe_split_summary.csv` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase3_nonterrain_priors/nonterrain_prior_metrics_by_bid.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase3_nonterrain_priors/nonterrain_prior_split_summary.csv` | fc_s6_componentwise_revised_lmutual_design_validation | report |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase4_revised_terms/revised_term_metrics_by_bid.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase5_candidate_selection/revised_mutual_candidate_table.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase_s6b_acceptance/candidate_comparison_by_bid.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase_s6b_acceptance/classwise_support_comparison.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase_s6b_acceptance/topology_comparison.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/joint-optimization/FC_S6_componentwise_revised_lmutual_design_validation/tables/phase_triage/FC_S6_DECISION_TABLE.csv` | fc_s6_componentwise_revised_lmutual_design_validation | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/mononormal_diag.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/mvs_hole_check.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/planefit_baseline.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/reports/s3b0_semantic_lineage.md` | e5_c001_s3b | document |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_alpha_sweep.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_gate_scores.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_hsweep.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_mask_iou.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_mono_reliability.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_outline_observability.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_p0prime_scores.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_seed_survival_timeline.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/er3_review_sources.md` | er3_review_sources | document |
| `docs/experiments/pilots/fair_pilot/STAGING.md` | fair_pilot | document |
| `docs/experiments/pilots/fair_pilot/reports/baseline_mvs_stats.md` | fair_pilot | document |
| `docs/experiments/pilots/fair_pilot/reports/data_inventory.md` | fair_pilot | document |
| `docs/experiments/pilots/fair_pilot/tables/positive_control_candidates.csv` | fair_pilot | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/manifests/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase1_render_export/baseline_rendered_sample_bank_metadata.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/manifests/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase2_fixed_export/baseline_fixed_export_metadata.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/phase7_g2_feasibility/g2_groups.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/phase8_final_decision.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/val3dity_probe.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_acceptance_decision.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_inventory_decision.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/scene_evidence_graph_E1_Baseline_rendered.json` | footprint_conditioned_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S1_semantic_surface_readout/REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/E1_RECOVERY_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/RENDERED_COMPARISON_PRE_V1C.md` | footprint_conditioned_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_ground_closure/B104_GROUND_CLOSURE_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_height_definition/B6_HEIGHT_DEFINITION_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_roof_decomposition/ROOF_DECOMPOSITION_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_support_attribution/RENDERED_SUPPORT_ATTRIBUTION_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/PATCH_ABLATION_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseD_final_decision/G2_READINESS_DECISION.md` | footprint_conditioned_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/E1_E2_FULL_COMPARISON_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/MUTUAL_LOSS_ALIGNMENT_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/EVIDENCE_DISTRIBUTION_AUDIT.md` | footprint_conditioned_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/B104_field_replacement_report.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/B6_field_replacement_report.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/FIELD_REPLACEMENT_SUMMARY.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/roof_cases_field_replacement_report.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/FOOTPRINT_MASKING_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/MUTUAL_ABLATION_REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/FC_S3_FINAL_DECISION.md` | footprint_conditioned_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/g2_4way_pilot_plan.md` | footprint_conditioned_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/REPORT.md` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/viewer/stage3_qa.html` | footprint_conditioned_readout | other |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase0_inventory/target_buildings.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase1_evidence/evidence_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase3_surface_eval/surface_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase3_surface_eval/surface_metrics_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/geometry_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/summary_metrics.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/topology_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase5_comparison/baseline_vs_mutual.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase5_comparison/evidence_to_model_transfer.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase6_baseline_comparison/conventional_baseline_metrics.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase6_baseline_comparison/ours_vs_baseline.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase7_g2_feasibility/g2_group_metrics.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_candidate_artifacts.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_evidence_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_sanity_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_stage3_matrix_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_vs_e2_evidence_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase1_render_export/baseline_rendered_sample_bank_views.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/rendered_baseline_vs_mutual_pre_v1c.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_diagnostics_by_case.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_deltas_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_paired_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_split_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_win_loss_by_metric.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/gradient_norms_by_class.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/gradient_norms_by_loss.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/loss_to_metric_alignment_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/mutual_loss_components_by_class.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/e1_e2_classwise_evidence_stats.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/ground_y_distribution_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/roof_evidence_distribution_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/support_rejection_distribution_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/field_replacement_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/footprint_buffer_sweep_metrics.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/footprint_sensitivity_by_split.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_config_table.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_evidence_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_stage3_metrics.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/g2_target_selection.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase2_stage3_v1_readout/stage3_v1_patch_summary.csv` | footprint_conditioned_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/algorithm_effect_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/evaluator_effect_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/final_effect_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/matrix_metrics_by_bid.csv` | footprint_conditioned_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/matrix_summary_by_source.csv` | footprint_conditioned_readout | report |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/domain_metrics.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/geometry_metrics.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/rendering_metrics.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/semantic_metrics.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/structure_mutual_vs_base/structure_stats.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/structure_stats_step13_vs_step16.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/metrics/figures/wall_thickness.json` | phase1_ablation | structured_record |
| `docs/experiments/joint-optimization/phase1_ablation/reports/REPORT.md` | phase1_ablation | report |
| `docs/experiments/joint-optimization/phase1_ablation/reports/notes/figures/phase1_visual_check/README.txt` | phase1_ablation | document |
| `docs/experiments/joint-optimization/phase1_ablation/reports/notes/figures/phase1_visual_check_maxdiff/README.txt` | phase1_ablation | document |
| `docs/experiments/joint-optimization/phase1_ablation/reports/notes/figures/render_compare_4way/README.txt` | phase1_ablation | document |
| `docs/experiments/joint-optimization/phase1_ablation/reports/notes/figures/semantic_compare_4way/README.txt` | phase1_ablation | document |
| `docs/experiments/evaluation/phase1_analysis/metrics/g1_vs_g2_summary.json` | phase1_analysis | report |
| `docs/experiments/joint-optimization/phase1_depth_normal/reports/REPORT.md` | phase1_depth_normal | report |
| `docs/experiments/joint-optimization/phase1_mutual/metrics/figures/geometry_metrics.json` | phase1_mutual | structured_record |
| `docs/experiments/joint-optimization/phase1_mutual/metrics/figures/mutual_effect.json` | phase1_mutual | structured_record |
| `docs/experiments/joint-optimization/phase1_mutual/metrics/figures/rendering_metrics.json` | phase1_mutual | structured_record |
| `docs/experiments/joint-optimization/phase1_mutual/metrics/figures/semantic_metrics.json` | phase1_mutual | structured_record |
| `docs/experiments/joint-optimization/phase1_mutual/reports/REPORT.md` | phase1_mutual | report |

Only the first 250 of 432 orphan candidates are shown.

## Required human decisions before migration

1. Approve the target structure and metadata contract.
2. For one family, approve canonical, supporting, superseded, retracted, and draft statuses.
3. Distinguish broken links from intentionally unavailable external/local artifacts.
4. Decide which run payloads are class C versus regenerable class D.
5. Review an exact path/reference migration preview before any move.
