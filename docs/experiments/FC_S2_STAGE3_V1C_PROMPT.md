Experiment name:
FC-S2: Baseline Rendered Recovery and Targeted Stage3-v1c Failure-mode Resolution

Short name:
FC-S2

Primary purpose:
This experiment removes the two remaining blockers before G2 training.

1. Recover or regenerate E1_Baseline_rendered so that a fair rendered Baseline-vs-Mutual comparison becomes possible.
2. Diagnose and minimally improve the remaining Stage3 failure modes identified after FC-S1 and Stage3-v1:
   - B104 ground closure
   - B6 height definition
   - B3/B123/B126 roof decomposition or reference matching
   - E2_Mutual_rendered support attribution

This is not a new full reconstruction pipeline. It is a controlled continuation of FC-S1 and Stage3-v1.

Core principle:
Track A completes the missing rendered baseline evidence.
Track B diagnoses remaining failure modes and applies targeted Stage3-v1c patches only when the issue is confirmed to be a Stage3 read-out problem.

Do not treat Track B as evaluation-only.
Do not treat Track B as a full Stage3 rewrite.
It is diagnosis + classified intervention + patch ablation.

Research alignment:
The experiment remains footprint-conditioned semantic surface read-out.
It is not full-scene no-prior building discovery.
It is not footprint estimation.
It is not G2 training.

The target output remains a semantic 3D building model with:
- RoofSurface
- WallSurface
- GroundSurface
- face adjacency
- edge incidence
- shell diagnostics

Primary internal outputs must remain:
- semantic_faces.json
- face_graph.json
- shell_diagnostics.json

CityJSON / CityGML export is optional serialization and QA support only.
Do not use CityJSON written status as proof of semantic/topological validity.

Controlled inputs:
Preserve the FC-S1 / Stage3-v1 controlled setting unless explicitly stated.

Keep fixed:
- FC-S1 building set:
  B0, B1, B2, B8, B6, B3, B123, B126, B50, B104
- source definitions:
  E0_GT_clean_upper_bound
  E1_Baseline_rendered
  E2_Mutual_rendered
  E3_Baseline_primitive
  E4_Mutual_primitive
- footprint/domain condition
- footprint buffer: 0.75 m
- gravity convention: [0, 1, 0]
- coordinate frame
- Stage3 primary output schema
- Metric-v1 audit framework
- Stage3-v1 output/debug structure where possible

Do not change:
- footprint estimation
- footprint buffer size
- building set
- source semantics
- gravity convention
- Stage2 evidence generation logic, except for E1_Baseline_rendered regeneration from the Baseline checkpoint
- GT roof type / GT roof partition / GT final mesh usage for Stage2-derived output
- thesis direction toward footprint-conditioned semantic surface read-out

Background:
Stage3-v1 compared Stage3Algo-v0 and Stage3Algo-v1 under Metric-v0 and Metric-v1.
The matrix separated evaluator effects from read-out algorithm effects.

Evaluator effect:
  Stage3Algo-v0 + Metric-v1
  minus
  Stage3Algo-v0 + Metric-v0

Algorithm effect:
  Stage3Algo-v1 + Metric-v1
  minus
  Stage3Algo-v0 + Metric-v1

Stage3-v1 showed:
- E1_Baseline_rendered remains SOURCE_MISSING.
- E2_Mutual_rendered remains 10/10 OK, but Stage3Algo-v1 did not improve its metrics.
- Stage3Algo-v1 recovered two zero-ground-evidence primitive failures into explicit shell attempts.
- Stage3-v1 improvement rows were zero for existing OK rows.
- Metric-v1 provided auditability without overturning FC-S1 conclusions.

Therefore, FC-S2 must not claim that Stage3-v1 improved the main rendered path yet.
FC-S2 must first recover E1 and then apply targeted v1c patches only where justified.
Track A:
E1_Baseline_rendered Recovery

