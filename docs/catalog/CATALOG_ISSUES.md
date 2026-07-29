# Repository catalog issues

> Generated report. It records review work; it does not authorize cleanup or make scientific verdicts.

## Snapshot

| Measure | Count |
|---|---|
| Cataloged indexed files | 1548 |
| Files directly under docs/ | 69 |
| Distinct inferred families | 245 |
| Local Markdown links/embeds that do not resolve | 5 |
| Run directories | 171 |
| Run directories with one or more record gaps | 171 |

### Catalog document statuses

| Status | Files |
|---|---|
| canonical | 27 |
| canonical_candidate | 9 |
| orphan_candidate | 177 |
| superseded | 39 |
| superseded_candidate | 12 |
| supporting | 1282 |
| temporary | 2 |

### Run Git states

| Git state | Runs |
|---|---|
| ignored_no_tracked_record | 86 |
| indexed_record_present | 2 |
| tracked_record_present | 77 |
| untracked_no_tracked_record | 6 |

## Issue 1: docs-root sprawl

`docs/` currently has 69 indexed files directly at its root. The target architecture gives each experiment family one owner directory; no file is moved by this task.

| Inferred family | Root files |
|---|---|
| e5_c001_s3ap | 7 |
| boundary_map | 2 |
| e5_c001_s2 | 2 |
| codex_prompt_fig_mech1 | 1 |
| context_for_review | 1 |
| p2_index | 1 |
| p2_현재프레임_핸드오프 | 1 |
| progress_brief | 1 |
| for_advisor | 1 |
| research_status | 1 |
| session_handoff | 1 |
| w3_overseg_diagnosis | 1 |
| w4d_coacquired_crosscheck | 1 |
| d4_손실config_감사 | 1 |
| d6_prior_provenance | 1 |
| d6_shape_audit | 1 |
| d6_survey | 1 |
| d6_textureless_fidelity | 1 |
| e5_pilot_gate_검수_판정회부 | 1 |
| assembly_fidelity | 1 |
| observability_test | 1 |
| opacity_diag | 1 |
| overseg_faithfulness | 1 |
| oversegmentation_lever | 1 |
| 3b_레시피설계_레퍼런스기반 | 1 |
| 관문a진단 | 1 |
| 밤샘3과제_검수 | 1 |
| 승부의지도_s3판정안건 | 1 |
| genclose_density_assembly | 1 |
| genclose_direct_plane | 1 |
| genclose_flat_seed_scores | 1 |
| issues | 1 |
| manual_review_judgments | 1 |
| mononormal_diag | 1 |
| mvs_hole_check | 1 |
| planefit_baseline | 1 |
| pointcloud_attributes | 1 |
| population_aux | 1 |
| population_verify | 1 |
| qs_baseline178_scores | 1 |
| qs_rescore | 1 |
| recipe_registry | 1 |
| regression_input_snapshot | 1 |
| s3b0_alpha_sweep | 1 |
| s3b0_gate_scores | 1 |
| s3b0_hsweep | 1 |
| s3b0_mask_iou | 1 |
| s3b0_mono_reliability | 1 |
| s3b0_outline_observability | 1 |
| s3b0_p0prime_scores | 1 |

## Issue 2: unresolved local Markdown links

| Source | Line | Raw target | Resolved target |
|---|---|---|---|
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 10 | ../phase2_ablation_citygml/figures/fig_polyfit_steps_large.png | `docs/archive/pre_tum_results/phase2_ablation_citygml/figures/fig_polyfit_steps_large.png` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 6 | ../phase2_ablation_citygml/_gt_polyfit_test/summary.json | `docs/archive/pre_tum_results/phase2_ablation_citygml/_gt_polyfit_test/summary.json` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 7 | ../../src/stage3/polyfit_cli.cpp | `docs/archive/src/stage3/polyfit_cli.cpp` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 8 | ../../scripts/phase2_synthesis/gt_polyfit_test.py | `docs/archive/scripts/phase2_synthesis/gt_polyfit_test.py` |
| `docs/archive/pre_tum_results/stage3_polyfit_analysis/phase1_REPORT.md` | 9 | ../phase2_ablation_citygml/REPORT.md | `docs/archive/pre_tum_results/phase2_ablation_citygml/REPORT.md` |

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

## Issue 4: orphan candidates

A file is an orphan candidate only when it has no parsed inbound path reference and is not an explicit canonical seed, guide, manifest, or figure. This is a triage signal, not proof that the file is unnecessary.

