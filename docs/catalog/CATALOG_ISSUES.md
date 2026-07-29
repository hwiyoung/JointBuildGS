# Repository catalog issues

> Generated report. It records review work; it does not authorize cleanup or make scientific verdicts.

## Snapshot

| Measure | Count |
|---|---|
| Cataloged indexed files | 1308 |
| Files directly under docs/ | 442 |
| Distinct inferred families | 285 |
| Local Markdown links/embeds that do not resolve | 2 |
| Run directories | 157 |
| Run directories with one or more record gaps | 157 |

### Catalog document statuses

| Status | Files |
|---|---|
| canonical | 8 |
| canonical_candidate | 3 |
| orphan_candidate | 260 |
| superseded | 16 |
| superseded_candidate | 6 |
| supporting | 1011 |
| temporary | 4 |

### Run Git states

| Git state | Runs |
|---|---|
| ignored_no_tracked_record | 86 |
| indexed_record_present | 2 |
| tracked_record_present | 63 |
| untracked_no_tracked_record | 6 |

## Issue 1: docs-root sprawl

`docs/` currently has 442 indexed files directly at its root. The target architecture gives each experiment family one owner directory; no file is moved by this task.

| Inferred family | Root files |
|---|---|
| e5_c001 | 127 |
| e5_c001_s3 | 36 |
| e5_c001_s2 | 31 |
| e5_c001_s2p | 30 |
| boundary_map | 22 |
| e5_c001_s3ap | 17 |
| pointcloud_attributes | 7 |
| anchor_census_supplement | 5 |
| anchor_census | 4 |
| attr_outcome_regression | 4 |
| degradation_curve | 4 |
| bucket_crosswalk | 4 |
| projection_gate | 4 |
| primary4_assembly_validation | 3 |
| population_aux | 3 |
| qs_cheap_refine_sweep | 3 |
| qs_rescore | 3 |
| e5_pilot_substantiveness | 2 |
| evidence | 2 |
| e5_pilot_block | 2 |
| projection_zeta_ls | 2 |
| qs_baseline178 | 2 |
| claude_web_brief | 1 |
| codex_prompt_fig_mech1 | 1 |
| context_for_review | 1 |
| experiment_plan | 1 |
| gsjso_loss_audit | 1 |
| p2_index | 1 |
| p2_makeorbreak_clean | 1 |
| p2_현재프레임_핸드오프 | 1 |
| progress_brief | 1 |
| for_advisor | 1 |
| research_context | 1 |
| research_status | 1 |
| session_handoff | 1 |
| tum_noise_check | 1 |
| tum_quality_coverage | 1 |
| tum_transfer_check | 1 |
| tum_tsdf_roofer_probe | 1 |
| w3_overseg_diagnosis | 1 |
| w4d_coacquired_crosscheck | 1 |
| d12_metric | 1 |
| d2_d3 | 1 |
| d4 | 1 |
| d4_precheck | 1 |
| d4_손실config_감사 | 1 |
| d5 | 1 |
| d6_overseg_diag | 1 |
| d6_prior_provenance | 1 |
| d6_shape_audit | 1 |

## Issue 2: unresolved local Markdown links

