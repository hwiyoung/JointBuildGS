# P1-4a Part B - GT-derived Evidence Relation Read-out

## 1. Purpose

This run tests whether GT-sampled position/normal/semantic evidence can be converted into a closed CityJSON shell through geometric relations. Roof archetype is not an input and is only written as a post-hoc diagnostic.

## 2. Inputs And Restrictions

- GT source: `results/phase2_synthesis/scene.obj`
- Allowed Part B inputs: sampled point position, sample normal, semantic class, support weight.
- Forbidden Part B inputs: GT roof type label, final footprint polygon, final roof model.
- Assertion: every `metrics.json` records `roof_type_label_used_in_part_b=false`, `final_footprint_used_in_part_b=false`, and `final_roof_model_used_in_part_b=false`.

## 3. Method

1. Build an evidence graph with wall/roof/ground plane candidates and relation edges.
2. Generate footprint candidates from wall support points and wall-plane support lines.
3. Generate roof surface candidates from roof plane evidence; assemble the final roof as a continuous height-field triangulation over the selected wall-derived footprint.
4. Split wall and ground boundaries against the roof boundary, then export a semantic CityJSON shell.
5. Evaluate edge incidence, val3dity availability/result, height, surface coverage, volume ratio, Hausdorff, and Chamfer.

## 4. Results

| bid | true_type_eval_only | diagnostic_archetype | val3dity | errors | h_err | coverage | vol_ratio | Hausdorff | edge_ok | verdict |
|---:|---|---|---|---|---:|---:|---:|---:|---|---|
| B1 | flat | flat-like | NOT_RUN | val3dity_not_found | 0.0000 | 0.990 | 1.000 | 0.7375 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |
| B2 | flat | flat-like | NOT_RUN | val3dity_not_found | 0.0000 | 1.000 | 1.620 | 0.6752 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |
| B8 | gable | flat-like | NOT_RUN | val3dity_not_found | 0.0010 | 0.988 | 1.392 | 0.6726 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |
| B6 | hip | hip-like | NOT_RUN | val3dity_not_found | 3.6070 | 0.883 | 0.630 | 3.9262 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |
| B0 | tri-slope | gable-like | NOT_RUN | val3dity_not_found | 0.0000 | 0.902 | 2.164 | 2.3981 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |
| B3 | complex | hip-like | NOT_RUN | val3dity_not_found | 7.3050 | 0.365 | 0.956 | 11.4784 | True | VAL3DITY_NOT_RUN_GEOMETRY_REVIEW_ONLY |

Coverage is surface coverage: sampled GT surface points within 0.5m of the relation-readout mesh.

## 5. Output Files

| bid | evidence graph | footprint graph | roof candidates | selected surfaces | cityjson | archetype | metrics |
|---:|---|---|---|---|---|---|---|
| B1 | [B1/evidence_graph.json](B1/evidence_graph.json) | [B1/footprint_graph.json](B1/footprint_graph.json) | [B1/roof_surface_candidates.json](B1/roof_surface_candidates.json) | [B1/selected_surfaces.json](B1/selected_surfaces.json) | [B1/relation_readout.city.json](B1/relation_readout.city.json) | [B1/optional_roof_archetype.json](B1/optional_roof_archetype.json) | [B1/metrics.json](B1/metrics.json) |
| B2 | [B2/evidence_graph.json](B2/evidence_graph.json) | [B2/footprint_graph.json](B2/footprint_graph.json) | [B2/roof_surface_candidates.json](B2/roof_surface_candidates.json) | [B2/selected_surfaces.json](B2/selected_surfaces.json) | [B2/relation_readout.city.json](B2/relation_readout.city.json) | [B2/optional_roof_archetype.json](B2/optional_roof_archetype.json) | [B2/metrics.json](B2/metrics.json) |
| B8 | [B8/evidence_graph.json](B8/evidence_graph.json) | [B8/footprint_graph.json](B8/footprint_graph.json) | [B8/roof_surface_candidates.json](B8/roof_surface_candidates.json) | [B8/selected_surfaces.json](B8/selected_surfaces.json) | [B8/relation_readout.city.json](B8/relation_readout.city.json) | [B8/optional_roof_archetype.json](B8/optional_roof_archetype.json) | [B8/metrics.json](B8/metrics.json) |
| B6 | [B6/evidence_graph.json](B6/evidence_graph.json) | [B6/footprint_graph.json](B6/footprint_graph.json) | [B6/roof_surface_candidates.json](B6/roof_surface_candidates.json) | [B6/selected_surfaces.json](B6/selected_surfaces.json) | [B6/relation_readout.city.json](B6/relation_readout.city.json) | [B6/optional_roof_archetype.json](B6/optional_roof_archetype.json) | [B6/metrics.json](B6/metrics.json) |
| B0 | [B0/evidence_graph.json](B0/evidence_graph.json) | [B0/footprint_graph.json](B0/footprint_graph.json) | [B0/roof_surface_candidates.json](B0/roof_surface_candidates.json) | [B0/selected_surfaces.json](B0/selected_surfaces.json) | [B0/relation_readout.city.json](B0/relation_readout.city.json) | [B0/optional_roof_archetype.json](B0/optional_roof_archetype.json) | [B0/metrics.json](B0/metrics.json) |
| B3 | [B3/evidence_graph.json](B3/evidence_graph.json) | [B3/footprint_graph.json](B3/footprint_graph.json) | [B3/roof_surface_candidates.json](B3/roof_surface_candidates.json) | [B3/selected_surfaces.json](B3/selected_surfaces.json) | [B3/relation_readout.city.json](B3/relation_readout.city.json) | [B3/optional_roof_archetype.json](B3/optional_roof_archetype.json) | [B3/metrics.json](B3/metrics.json) |

## 6. PolyFit Audit Comparison

- PolyFit audit reference: `results/stage3_v4_validation/polyfit_input_audit/AUDIT_REPORT.md`
- PolyFit GT-derived raw input result summary: B1 success; B2/B8 valid-small; B6/B0/B3 over-segmented or arrangement-limited.
- Relation read-out avoids mandatory roof-type selection and does not assemble raw plane arrangements directly. It instead builds a closed shell from wall-derived boundary plus roof evidence height relations.
- If val3dity is unavailable in this shell, geometry conclusions are limited to edge incidence and sampled metric checks until the validator is installed.

## 7. Stage2-derived Read-out Decision

- Overall Part B verdict: `B_UNDECIDED_VAL3DITY_NOT_AVAILABLE`
- Decision: rerun with `val3dity` on PATH before a formal GO/NG. Geometry artifacts and metrics are still generated for inspection.

## 8. Self-verification

- PASS: all target bids have evidence_graph.json
- PASS: all target bids have footprint_graph.json
- PASS: all target bids have roof_surface_candidates.json
- PASS: all target bids have selected_surfaces.json
- PASS: all target bids have relation_readout.city.json
- PASS: all target bids have optional_roof_archetype.json
- PASS: all target bids have metrics.json
- PASS: GT roof type not used as Part B scoring/construction input