Purpose:
Recover or regenerate missing E1_Baseline_rendered so that rendered Baseline-vs-Mutual comparison is no longer blocked.

Why this matters:
Without E1_Baseline_rendered, we cannot claim that E2_Mutual_rendered improves over Baseline rendered evidence at final semantic model level.
We can only compare E2 to E0 upper-bound, not to Baseline.

A0. Search for existing E1 artifact

Search all likely result roots for Baseline rendered evidence.

Commands:

find results -type f \( \
  -iname '*rendered_evidence*.npz' -o \
  -iname '*rendered*evidence*.npz' -o \
  -iname '*baseline*rendered*.npz' -o \
  -iname '*baseline*evidence*.npz' \
\) -print | sort

find results -type f -iname '*.npz' | grep -i rendered
find results -type f -iname '*.npz' | grep -i baseline
find results -type f -iname '*.npz' | grep -i mutual

Classification:
- FOUND_COMPATIBLE:
  Existing E1 artifact is found and matches E2 export conditions.
- FOUND_INCOMPATIBLE:
  Existing artifact exists but differs in renderer, coordinate frame, filtering, voxel size, camera set, or class semantics.
- NOT_FOUND:
  No usable E1 artifact exists.
- FOUND_BUT_UNREGISTERED:
  Artifact exists but FC-S1/Stage3-v1 inventory did not link it.

Deliverables:
phaseA_e1_recovery/
  e1_search_log.txt
  e1_candidate_artifacts.csv
  e1_inventory_decision.json

A1. Regenerate E1 if missing or incompatible

If E1 is NOT_FOUND or FOUND_INCOMPATIBLE, regenerate E1 from the Baseline checkpoint.

E1 must match E2_Mutual_rendered conditions.

Required matching conditions:
- same scene
- same camera set
- same render resolution
- same depth export convention
- same normal export convention
- same semantic export convention
- same mask rule
- same class-normal-aware filtering
- same voxel size as E2, especially voxel_0p05 if E2 used it
- same coordinate frame
- same gravity convention [0, 1, 0]
- same footprint-conditioned extraction
- same Stage3 read-out config

Important:
E1 regeneration is not a Stage3 algorithm change.
It is an evidence artifact completion step.

Do not:
- tune Baseline rendering differently from Mutual rendering
- use GT roof type
- use GT final mesh
- change footprint/domain
- change Stage2 training or evidence logic except for running the same rendered export on the Baseline checkpoint

Deliverables:
phaseA_e1_recovery/
  E1_Baseline_rendered.npz
  baseline_rendered_regeneration_status.json
  e1_render_config.json
  e1_render_log.txt

A2. E1 sanity gate

Before Stage3 read-out, validate the E1 rendered evidence.

Checks by bid:
- file_exists
- n_points
- n_roof
- n_wall
- n_ground
- semantic label distribution
- entropy / confidence distribution if available
- normal consistency
- coordinate range
- footprint crop hit rate
- empty-domain count
- invalid coordinate count
- comparison with E2 evidence statistics

Pass requirements:
- E1 must have non-zero evidence for most target buildings.
- E1 coordinate range must match E2 / scene / footprints.
- E1 semantic labels must include roof/wall and preferably ground.
- If ground is absent in some buildings, record it explicitly rather than silently failing.
- If sanity check fails, do not run final comparison until the failure reason is documented.

Deliverables:
phaseA_e1_recovery/
  e1_sanity_by_bid.csv
  e1_evidence_summary.csv
  e1_vs_e2_evidence_summary.csv
  e1_acceptance_decision.json

A3. Add E1 to Stage3 matrix

Once E1 passes sanity gate, run the same Stage3 matrix as Stage3-v1:

Required combinations:
- Stage3Algo-v0 + Metric-v0
- Stage3Algo-v0 + Metric-v1
- Stage3Algo-v1 + Metric-v1
- Stage3Algo-v1 + Metric-v0 optional