| Source | Line | Raw target | Resolved target |
|---|---|---|---|
| `docs/W_D2_D3.md` | 47 | docs/W2_3a_roofer_tuning.md | `docs/W2_3a_roofer_tuning.md` |
| `docs/W_observability_inventory.md` | 83 | 0.5×0.5 km | `docs/0.5×0.5 km` |

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
| P2 | 20260706_attr_v1_3 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
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
| `docs/W_D_followup_audit.md` | d_followup_audit | report |
| `docs/W_E5_C001_S1원인감사_검수·라우팅_20260708.md` | e5_c001 | report |
| `docs/W_E5_C001_S2_checkpoint_20260710.md` | e5_c001_s2 | report |
| `docs/W_E5_C001_S3Ap_FM재삼각측량_20260714.md` | e5_c001_s3ap | report |
| `docs/W_E5_C001_S3Ap_FM재채점_20260715.md` | e5_c001_s3ap | report |
| `docs/W_E5_C001_S3Ap_Phase0_20260715.md` | e5_c001_s3ap | report |
| `docs/W_E5_C001_S3Ap_Phase1_20260715.md` | e5_c001_s3ap | report |
| `docs/W_E5_C001_S3Ap_Phase3_20260715.md` | e5_c001_s3ap | report |
| `docs/W_E5_C001_S3_의미유도.md` | e5_c001_s3 | report |
| `docs/W_E5_C001_corrected-S1_검수·라우팅_20260709.md` | e5_c001 | report |
| `docs/W_E5_C001_③a_readout재실행.md` | e5_c001 | report |
| `docs/W_E5_pilot_prep.md` | e5_pilot_prep | report |
| `docs/W_attr_outcome_regression.md` | attr_outcome_regression | report |
| `docs/W_matched_rms.md` | matched_rms | report |
| `docs/W_qs_rescore_completeness_panel_20260718.md` | qs_rescore_completeness_panel | report |
| `docs/W_report_evidence.csv` | evidence | report |
| `docs/W_밤샘3과제_검수_20260717.md` | 밤샘3과제_검수 | report |
| `docs/W_승부의지도·S3판정안건_20260711.md` | 승부의지도_s3판정안건 | report |
| `docs/W_재소집안건지_S3A프라임_20260714.md` | 재소집안건지_s3a프라임 | report |
| `docs/aux_v4_change_report.md` | aux_change | report |
| `docs/aux_v4b_change_report.md` | aux_v4b_change | report |
| `docs/bucket_crosswalk.md` | bucket_crosswalk | document |
| `docs/datum_tie.md` | datum_tie | document |
| `docs/datum_tie_overlay.md` | datum_tie_overlay | document |
| `docs/e5_c001_3b_s1_filter_contrib.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_inventory.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_3b_s1_render_cause_attribution.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_render_condition_strata.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_render_depth_supervision.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_render_eval_metrics.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_render_floater_metrics.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_render_readout_coverage.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_representative_buildings.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_3b_s1_summary.csv` | e5_c001 | report |
| `docs/e5_c001_3b_s1_tradeoff.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_filter_contrib.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_inventory.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_corrected_s1_recheck_building_8way.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_recheck_filter_contrib.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_recheck_inventory.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_recheck_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_corrected_s1_recheck_preprune_coverage.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_recheck_readout_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_corrected_s1_recheck_representative_buildings.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_recheck_summary.csv` | e5_c001 | report |
| `docs/e5_c001_corrected_s1_recheck_tradeoff.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_representative_buildings.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_corrected_s1_summary.csv` | e5_c001 | report |
| `docs/e5_c001_corrected_s1_tradeoff.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_405_rescore_building.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_405_rescore_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_s1_full_building_8way.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_coverage.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_filter_contrib.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_inventory.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_s1_full_normal_precheck_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_s1_full_normal_precheck_runtime.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_pipeline_strips_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_s1_full_readout_inventory.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_readout_issues.csv` | e5_c001 | issue_log |
| `docs/e5_c001_s1_full_representative_buildings.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s1_full_summary.csv` | e5_c001 | report |
| `docs/e5_c001_s1_full_tradeoff.csv` | e5_c001 | evidence_table |
| `docs/e5_c001_s2_405_repair_issues.csv` | e5_c001_s2 | issue_log |
| `docs/e5_c001_s2_405_repair_status_building.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_405_rescore.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_a5_metric_prep.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_coverage.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_filter_contrib.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_implementation_check.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_inventory.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_issues.csv` | e5_c001_s2 | issue_log |
| `docs/e5_c001_s2_mono_runtime.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_monodepth_resolution.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_pipeline_strips.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_pipeline_strips_issues.csv` | e5_c001_s2 | issue_log |
| `docs/e5_c001_s2_readout_inventory.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_readout_issues.csv` | e5_c001_s2 | issue_log |
| `docs/e5_c001_s2_representative_buildings.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2_summary.csv` | e5_c001_s2 | report |
| `docs/e5_c001_s2_tradeoff.csv` | e5_c001_s2 | evidence_table |
| `docs/e5_c001_s2p_405_repair_issues.csv` | e5_c001_s2p | issue_log |
| `docs/e5_c001_s2p_405_repair_status_building.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_405_rescore.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_8way_panel_inventory.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_coverage.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_filter_contrib.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_monodepth_precheck_v2_image.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_monodepth_precheck_v2_view.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_monodepth_runtime_v2.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_pipeline_strips.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_pipeline_strips_issues.csv` | e5_c001_s2p | issue_log |
| `docs/e5_c001_s2p_readout_inventory.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_readout_issues.csv` | e5_c001_s2p | issue_log |
| `docs/e5_c001_s2p_representative_buildings.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s2p_summary.csv` | e5_c001_s2p | report |
| `docs/e5_c001_s2p_tradeoff.csv` | e5_c001_s2p | evidence_table |
| `docs/e5_c001_s3_405_repair_issues.csv` | e5_c001_s3 | issue_log |
| `docs/e5_c001_s3_coverage.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_filter_contrib.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_inventory.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_readout_inventory.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_readout_issues.csv` | e5_c001_s3 | issue_log |
| `docs/e5_c001_s3_representative_buildings.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_semantic_gate_candidates.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_semantic_region_height_audit.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_semantic_region_inventory.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_semantic_region_mapping.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_semantic_region_projection_height_audit.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3_summary.csv` | e5_c001_s3 | report |
| `docs/e5_c001_s3_tradeoff.csv` | e5_c001_s3 | evidence_table |
| `docs/e5_c001_s3ap_anchor_inventory.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_fm_rescore.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_fm_retri_registration.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_fm_retri_rescore.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_fm_retriangulation.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_perturbation.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_c001_s3ap_perturbation_cells.csv` | e5_c001_s3ap | evidence_table |
| `docs/e5_pilot_block_candidates_summary.md` | e5_pilot_block | preregistration_or_lock |
| `docs/e5_pilot_completion_checklist.csv` | e5_pilot_completion_checklist | evidence_table |
| `docs/e5_pilot_seed_pair_summary.csv` | e5_pilot_seed_pair | report |
| `docs/e5_pilot_train_prep.md` | e5_pilot_train_prep | document |
| `docs/evidence_cards_v2_qA.md` | evidence_cards_qa | document |
| `docs/experiments/FC_METHOD_CURRENT.md` | fc_method_current | document |
| `docs/experiments/FC_S2_STAGE3_V1C_PROMPT.md` | fc_s2_stage3_v1c_prompt | document |
| `docs/experiments/FC_S5_LOSS_DESIGN_SPEC_v2.md` | fc_s5_loss_design_spec | document |
| `docs/experiments/FC_S6C_LMU5_8_DESIGN_FREEZE.md` | fc_s6c_lmu5_8_design_freeze | document |
| `docs/experiments/FC_S6D_LMUTUAL_DIRECTIONAL_SPEC.md` | fc_s6d_lmutual_directional_spec | document |
| `docs/experiments/er3_review_sources.md` | er3_review_sources | document |
| `docs/genclose_direct_plane.csv` | genclose_direct_plane | evidence_table |
| `docs/judgment_kit_v4_report.md` | judgment_kit | report |
| `docs/metric_contract_rv1.md` | metric_contract_rv1 | document |
| `docs/mononormal_diag.csv` | mononormal_diag | evidence_table |
| `docs/mvs_hole_check.csv` | mvs_hole_check | evidence_table |
| `docs/overnight_summary.md` | overnight | report |
| `docs/planefit_baseline.csv` | planefit_baseline | evidence_table |
| `docs/projection_datum_unitcheck.csv` | projection_datum_unitcheck | evidence_table |
| `docs/projection_gate_v2.md` | projection_gate | document |
| `docs/projection_zeta_ls.csv` | projection_zeta_ls | evidence_table |
| `docs/qs_cheap_refine_pilot.csv` | qs_cheap_refine_pilot | evidence_table |
| `docs/qs_rescore_fixed_conditions.csv` | qs_rescore_fixed_conditions | evidence_table |
| `docs/qs_rescore_hausdorff_spotcheck.csv` | qs_rescore_hausdorff_spotcheck | evidence_table |
| `docs/qs_rescore_pairs.csv` | qs_rescore | evidence_table |
| `docs/qs_rescore_summary.csv` | qs_rescore | report |
| `docs/qs_rescore_topview_panel.csv` | qs_rescore_topview_panel | evidence_table |
| `docs/repo_audit_rv1_20260728_2327.md` | repo_audit_rv1_2327 | document |
| `docs/research/REPO_STORAGE_AUDIT.md` | repo_storage_audit | document |
| `docs/s3b0_gate_scores.csv` | s3b0_gate_scores | evidence_table |
| `docs/s3b0_hsweep.csv` | s3b0_hsweep | evidence_table |
| `docs/s3b0_mask_iou.csv` | s3b0_mask_iou | evidence_table |
| `docs/s3b0_mono_reliability.csv` | s3b0_mono_reliability | evidence_table |
| `docs/s3b0_outline_observability.csv` | s3b0_outline_observability | evidence_table |
| `docs/s3b0_p0prime_scores.csv` | s3b0_p0prime_scores | evidence_table |
| `docs/s3b0_semantic_lineage.md` | s3b0_semantic_lineage | document |
| `docs/texture_anchor_check.md` | texture_anchor_check | document |
| `docs/사전등록_관문A_v2·SE3채택재판정_20260725.md` | 사전등록_관문a_se3채택재판정 | preregistration_or_lock |
| `docs/사전등록서_품질축본선_초안v1.2_20260718.md` | 사전등록서_품질축본선_초안 | preregistration_or_lock |
| `docs/원격프롬프트_S2_방향자리_사슬4arm·선행묶음_20260710.md` | 원격프롬프트_s2_방향자리_사슬4arm_선행묶음 | document |
| `docs/품질축본선_1파_구현부록잠금v1_20260722.md` | 품질축본선_1파_구현부록잠금 | preregistration_or_lock |
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
| `phases/p0-audit/docs/W2_3a_roofer_tuning.md` | w2_3a_roofer_tuning | document |
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
| `phases/p0-audit/docs/W3_qualitative_compare.md` | w3_qualitative_compare | document |
| `phases/p0-audit/docs/W3_summary.md` | w3 | report |
| `phases/p0-audit/docs/W3_survivor_texture_gap.md` | w3_survivor_texture_gap | document |
| `phases/p0-audit/docs/W3_survivor_texture_gap_building_metrics.csv` | w3_survivor_texture_gap_building | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_gap_correlations.csv` | w3_survivor_texture_gap_correlations | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_gap_strata.csv` | w3_survivor_texture_gap_strata | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine.md` | w3_survivor_texture_refine | document |
| `phases/p0-audit/docs/W3_survivor_texture_refine_building_metrics.csv` | w3_survivor_texture_refine_building | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_correlations.csv` | w3_survivor_texture_refine_correlations | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_strata.csv` | w3_survivor_texture_refine_strata | evidence_table |
| `phases/p0-audit/docs/W3_survivor_texture_refine_thresholds.csv` | w3_survivor_texture_refine_thresholds | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown.md` | w3_validity_error_breakdown | document |
| `phases/p0-audit/docs/W3_validity_error_breakdown_building_errors.csv` | w3_validity_error_breakdown_building_errors | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown_quality_attribution.csv` | w3_validity_error_breakdown_quality_attribution | evidence_table |
| `phases/p0-audit/docs/W3_validity_error_breakdown_type_by_input.csv` | w3_validity_error_breakdown_type_by_input | evidence_table |
| `phases/p0-audit/docs/W4b_population_profile.md` | w4b_population_profile | document |

Only the first 250 of 260 orphan candidates are shown.

## Required human decisions before migration

1. Approve the target structure and metadata contract.
2. For one family, approve canonical, supporting, superseded, retracted, and draft statuses.
3. Distinguish broken links from intentionally unavailable external/local artifacts.
4. Decide which run payloads are class C versus regenerable class D.
5. Review an exact path/reference migration preview before any move.
