# Repository catalog issues

> Generated report. It records review work; it does not authorize cleanup or make scientific verdicts.

## Snapshot

| Measure | Count |
|---|---|
| Cataloged indexed files | 1888 |
| Files directly under docs/ | 0 |
| Distinct inferred families | 96 |
| Local Markdown links/embeds that do not resolve | 0 |
| Reviewed external artifact references | 63 |
| Reviewed missing evidence references | 87 |
| Run directories | 85 |
| Run directories with one or more record gaps | 85 |

### Catalog document statuses

| Status | Files |
|---|---|
| canonical | 34 |
| canonical_candidate | 5 |
| orphan_candidate | 367 |
| superseded | 53 |
| superseded_candidate | 8 |
| supporting | 1421 |

### Run Git states

| Git state | Runs |
|---|---|
| indexed_record_present | 3 |
| tracked_record_present | 82 |

## Issue 1: docs-root sprawl

`docs/` currently has 0 indexed files directly at its root. The target architecture gives each experiment family one owner directory; no file is moved by this task.

| Inferred family | Root files |
|---|---|

## Issue 2: unclassified local Markdown links

No unclassified local Markdown links were found in the scanned text range.

## Reviewed external and missing references

External references are manifest-backed payload locations that a remote clone does not contain. Missing references were checked against both Git and the local artifact backend; no same-named file from another experiment may be substituted.

| Reviewed state | References | Lineage target |
|---|---|---|
| external_artifact | 63 | artifact://JointBuildGS/... |
| missing_evidence | 87 | missing://JointBuildGS/... |

## Issue 3: run receipt gaps

These are gaps against the target run contract, not claims that a historical run violated the rules in force when it was created.

| Phase | Run ID | Git state | Issues |
|---|---|---|---|
| P0 | e5p_405_repair_20260709_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P0 | e5p_baseline_acmp_20260706_001813 | tracked_record_present | missing_tracked_manifest |
| P0 | e5p_baseline_sparse_20260706_002300 | tracked_record_present | missing_tracked_manifest |
| P0 | e5p_gate_20260707_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P0 | e5p_readout_ablation_20260708_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260716_boundary_map | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_boundary_map_v2 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260719_boundary_map_v3 | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260720_anchor_census | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260720_anchor_census_supplement | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260721_degradation_curve | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260721_primary4_assembly_validation | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260721_primary4_assembly_validation_driver | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260707_e5_c001_8way | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260707_e5_c001_gsdiag | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260707_e5_pilot_attr_v1_3_append | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260707_e5_pilot_subst | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
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
| P2 | 20260716_e5_c001_s3b0_measurements | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | e5p_const_20260706_235710 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_prep_20260706_235306 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_sparse_config_20260706_000204 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | e5p_train_20260707_C001 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_aux_v4a | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_aux_v4b | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_cards_v4_kit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260704_attr_v1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_2 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_attr_v1_3 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_regression_v1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260706_regression_v1_1 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260708_d4_config_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260724_fusion_w1 | indexed_record_present | missing_tracked_versions |
| P2 | 20260726_fusion_w1_aprime | indexed_record_present | missing_tracked_versions |
| P2 | 20260727_fusion_w1_aprime_smoke_recovery | tracked_record_present | missing_tracked_manifest;missing_tracked_versions |
| P2 | 20260728_fusion_w1_dense_baseline_qualitative_v1 | indexed_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260702_A0_projection_fix | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260702_A1_zeta_ls | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260702_A2_projection_gate_v2 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_datum_tie_overlay | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_datum_tie_v3 | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | 20260703_recipe_audit | tracked_record_present | missing_tracked_manifest;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S5_loss_ledger_instrumentation | tracked_record_present | missing_tracked_versions |
| P2 | legacy-results-FC_S6C_lmutual_completion | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6D_directional_screening | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6E_joint | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | legacy-results-FC_S6_componentwise_revised_lmutual_design_validation | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260721_pilot_1wave | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260722_pilot_1wave_readout | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260724_pilot_1wave_report | tracked_record_present | missing_tracked_manifest;missing_tracked_versions |
| P2 | 20260716_genclose_flat_density | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260716_overnight_abc | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260716_qs_rescore | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260717_qs_cheap_refine_pilot | tracked_record_present | missing_tracked_report_or_index |
| P2 | 20260717_qs_rescore_fixed_conditions | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_baseline178_rescore | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_cheap_refine_sweep | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |
| P2 | 20260718_qs_rescore_completeness_panel | tracked_record_present | missing_tracked_versions;missing_tracked_report_or_index |
| P2 | footprint_conditioned_readout | tracked_record_present | missing_tracked_manifest;missing_tracked_versions;missing_tracked_report_or_index |