For E1 final comparison, at minimum report:
- E1_Baseline_rendered + Stage3Algo-v1 + Metric-v1
- E2_Mutual_rendered + Stage3Algo-v1 + Metric-v1

If Stage3-v1c patches are selected later, also report:
- E1_Baseline_rendered + Stage3Algo-v1c-selected + Metric-v1
- E2_Mutual_rendered + Stage3Algo-v1c-selected + Metric-v1

Deliverables:
phaseA_e1_recovery/
  e1_stage3_matrix_metrics_by_bid.csv
  e1_readout_status.csv
  rendered_baseline_vs_mutual_pre_v1c.csv
Track B:
Targeted Stage3-v1c Failure-mode Resolution

Purpose:
Classify each remaining failure mode as:
- Stage3 algorithm issue
- evaluator/reference matching issue
- Stage2 evidence/support issue
- unresolved

Then apply minimal Stage3-v1c patches only to confirmed Stage3 algorithm issues.

This track includes both diagnosis and improvement.
It is not evaluation-only.
It is not a full Stage3 rewrite.

Definition of minimal patch:
A minimal patch is a targeted, flag-controlled change that addresses a confirmed failure mode without rewriting the entire Stage3 pipeline.

A minimal patch must:
- have a clearly identified failure mode
- affect a limited module or decision point
- be enabled/disabled by config flag
- be evaluated by patch ablation
- preserve Stage2 evidence files
- preserve footprint/domain conditions
- preserve source definitions
- avoid using GT final geometry to construct Stage2-derived outputs
- avoid broad regressions on good/simple cases

Examples of minimal patches:
- ground face orientation sanity fix
- ground elevation correction when clearly inconsistent
- wall-ground lower edge closure correction
- roof near-coplanar merge only when ridge/valley structure is preserved
- tiny unsupported roof patch prune
- support-informed face confidence
- evaluator one-to-many roof matching correction if issue is evaluator-side

Definition of full patch:
A full patch rewrites or globally replaces Stage3 behavior, for example:
- new global roof reconstruction pipeline
- full mesh repair as default
- global shell optimization
- external mesh repair replacing Stage3 output
- changing Stage2 evidence filtering
- changing footprint/domain conditions
- joint roof/wall/ground re-optimization across all cases

Full patch is out of scope for FC-S2 unless all targeted patches fail and a separate experiment is proposed.

B0. Baseline for Track B

Use Stage3-v1 + Metric-v1 as the baseline for v1c patch ablations.

Do not compare patches only to FC-S1 Stage3-v0.
The correct patch baseline is:
  Stage3Algo-v1 + Metric-v1

For algorithm effect:
  Stage3Algo-v1c-branch + Metric-v1
  minus
  Stage3Algo-v1 + Metric-v1

For evaluator effect:
  Stage3Algo-v1 + new Metric variant
  minus
  Stage3Algo-v1 + Metric-v1

B1. Viewer QA setup

Use the existing repository viewer.
Do not create a separate standalone viewer unless needed for temporary debugging.

Add or reuse a Stage3 QA page with:
- source selector
- bid selector
- Stage3 algorithm version selector
- metric version selector
- predicted semantic faces layer
- reference samples layer
- evidence points layer
- support accepted layer
- support rejected layer
- unmatched coverage samples layer
- face graph edge layer
- open edge layer
- non-manifold edge layer
- semantic color mode
- support heatmap mode
- coverage error heatmap mode
- topology error mode
- face inspector
- metric panel

Required cases for visual QA:
- B2 / E2 as success reference
- B104 / E2 for ground_cov=0 with rendered evidence
- B104 / E4 for recovered primitive shell attempt
- B50 / E3 for recovered primitive shell attempt
- B6 / E0 and E2 for high h_err
- B3 / E0 and E2 for low roof_cov
- B123 / E0 and E2 for low roof_cov
- B126 / E0 and E2 for low roof_cov
- E1 / same bids if E1 is recovered

Deliverables:
phaseB_viewer_qa/
  stage3_qa_fc_s2.html
  saved_views/
  viewer_case_notes.md