| Path | Family | Type |
|---|---|---|
| `docs/CODEX_PROMPT_FIG_MECH1.md` | codex_prompt_fig_mech1 | document |
| `docs/CONTEXT_FOR_REVIEW.md` | context_for_review | document |
| `docs/P2_현재프레임_핸드오프.md` | p2_현재프레임_핸드오프 | document |
| `docs/W_D4_손실config_감사.md` | d4_손실config_감사 | report |
| `docs/W_E5_C001_S3Ap_Phase3_20260715.md` | e5_c001_s3ap | report |
| `docs/W_E5_pilot_gate_검수·판정회부_20260707.md` | e5_pilot_gate_검수_판정회부 | report |
| `docs/W_③b_레시피설계_레퍼런스기반_20260707.md` | 3b_레시피설계_레퍼런스기반 | report |
| `docs/W_관문A진단_20260725.md` | 관문a진단 | report |
| `docs/W_밤샘3과제_검수_20260717.md` | 밤샘3과제_검수 | report |
| `docs/W_승부의지도·S3판정안건_20260711.md` | 승부의지도_s3판정안건 | report |
| `docs/e5_c001_s2_mono_runtime.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_monodepth_precheck.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s3ap_boundary_propagation.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_fm_retri_rescore.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_perturbation.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_perturbation_cells.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_phase3_scores.csv` | e5_c001_s3ap | evidence_table |
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
| `docs/experiments/er3_review_sources.md` | er3_review_sources | document |
| `docs/experiments/tum2twin_surface_proxy_rv1/reports/metric_contract_rv1.md` | tum2twin_surface_proxy_rv1 | document |
| `docs/experiments/tum2twin_surface_proxy_rv1/reports/repo_audit_rv1_20260728_2327.md` | tum2twin_surface_proxy_rv1 | document |
| `docs/genclose_direct_plane.csv` | genclose_direct_plane | evidence_table |
| `docs/mononormal_diag.csv` | mononormal_diag | evidence_table |
| `docs/mvs_hole_check.csv` | mvs_hole_check | evidence_table |
| `docs/planefit_baseline.csv` | planefit_baseline | evidence_table |
| `docs/qs_baseline178_scores.csv` | qs_baseline178_scores | evidence_table |
| `docs/qs_rescore_pairs.csv` | qs_rescore | evidence_table |
| `docs/research/preregistration/fusion_w1/사전등록_관문A_v2·SE3채택재판정_20260725.md` | fusion_w1 | preregistration_or_lock |
| `docs/s3b0_gate_scores.csv` | s3b0_gate_scores | evidence_table |
| `docs/s3b0_hsweep.csv` | s3b0_hsweep | evidence_table |
| `docs/s3b0_mask_iou.csv` | s3b0_mask_iou | evidence_table |
| `docs/s3b0_mono_reliability.csv` | s3b0_mono_reliability | evidence_table |
| `docs/s3b0_outline_observability.csv` | s3b0_outline_observability | evidence_table |
| `docs/s3b0_p0prime_scores.csv` | s3b0_p0prime_scores | evidence_table |
| `docs/s3b0_semantic_lineage.md` | s3b0_semantic_lineage | document |
| `docs/사전등록_관문A_v2·SE3채택재판정_20260725.md` | 사전등록_관문a_se3채택재판정 | preregistration_or_lock |
| `docs/사전등록서_품질축본선_승인잠금v4_20260721.md` | 사전등록서_품질축본선_승인잠금 | preregistration_or_lock |
| `docs/사전등록서_품질축본선_초안v1.2_20260718.md` | 사전등록서_품질축본선_초안 | preregistration_or_lock |
| `docs/원격프롬프트_S2_방향자리_사슬4arm·선행묶음_20260710.md` | 원격프롬프트_s2_방향자리_사슬4arm_선행묶음 | document |
| `phases/p0-audit/docs/P0_입력치환Audit_실험설계서_v1_20260610.docx` | p0_입력치환audit_실험설계서 | binary_document |
| `phases/p0-audit/docs/W2_1_roofer_default.md` | w2_1_roofer_default | document |
| `phases/p0-audit/docs/W2_1b_als_roofer_failure_memo.csv` | w2_1b_als_roofer_failure_memo | evidence_table |
| `phases/p0-audit/docs/W2_1b_missing_roofer_exclusions.csv` | w2_1b_missing_roofer_exclusions | evidence_table |
| `phases/p0-audit/docs/W2_1b_paired_analysis.md` | w2_1b_paired_analysis | document |
| `phases/p0-audit/docs/W2_1b_paired_status.csv` | w2_1b_paired_status | evidence_table |
| `phases/p0-audit/docs/W2_1b_reason_crosstab.csv` | w2_1b_reason_crosstab | evidence_table |
| `phases/p0-audit/docs/W2_1c_coverage_sensitivity.csv` | w2_1c_coverage | evidence_table |
| `phases/p0-audit/docs/W2_1c_failure_bucket_summary.csv` | w2_1c_failure_bucket | report |
| `phases/p0-audit/docs/W2_1c_paired_status.csv` | w2_1c_paired_status | evidence_table |
| `phases/p0-audit/docs/W2_1c_quality_paired.md` | w2_1c_quality_paired | document |
| `phases/p0-audit/docs/W2_1c_reference_mismatch_exclusions.csv` | w2_1c_reference_mismatch_exclusions | evidence_table |
| `phases/p0-audit/docs/W2_1c_success_rates.csv` | w2_1c_success_rates | evidence_table |
| `phases/p0-audit/docs/W2_2_city3d_default.md` | w2_2_city3d_default | document |
| `phases/p0-audit/docs/W2_2_city3d_failure_reasons.csv` | w2_2_city3d_failure_reasons | evidence_table |
| `phases/p0-audit/docs/W2_2_city3d_paired_status.csv` | w2_2_city3d_paired_status | evidence_table |
| `phases/p0-audit/docs/W2_2_city3d_success_rates.csv` | w2_2_city3d_success_rates | evidence_table |
| `phases/p0-audit/docs/W2_2_roofer_city3d_2x2.csv` | w2_2_roofer_city3d_2x2 | evidence_table |
| `phases/p0-audit/docs/W2_2b_als_1200_sample.csv` | w2_2b_als_1200_sample | evidence_table |
| `phases/p0-audit/docs/W2_2b_als_val3dity_error_codes.csv` | w2_2b_als_val3dity_error_codes | evidence_table |
| `phases/p0-audit/docs/W2_2b_city3d_diagnosis.md` | w2_2b_city3d_diagnosis | document |
| `phases/p0-audit/docs/W2_2b_obj_representatives.csv` | w2_2b_obj_representatives | evidence_table |
| `phases/p0-audit/docs/W2_2b_val3dity_recheck_summary.csv` | w2_2b_val3dity_recheck | report |
| `phases/p0-audit/docs/W2_3a_bucket_summary.csv` | w2_3a_bucket | report |
| `phases/p0-audit/docs/W2_3a_dev_subset.csv` | w2_3a_dev_subset | evidence_table |
| `phases/p0-audit/docs/W2_3a_grid_results.csv` | w2_3a_grid_results | evidence_table |
| `phases/p0-audit/docs/W2_3a_paired_success.csv` | w2_3a_paired_success | evidence_table |
| `phases/p0-audit/docs/W2_3a_selected_params.csv` | w2_3a_selected_params | evidence_table |
| `phases/p0-audit/docs/W2_3a_tuned_paired_status.csv` | w2_3a_tuned_paired_status | evidence_table |
| `phases/p0-audit/docs/W2_3b_bucket_summary.csv` | w2_3b_bucket | report |
| `phases/p0-audit/docs/W2_3b_dim_variants.md` | w2_3b_dim_variants | document |
| `phases/p0-audit/docs/W2_3b_roof_matching_recovery.csv` | w2_3b_roof_matching_recovery | evidence_table |
| `phases/p0-audit/docs/W2_3b_variant_density_summary.csv` | w2_3b_variant_density | report |
| `phases/p0-audit/docs/W2_3b_variant_pointcloud_stats.csv` | w2_3b_variant_pointcloud_stats | evidence_table |
| `phases/p0-audit/docs/W2_3b_variant_status.csv` | w2_3b_variant_status | evidence_table |
| `phases/p0-audit/docs/W2_3b_variant_success.csv` | w2_3b_variant_success | evidence_table |
| `phases/p0-audit/docs/W3_1_roofer_quality.md` | w3_1_roofer_quality | document |
| `phases/p0-audit/docs/W3_1_roofer_quality_metrics.csv` | w3_1_roofer_quality | evidence_table |
| `phases/p0-audit/docs/W3_1_roofer_quality_summary.csv` | w3_1_roofer_quality | report |
| `phases/p0-audit/docs/W3_1_threshold_position.csv` | w3_1_threshold_position | evidence_table |
| `phases/p0-audit/docs/W3_1b_height_outlier_note.csv` | w3_1b_height_outlier_note | evidence_table |
| `phases/p0-audit/docs/W3_1b_internal_boundary_metrics.csv` | w3_1b_internal_boundary | evidence_table |
| `phases/p0-audit/docs/W3_1b_internal_boundary_summary.csv` | w3_1b_internal_boundary | report |
| `phases/p0-audit/docs/W3_1b_matching_validation.md` | w3_1b_matching_validation | document |
| `phases/p0-audit/docs/W3_1b_overlay_selection.csv` | w3_1b_overlay_selection | evidence_table |
| `phases/p0-audit/docs/W3_2b_roofer_repeatability_noise.csv` | w3_2b_roofer_repeatability_noise | evidence_table |
| `phases/p0-audit/docs/W3_2b_roofer_repeatability_success.csv` | w3_2b_roofer_repeatability_success | evidence_table |
| `phases/p0-audit/docs/W3_2b_roofer_repeatability_unstable_buildings.csv` | w3_2b_roofer_repeatability_unstable_buildings | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_closeout.md` | w3_2c_canonical_closeout | document |
| `phases/p0-audit/docs/W3_2c_canonical_input_bucket_summary.csv` | w3_2c_canonical_input_bucket | report |
| `phases/p0-audit/docs/W3_2c_canonical_internal_boundary_metrics.csv` | w3_2c_canonical_internal_boundary | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_internal_boundary_summary.csv` | w3_2c_canonical_internal_boundary | report |
| `phases/p0-audit/docs/W3_2c_canonical_paired_status.csv` | w3_2c_canonical_paired_status | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_priority_buckets.csv` | w3_2c_canonical_priority_buckets | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_roofer_quality_metrics.csv` | w3_2c_canonical_roofer_quality | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_roofer_quality_summary.csv` | w3_2c_canonical_roofer_quality | report |
| `phases/p0-audit/docs/W3_2c_canonical_success_rates.csv` | w3_2c_canonical_success_rates | evidence_table |
| `phases/p0-audit/docs/W3_2c_canonical_threshold_position.csv` | w3_2c_canonical_threshold_position | evidence_table |
| `phases/p0-audit/docs/W3_2c_quality_median_change.csv` | w3_2c_quality_median_change | evidence_table |
| `phases/p0-audit/docs/W3_failure_diagnosis.md` | w3_failure_diagnosis | document |
| `phases/p0-audit/docs/W3_failure_diagnosis_building_metrics.csv` | w3_failure_diagnosis_building | evidence_table |
| `phases/p0-audit/docs/W3_failure_diagnosis_control_summary.csv` | w3_failure_diagnosis_control | report |
| `phases/p0-audit/docs/W3_failure_diagnosis_thresholds.csv` | w3_failure_diagnosis_thresholds | evidence_table |
| `phases/p0-audit/docs/W3_failure_surface_cause.md` | w3_failure_surface_cause | document |
| `phases/p0-audit/docs/W3_failure_surface_cause_building_metrics.csv` | w3_failure_surface_cause_building | evidence_table |
| `phases/p0-audit/docs/W3_failure_surface_cause_control_summary.csv` | w3_failure_surface_cause_control | report |
| `phases/p0-audit/docs/W3_failure_surface_cause_thresholds.csv` | w3_failure_surface_cause_thresholds | evidence_table |
| `phases/p0-audit/docs/W3_figure_failure_story_metadata.json` | w3_figure_failure_story_metadata | structured_record |
| `phases/p0-audit/docs/W3_survivor_texture_gap.md` | w3_survivor_texture_gap | document |
| `phases/p0-audit/docs/W3_survivor_texture_gap_building_metrics.csv` | w3_survivor_texture_gap_building | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_gap_correlations.csv` | w3_survivor_texture_gap_correlations | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_gap_strata.csv` | w3_survivor_texture_gap_strata | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_building_metrics.csv` | w3_survivor_texture_refine_building | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_correlations.csv` | w3_survivor_texture_refine_correlations | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_strata.csv` | w3_survivor_texture_refine_strata | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_thresholds.csv` | w3_survivor_texture_refine_thresholds | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown.md` | w3_validity_error_breakdown | document |
| `phases/p0-audit/docs/W3_validity_error_breakdown_building_errors.csv` | w3_validity_error_breakdown_building_errors | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown_quality_attribution.csv` | w3_validity_error_breakdown_quality_attribution | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown_type_by_input.csv` | w3_validity_error_breakdown_type_by_input | evidence_table |
| `phases/p0-audit/docs/W4b_population_profile_building_metrics.csv` | w4b_population_profile_building | evidence_table |
| `phases/p0-audit/docs/W4b_population_profile_summary.csv` | w4b_population_profile | report |
| `phases/p0-audit/docs/W4c_no_points_breakdown.csv` | w4c_no_points_breakdown | evidence_table |
| `phases/p0-audit/docs/W4c_no_points_breakdown_meta.json` | w4c_no_points_breakdown_meta | structured_record |
| `phases/p0-audit/docs/dim_v1_classification_stats.md` | dim_classification_stats | document |
| `phases/p0-audit/docs/dim_v1_stats.md` | dim_stats | document |
| `phases/p0-audit/docs/footprints_summary.md` | footprints | report |
| `phases/p0-audit/docs/opf2colmap_summary.md` | opf2colmap | report |
| `phases/p0-audit/docs/scene_aoi_buildings.csv` | scene_aoi_buildings | evidence_table |

## Required human decisions before migration

1. Approve the target structure and metadata contract.
2. For one family, approve canonical, supporting, superseded, retracted, and draft statuses.
3. Distinguish broken links from intentionally unavailable external/local artifacts.
4. Decide which run payloads are class C versus regenerable class D.
5. Review an exact path/reference migration preview before any move.