## Issue 4: orphan candidates

A file is an orphan candidate only when it has no parsed inbound path reference and is not an explicit canonical seed, guide, manifest, or figure. This is a triage signal, not proof that the file is unnecessary.

| Path | Family | Type |
|---|---|---|
| `docs/evidence/evidence_cards_v2/evidence_cards_v2_qA.md` | evidence_cards | document |
| `docs/evidence/judgment_kit_v4/judgment_kit_v4_report.md` | judgment_kit | report |
| `docs/evidence/p0-audit/design-and-provenance/reports/P0_입력치환Audit_실험설계서_v1_20260610.docx` | p0_audit | binary_document |
| `docs/evidence/p0-audit/w1-input-diagnostics/reports/dim_v1_classification_stats.md` | p0_audit | document |
| `docs/evidence/p0-audit/w1-input-diagnostics/reports/dim_v1_stats.md` | p0_audit | document |
| `docs/evidence/p0-audit/w1-input-diagnostics/reports/footprints_summary.md` | p0_audit | report |
| `docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md` | p0_audit | report |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_1_roofer_default.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_1b_paired_analysis.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_1c_quality_paired.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_2_city3d_default.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_2b_city3d_diagnosis.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/reports/W2_3b_dim_variants.md` | p0_audit | document |
| `docs/evidence/p0-audit/w2-reconstruction-audit/tables/W2_2_city3d_failure_reasons.csv` | p0_audit | evidence_table |
| `docs/evidence/p0-audit/w2-reconstruction-audit/tables/W2_2b_als_1200_sample.csv` | p0_audit | evidence_table |
| `docs/evidence/p0-audit/w2-reconstruction-audit/tables/W2_2b_als_val3dity_error_codes.csv` | p0_audit | evidence_table |
| `docs/evidence/p0-audit/w2-reconstruction-audit/tables/W2_2b_obj_representatives.csv` | p0_audit | evidence_table |
| `docs/evidence/p0-audit/w2-reconstruction-audit/tables/W2_2b_val3dity_recheck_summary.csv` | p0_audit | report |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_1_roofer_quality.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_2c_canonical_closeout.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_failure_diagnosis.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_failure_surface_cause.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_summary.md` | p0_audit | report |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_survivor_texture_gap.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/reports/W3_survivor_texture_refine.md` | p0_audit | document |
| `docs/evidence/p0-audit/w3-quality-integration/tables/W3_2c_canonical_internal_boundary_metrics.csv` | p0_audit | evidence_table |
| `docs/evidence/p0-audit/w3-quality-integration/tables/W3_figure_failure_story_metadata.json` | p0_audit | structured_record |
| `docs/evidence/p0-audit/w4-gate-population/reports/W4b_population_profile.md` | p0_audit | document |
| `docs/evidence/p0-audit/w4-gate-population/tables/W4c_no_points_breakdown_meta.json` | p0_audit | structured_record |
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
| `docs/experiments/citygml-readout/footprint_conditioned_readout/manifests/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase1_render_export/baseline_rendered_sample_bank_metadata.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/manifests/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase2_fixed_export/baseline_fixed_export_metadata.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/phase7_g2_feasibility/g2_groups.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/phase8_final_decision.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S1_semantic_surface_readout/val3dity_probe.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_acceptance_decision.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_inventory_decision.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/metrics/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/scene_evidence_graph_E1_Baseline_rendered.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S1_semantic_surface_readout/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/E1_RECOVERY_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/RENDERED_COMPARISON_PRE_V1C.md` | citygml_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_ground_closure/B104_GROUND_CLOSURE_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_height_definition/B6_HEIGHT_DEFINITION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_roof_decomposition/ROOF_DECOMPOSITION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_support_attribution/RENDERED_SUPPORT_ATTRIBUTION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/PATCH_ABLATION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseD_final_decision/G2_READINESS_DECISION.md` | citygml_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/E1_E2_FULL_COMPARISON_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/MUTUAL_LOSS_ALIGNMENT_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/EVIDENCE_DISTRIBUTION_AUDIT.md` | citygml_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/B104_field_replacement_report.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/B6_field_replacement_report.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/FIELD_REPLACEMENT_SUMMARY.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/roof_cases_field_replacement_report.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/FOOTPRINT_MASKING_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/MUTUAL_ABLATION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/FC_S3_FINAL_DECISION.md` | citygml_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/g2_4way_pilot_plan.md` | citygml_readout | document |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/reports/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/viewer/stage3_qa.html` | citygml_readout | other |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase0_inventory/target_buildings.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase1_evidence/evidence_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase3_surface_eval/surface_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase3_surface_eval/surface_metrics_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/geometry_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/summary_metrics.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase4_geometry_topology/topology_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase5_comparison/baseline_vs_mutual.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase5_comparison/evidence_to_model_transfer.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase6_baseline_comparison/conventional_baseline_metrics.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase6_baseline_comparison/ours_vs_baseline.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S1_semantic_surface_readout/phase7_g2_feasibility/g2_group_metrics.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_candidate_artifacts.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_evidence_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_sanity_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_stage3_matrix_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/e1_vs_e2_evidence_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/render_regeneration/phase1_render_export/baseline_rendered_sample_bank_views.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/rendered_baseline_vs_mutual_pre_v1c.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseB_diagnostics_by_case.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_deltas_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseC_stage3_v1c_ablation/patch_ablation_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_paired_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_split_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase1_full_e1_e2_comparison/e1_e2_win_loss_by_metric.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/gradient_norms_by_class.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/gradient_norms_by_loss.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/loss_to_metric_alignment_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase2_mutual_loss_audit/mutual_loss_components_by_class.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/e1_e2_classwise_evidence_stats.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/ground_y_distribution_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/roof_evidence_distribution_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase3_evidence_distribution/support_rejection_distribution_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase4_field_replacement/field_replacement_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/footprint_buffer_sweep_metrics.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase5_footprint_sensitivity/footprint_sensitivity_by_split.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_config_table.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_evidence_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase6_mutual_ablation/mutual_ablation_stage3_metrics.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/FC_S3_mutual_loss_alignment_g2_target_definition/phase7_g2_readiness/g2_target_selection.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase2_stage3_v1_readout/stage3_v1_patch_summary.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/algorithm_effect_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/evaluator_effect_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/final_effect_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/matrix_metrics_by_bid.csv` | citygml_readout | evidence_table |
| `docs/experiments/citygml-readout/footprint_conditioned_readout/tables/Stage3_v1_auditable_readout_FC_S1_v0_v1_comparison/phase3_matrix/matrix_summary_by_source.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_cluster_sweep/sweep_results.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_diag/d1/comparison.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_diag/d1/comparison_bid2.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_diag/d1/comparison_bid22.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_diag/d2/d2_results.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_diag/d4_stats.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_f1_geometry/phase2_f1_geometry.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_g2_stage3_test/comparison.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_gt_direct/summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_gt_stage3_test/summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_gt_stage3_test_2_5d_v2/summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_miou/phase2_miou.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_perturb_test/all_prims/perturb_bid21.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_perturb_test/perturb_bid21.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_ransac_stage3_test/results.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_sanity_g2/g2_sanity_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/_sanity_g2_mutual/g2_sanity_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/baseline/eval/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/baseline/eval_fixed/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/baseline/stage3/stage3_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/both/eval/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/both/eval_fixed/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/both/stage3/stage3_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/mutual/eval/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/mutual/eval_fixed/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/mutual/stage3/stage3_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/stage2_primitive_metrics.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/structure/eval/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/structure/eval_fixed/eval_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/metrics/structure/stage3/stage3_summary.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/phase2_ablation_citygml/reports/notes/_sanity_g2_mutual/figs_table/bldg_021_summary.txt` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_polyfit_phase2/reports/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_rendered_evidence/manifests/S1_rendered_e2style_gate/experiment_policy.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/stage3_rendered_evidence/metrics/S1_debug_rendered_interface/decision.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/stage3_rendered_evidence/metrics/S1_rendered_e2style_gate/decision.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/stage3_rendered_evidence/reports/S1_debug_rendered_interface/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_rendered_evidence/reports/S1_rendered_e2style_gate/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/metrics/E1_gt_131_per_building/summary_metrics.json` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/metrics/P1_4a_gt_sanity/preflight_precision_metrics.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/E1_gt_131_per_building/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/VAL3DITY_AND_PRECISION_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/reports/P1_4a_gt_sanity/VAL3DITY_RERUN_REPORT.md` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/tables/E1_gt_131_per_building/summary_metrics.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/stage3_typed_readout/tables/P1_4a_gt_sanity/summary_metrics.csv` | citygml_readout | report |
| `docs/experiments/citygml-readout/synthetic_a/manifests/3dbag_sampled_buildings.json` | citygml_readout | structured_record |
| `docs/experiments/citygml-readout/synthetic_a/reports/REPORT.md` | citygml_readout | report |
| `docs/experiments/evaluation/attr_outcome_regression/tables/regression_input_snapshot.csv` | evaluation | evidence_table |
| `docs/experiments/evaluation/er3_recoverability/reports/review_sources.md` | evaluation | document |
| `docs/experiments/evaluation/phase1_analysis/metrics/g1_vs_g2_summary.json` | evaluation | report |
| `docs/experiments/evaluation/primary4_assembly_validation/tables/genclose_density_assembly.csv` | evaluation | evidence_table |
| `docs/experiments/evaluation/primary4_assembly_validation/tables/genclose_direct_plane.csv` | evaluation | evidence_table |
| `docs/experiments/evaluation/primary4_assembly_validation/tables/genclose_flat_seed_scores.csv` | evaluation | evidence_table |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_2_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_3/p1_3_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_3_phase0/p1_3_phase0_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_3_phase0c/p1_3_phase0c_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_3a/p1_3a_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/metrics/p1_3b/p1_3b_metrics.json` | evaluation | structured_record |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_2_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_3_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_3_phase0_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_3_phase0c_b0_backend_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_3a_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/P1_3b_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/reports/polyfit_input_audit/AUDIT_REPORT.md` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/tables/polyfit_input_audit/audit_summary.csv` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/tables/polyfit_input_audit/gt_face_sampling_coverage_summary.csv` | evaluation | report |
| `docs/experiments/evaluation/stage3_v4_validation/tables/polyfit_input_audit/input_validation.csv` | evaluation | evidence_table |
| `docs/experiments/evaluation/stage3_v4_validation/tables/polyfit_input_audit/input_validation_summary.csv` | evaluation | report |
| `docs/experiments/evaluation/tum2twin_surface_proxy_rv1/reports/metric_contract_rv1.md` | evaluation | document |
| `docs/experiments/evaluation/tum2twin_surface_proxy_rv1/reports/repo_audit_rv1_20260728_2327.md` | evaluation | document |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/mononormal_diag.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/mvs_hole_check.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3ap/tables/planefit_baseline.csv` | e5_c001_s3ap | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/reports/s3b0_semantic_lineage.md` | e5_c001_s3b | document |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_gate_scores.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_hsweep.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_mask_iou.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_mono_reliability.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_outline_observability.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/e5_c001_s3b0/tables/s3b0_p0prime_scores.csv` | e5_c001_s3b | evidence_table |
| `docs/experiments/input-and-alignment/phase2_synthesis/manifests/gravity.json` | input_and_alignment | structured_record |
| `docs/experiments/input-and-alignment/phase2_synthesis/manifests/scene_layout.json` | input_and_alignment | structured_record |
| `docs/experiments/input-and-alignment/phase2_synthesis/manifests/selected_block.json` | input_and_alignment | preregistration_or_lock |
| `docs/experiments/input-and-alignment/phase2_synthesis/models/scene.mtl` | input_and_alignment | other |
| `docs/experiments/input-and-alignment/phase2_synthesis/models/scene.obj` | input_and_alignment | other |
| `docs/experiments/input-and-alignment/phase2_synthesis/reports/REPORT.md` | input_and_alignment | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/FC_S5_EXPERIMENT_REPORT.md` | joint_optimization | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase1_instrumentation/INSTRUMENTATION_REPORT.md` | joint_optimization | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase1_instrumentation/default_off_equivalence.md` | joint_optimization | document |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/reports/phase2_diagnostics/LOSS_DIAGNOSTIC_REPORT.md` | joint_optimization | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase1_instrumentation/log_tag_check.csv` | joint_optimization | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/B104_terrain_drift_summary.csv` | joint_optimization | report |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/M10_metrics_by_bid.csv` | joint_optimization | evidence_table |
| `docs/experiments/joint-optimization/FC_S5_loss_ledger_instrumentation/tables/phase2_diagnostics/M3_metrics_by_bid.csv` | joint_optimization | evidence_table |

Only the first 250 of 367 orphan candidates are shown.

## Required human decisions before migration

1. Approve the target structure and metadata contract.
2. For one family, approve canonical, supporting, superseded, retracted, and draft statuses.
3. Distinguish broken links from intentionally unavailable external/local artifacts.
4. Decide which run payloads are class C versus regenerable class D.
5. Review an exact path/reference migration preview before any move.