B2. B104 ground closure subtrack

Purpose:
Determine whether B104 ground failure is caused by Stage3 ground closure, evaluator/reference matching, or evidence support.

Target cases:
- B104 / E0_GT_clean_upper_bound
- B104 / E2_Mutual_rendered
- B104 / E4_Mutual_primitive
- B104 / E1_Baseline_rendered if available

Questions:
- Does a ground face exist?
- Is its semantic label GroundSurface?
- Is its normal aligned with gravity?
- Is its elevation plausible?
- Does it overlap the footprint?
- Does it connect to wall lower edges?
- Are ground reference samples unmatched?
- If ground_cov is zero, which rejection reason dominates?
- Is this a geometry issue or a matching issue?

Diagnostics:
- ground_face_exists
- ground_face_id
- ground_elevation
- reference_ground_elevation
- elevation_delta
- ground_normal
- gravity_alignment
- footprint_overlap_ratio
- wall_ground_adjacency_count
- lower_open_edge_count
- ground_coverage_matched_samples
- ground_coverage_unmatched_samples
- ground_rejection_reason_histogram

Possible classifications:
- STAGE3_GROUND_ORIENTATION_FAILURE
- STAGE3_GROUND_ELEVATION_FAILURE
- STAGE3_WALL_GROUND_CLOSURE_FAILURE
- EVALUATOR_GROUND_MATCHING_FAILURE
- EVIDENCE_GROUND_SUPPORT_FAILURE
- UNRESOLVED

Allowed minimal patches:
- v1c-ground-orientation-fix
- v1c-ground-elevation-fix
- v1c-wall-ground-closure-fix
- v1c-ground-semantic-sanity-fix
- v1c-ground-evaluator-matching-fix

Patch acceptance:
Accept only if:
- target B104 issue improves or is clearly explained
- F / vol_ratio / topology do not degrade significantly
- good cases B1/B2/E0 do not regress
- patch effect is visible in diagnostic logs and viewer

Deliverables:
phaseB_ground_closure/
  B104_ground_diagnostics.md
  ground_rejection_reasons.csv
  v1c_ground_patch_ablation.csv
  saved_views/
B3. B6 height definition subtrack

Purpose:
Explain B6 high h_err despite good F/chamfer, especially because E0 also shows high h_err.

This subtrack is primarily evaluator/definition audit.
Only apply algorithm patch if actual ground or roof placement error is confirmed.

Target cases:
- B6 / E0_GT_clean_upper_bound
- B6 / E2_Mutual_rendered
- B6 / E1_Baseline_rendered if available

Questions:
- What exactly does h_err measure?
- Is it max height error?
- Is it mean roof height error?
- Is it eave height error?
- Is it ridge height error?
- Is it ground elevation error?
- Does E0 show the same issue?
- Is h_err inconsistent with F/chamfer because it measures a different failure mode?

Required height breakdown:
- pred_min_height
- pred_max_height
- pred_mean_roof_height
- pred_eave_height_if_available
- pred_ridge_height_if_available
- ref_min_height
- ref_max_height
- ref_mean_roof_height
- ref_eave_height_if_available
- ref_ridge_height_if_available
- height_error_ground
- height_error_max
- height_error_mean_roof
- height_error_eave
- height_error_ridge
- volume_ratio
- volume_error_reason

Possible classifications:
- HEIGHT_METRIC_DEFINITION_ISSUE
- HEIGHT_REFERENCE_MISMATCH
- STAGE3_GROUND_HEIGHT_FAILURE
- STAGE3_ROOF_HEIGHT_FAILURE
- TRUE_GEOMETRY_HEIGHT_FAILURE
- UNRESOLVED

Allowed actions:
- add auxiliary height metrics
- clarify h_err definition
- adjust evaluator if definition is wrong or misleading
- apply ground/roof placement patch only if actual geometry failure is confirmed

Do not:
- patch geometry simply because h_err is high
- collapse h_err into F-score
- claim B6 is a Stage2 evidence failure if E0 shows the same issue

Deliverables:
phaseB_height_definition/
  B6_height_audit.md
  height_breakdown_by_bid.csv
  height_metric_definition_v2.md
  v1c_height_action_decision.json
B4. B3/B123/B126 roof decomposition and reference matching subtrack

Purpose:
Determine whether low roof_cov is caused by Stage3 roof decomposition, evaluator/reference matching, true complex roof limitation, or evidence support.

Target cases:
- B3 / E0_GT_clean_upper_bound
- B3 / E2_Mutual_rendered
- B123 / E0_GT_clean_upper_bound
- B123 / E2_Mutual_rendered
- B126 / E0_GT_clean_upper_bound
- B126 / E2_Mutual_rendered
- E1 versions if available

Questions:
- Is the building actually a complex roof case?
- Are roof faces over-fragmented?
- Are near-coplanar roof faces unnecessarily split?
- Are small patches real roof detail or noise?
- Are unmatched reference roof samples concentrated in specific roof regions?
- Does one-to-many or many-to-one matching explain low roof_cov?
- Would merging improve coverage but destroy ridge/hip/valley structure?
- Does E0 low roof_cov imply evaluator/reference mismatch or Stage3 upper-bound failure?

Required diagnostics:
- roof_group_id
- roof_plane_parameters
- roof_face_count
- roof_face_area
- roof_face_support_score
- roof_face_matched_reference_ratio
- near_coplanar_merge_candidates
- small_patch_candidates
- merge_rejection_reason
- ridge_valley_preservation_indicator_if_available
- unmatched_roof_reference_samples
- roof_reference_to_predicted_match_table

Possible classifications:
- STAGE3_ROOF_OVER_FRAGMENTATION
- STAGE3_ROOF_UNDER_MERGING
- STAGE3_ROOF_SMALL_PATCH_NOISE
- EVALUATOR_ROOF_ONE_TO_MANY_MATCHING_ISSUE
- EVALUATOR_REFERENCE_MISMATCH
- TRUE_COMPLEX_ROOF_LIMITATION
- EVIDENCE_ROOF_SUPPORT_FAILURE
- UNRESOLVED

Allowed minimal patches:
- v1c-roof-near-coplanar-merge
- v1c-roof-small-unsupported-prune
- v1c-roof-small-patch-merge-to-neighbor
- v1c-roof-ridge-valley-preservation-rule
- v1c-roof-evaluator-one-to-many-matching

Patch acceptance:
Accept only if:
- target roof cases improve or are explained
- E0 upper-bound bottleneck is reduced or classified
- E2 does not regress on good cases
- B1/B2/B104 do not lose valid roof structure
- topology does not degrade
- ridge/valley structure is not blindly destroyed

Deliverables:
phaseB_roof_decomposition/
  B3_B123_B126_roof_diagnostics.md
  roof_match_table.csv
  roof_merge_candidates.csv
  roof_unmatched_samples.csv
  v1c_roof_patch_ablation.csv
  saved_views/
B5. E2 support attribution subtrack

Purpose:
Explain low E2_Mutual_rendered support_cov and decide whether it is a Stage3 support attribution issue, evidence distribution issue, or G2 target.

Target:
- E2_Mutual_rendered all bids
- focus on B2, B6, B50, B104, B3, B123, B126
- compare E1 if available

Questions:
- Which semantic class has low support: roof, wall, or ground?
- Which faces have lowest support?
- Are unsupported faces still geometrically correct?
- Are support rejections caused by distance, normal, semantic, confidence, or outside-polygon checks?
- Does low support correlate with low F/coverage?
- Are there cases where support is low but geometry is good?
- Are there cases where support is high but coverage is low?

Required metrics:
- support_cov
- roof_support_cov
- wall_support_cov
- ground_support_cov
- face_support_cov_mean
- face_support_cov_min
- unsupported_face_area_ratio
- support_rejection_reason_histogram
- per_face_support.csv

Required rejection reasons:
- NO_NEARBY_EVIDENCE
- DISTANCE_TOO_LARGE
- NORMAL_MISMATCH
- SEMANTIC_MISMATCH
- OUTSIDE_FACE_POLYGON
- LOW_CONFIDENCE_EVIDENCE
- UNKNOWN

Possible classifications:
- STAGE3_SUPPORT_ASSIGNMENT_THRESHOLD_ISSUE
- STAGE3_FACE_CONFIDENCE_ISSUE
- STAGE3_SUPPORT_INFORMED_MERGE_PRUNE_NEEDED
- STAGE2_EVIDENCE_DISTRIBUTION_ISSUE
- G2_SURFACE_GROUPING_TARGET
- EVALUATOR_SUPPORT_DEFINITION_ISSUE
- UNRESOLVED

Allowed minimal patches:
- v1c-support-threshold-audit
- v1c-support-face-confidence
- v1c-support-informed-roof-prune
- v1c-support-informed-roof-merge
- v1c-support-classwise-reporting

Important:
Support attribution is not automatically a geometry patch.
If support is low because Stage2 evidence is weak, classify it as a G2 target.
If support is low because Stage3 assignment thresholds are wrong, patch Stage3.
If geometry is good but support is low, report confidence limitation rather than forcing geometry changes.

Deliverables:
phaseB_support_attribution/
  E2_support_attribution_report.md
  per_face_support.csv
  support_rejection_histogram.csv
  support_classwise_summary.csv
  v1c_support_patch_ablation.csv
Patch ablation design

Run every Stage3-v1c patch branch separately before combining.

Branches:
- v1c-ground
- v1c-height-definition
- v1c-roof-merge-prune
- v1c-roof-evaluator-matching
- v1c-support-attribution
- v1c-combined-selected

Baseline:
- Stage3Algo-v1 + Metric-v1

For each branch compare:
- Stage3Algo-v1 + Metric-v1
- Stage3Algo-v1c-branch + Metric-v1

If E1 is recovered, include:
- E1_Baseline_rendered
- E2_Mutual_rendered

Patch report columns:
- patch_name
- enabled
- affected_workflow_step
- target_failure_mode
- affected_bids
- affected_sources
- expected_effect
- observed_effect
- metric_delta
- topology_delta
- support_delta
- visual_QA_result
- regressions
- keep_or_revert
- reason

Patch rejection criteria:
Reject patch if:
- it improves a target case but degrades good/simple cases
- it increases open edges or non-manifold edges
- it hides GroundSurface failure rather than fixing it
- it improves roof_cov by destroying meaningful roof topology
- it changes Stage2 evidence
- it changes footprint/domain assumptions
- it cannot be explained through logs/viewer
Required final reports

1. E1 recovery report
File:
  phaseA_e1_recovery/E1_RECOVERY_REPORT.md

Must include:
- whether E1 was found or regenerated
- final E1 path
- config comparison with E2
- evidence sanity by bid
- failure reason if E1 cannot be generated
- accept/reject decision for Stage3 matrix

2. Rendered Baseline-vs-Mutual comparison
File:
  phaseA_e1_recovery/rendered_baseline_vs_mutual.csv
  phaseA_e1_recovery/RENDERED_COMPARISON.md

Must include:
- E1 vs E2 evidence summary
- E1 vs E2 read-out status
- E1 vs E2 surface metrics
- E1 vs E2 support metrics
- E1 vs E2 geometry metrics
- E1 vs E2 topology diagnostics
- bid-level comparison
- whether Mutual final-model gain is supported, mixed, or not supported

3. B104 ground closure report
File:
  phaseB_ground_closure/B104_GROUND_CLOSURE_REPORT.md

Must classify:
- Stage3 ground failure
- evaluator matching issue
- evidence support issue
- unresolved

4. B6 height definition report
File:
  phaseB_height_definition/B6_HEIGHT_DEFINITION_REPORT.md

Must classify:
- metric definition issue
- reference mismatch
- actual geometry height failure
- unresolved

5. B3/B123/B126 roof decomposition report
File:
  phaseB_roof_decomposition/ROOF_DECOMPOSITION_REPORT.md

Must classify each bid:
- Stage3 roof decomposition issue
- evaluator/reference matching issue
- true complex roof limitation
- evidence support issue
- unresolved

6. E2 support attribution report
File:
  phaseB_support_attribution/E2_SUPPORT_ATTRIBUTION_REPORT.md

Must decide:
- Stage3 support patch
- G2 target
- evaluator definition issue
- unresolved

7. Stage3-v1c patch ablation report
File:
  phaseC_stage3_v1c_ablation/PATCH_ABLATION_REPORT.md

Must include:
- separate branch results
- combined selected result
- kept patches
- reverted patches
- reason for each decision

8. G2 readiness decision
File:
  phaseD_final_decision/G2_READINESS_DECISION.md

Decision options:
- GO_TO_G2
- CONDITIONAL_GO_TO_G2
- NO_GO_STAGE3_OR_E1_BLOCKED
Required final tables

Table 1. E1 recovery summary

Columns:
- e1_status
- artifact_path
- regenerated
- compatible_with_E2
- mean_n_points
- mean_n_roof
- mean_n_wall
- mean_n_ground
- normal_consistency
- semantic_entropy
- coordinate_sanity
- accepted_for_stage3
- interpretation

Table 2. Rendered Baseline-vs-Mutual final comparison

Rows:
- E1_Baseline_rendered + selected Stage3 + Metric-v1
- E2_Mutual_rendered + selected Stage3 + Metric-v1

Columns:
- source
- OK_count
- mean_F
- mean_roof_cov
- mean_wall_cov
- mean_ground_cov
- mean_support_cov
- mean_roof_support_cov
- mean_wall_support_cov
- mean_ground_support_cov
- mean_h_err
- mean_vol_ratio
- mean_chamfer
- mean_open_edges
- interpretation

Table 3. Failure-mode classification

Rows:
- B104 ground closure
- B6 height definition
- B3 roof decomposition/reference matching
- B123 roof decomposition/reference matching
- B126 roof decomposition/reference matching
- E2 support attribution

Columns:
- case
- symptom
- classified_as
- evidence
- patch_applied
- metric_effect
- visual_QA_result
- final_interpretation

Table 4. Patch ablation

Columns:
- patch
- target
- enabled
- affected_bids
- metric_gain
- support_gain
- topology_change
- regression_cases
- keep_or_revert
- reason

Table 5. G2 readiness

Columns:
- condition
- result
- decision_note

Conditions:
- E1 rendered comparison completed
- Mutual vs Baseline rendered conclusion available
- B104 ground issue classified
- B6 h_err issue classified
- B3/B123/B126 roof issue classified
- E2 support attribution classified
- Stage3-v1c selected patches stable
- good cases not regressed
- G2 target clear
GO / CONDITIONAL GO / NO-GO criteria

GO_TO_G2:
All or most of the following are true:
- E1_Baseline_rendered is recovered or regenerated and passes sanity checks.
- E1 vs E2 rendered comparison is completed.
- E2_Mutual_rendered shows a meaningful final-model or support/grouping advantage over E1, or the G2 target is clearly identified.
- B104 ground issue is classified and preferably fixed.
- B6 h_err is explained as metric/reference issue or true geometry issue.
- B3/B123/B126 low roof_cov is classified.
- E2 support attribution is decomposed by class, face, and rejection reason.
- Stage3-v1c selected patches do not regress good cases.
- G2 target is clearly one of:
  roof grouping
  wall support
  ground support
  support attribution
  surface grouping
  semantic-geometric evidence stabilization

CONDITIONAL_GO_TO_G2:
Use when:
- E1 is recovered but E1-vs-E2 result is mixed.
- Stage3-v1c explains most failure modes but not all.
- Complex roof remains partially unresolved.
- Support attribution clearly indicates a G2 target.
- Stage3-v1c does not regress good cases.

NO_GO_STAGE3_OR_E1_BLOCKED:
Use when:
- E1 cannot be found or regenerated.
- E1 coordinate/export condition is incompatible with E2.
- E1 vs E2 comparison remains blocked.
- E0 upper-bound low metrics remain unexplained.
- B104 ground issue remains unexplained.
- B6 height issue remains unexplained.
- roof decomposition/reference matching remains ambiguous.
- Stage3-v1c patches regress good cases.
- support attribution remains uninterpretable.
Final interpretation rules

Do not overclaim.

Allowed claims if supported:
- E1 recovery completes rendered Baseline-vs-Mutual comparison.
- Stage3-v1c resolves a specific failure mode.
- Metric-v1 separates evaluator effects from algorithm effects.
- E2 Mutual rendered is better/worse/mixed relative to E1 Baseline rendered under the same Stage3 and Metric-v1.
- Specific remaining issues should be passed to G2 as surface grouping/support targets.

Forbidden claims unless directly supported:
- Mutual rendered improves over Baseline rendered if E1 remains missing.
- Stage3-v1c is a new full reconstruction pipeline.
- CityJSON export written means semantic/topological validity.
- roof_cov improvement alone proves better roof topology.
- ground failure is solved by excluding GroundSurface.
- G2 should start before E1 and major Stage3 failure modes are classified.

One-sentence desired final conclusion:
FC-S2 should determine whether the Mutual rendered path truly improves final semantic building model read-out over Baseline rendered evidence, and whether remaining Stage3 failures are evaluator issues, Stage3 algorithm issues, or G2 evidence/support targets.
Expected output directory

results/footprint_conditioned_readout/FC_S2_baseline_rendered_recovery_stage3_v1c/

  phaseA_e1_recovery/
    e1_search_log.txt
    e1_candidate_artifacts.csv
    e1_inventory_decision.json
    E1_Baseline_rendered.npz
    baseline_rendered_regeneration_status.json
    e1_render_config.json
    e1_sanity_by_bid.csv
    e1_evidence_summary.csv
    e1_vs_e2_evidence_summary.csv
    e1_stage3_matrix_metrics_by_bid.csv
    rendered_baseline_vs_mutual.csv
    E1_RECOVERY_REPORT.md
    RENDERED_COMPARISON.md

  phaseB_viewer_qa/
    stage3_qa_fc_s2.html
    saved_views/
    viewer_case_notes.md

  phaseB_ground_closure/
    B104_GROUND_CLOSURE_REPORT.md
    ground_rejection_reasons.csv
    v1c_ground_patch_ablation.csv

  phaseB_height_definition/
    B6_HEIGHT_DEFINITION_REPORT.md
    height_breakdown_by_bid.csv
    height_metric_definition_v2.md

  phaseB_roof_decomposition/
    ROOF_DECOMPOSITION_REPORT.md
    roof_match_table.csv
    roof_merge_candidates.csv
    roof_unmatched_samples.csv
    v1c_roof_patch_ablation.csv

  phaseB_support_attribution/
    E2_SUPPORT_ATTRIBUTION_REPORT.md
    per_face_support.csv
    support_rejection_histogram.csv
    support_classwise_summary.csv
    v1c_support_patch_ablation.csv

  phaseC_stage3_v1c_ablation/
    patch_ablation_summary.csv
    PATCH_ABLATION_REPORT.md

  phaseD_final_matrix/
    matrix_metrics_by_bid.csv
    evaluator_effect_by_bid.csv
    algorithm_effect_by_bid.csv
    rendered_baseline_vs_mutual.csv
    failure_mode_classification.csv
    g2_readiness_decision.csv

  phaseD_final_decision/
    G2_READINESS_DECISION.md

  REPORT.md