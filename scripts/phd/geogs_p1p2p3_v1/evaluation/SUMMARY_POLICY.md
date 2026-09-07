# Descriptive aggregation and case visibility

`summarize.py` verifies the supplied analysis policy against the frozen
`contracts/evaluation_analysis_v1.json`; regional training configuration is not
modified. All aggregates remain development diagnostics without independent
population inference.

The geometry macro groups exact candidate, surface representation, surface/reference
sampling sensitivity and distance threshold. Each region contributes equal weight.
The mean of regional F1 values differs from F1 computed from mean precision/recall;
the mean of regional p95 values is not a pooled point-level p95. Missing-reference,
missing-region and reconstruction-failure counts accompany every group. Empty
reconstruction contributes F1/precision/recall zero by the fixed convention.
Reference-to-empty-surface distance is infinite. Prediction-to-reference distance
is undefined when there are no prediction samples; its macro is explicitly null
with an undefined-with-failure status rather than averaging only surviving regions.

For every frozen distance threshold, surface rows also report
`far_from_observed_reference_area_estimate_m2 = surface_area_m2 * (1 - precision)`.
The existing precision uses distance strictly below the threshold, so its complement
estimates area at or above it. This is an area-sampling estimate of distance from
observed UAS points, not confirmed wrong residual structure area: sparse or absent
local reference coverage remains ambiguous. A zero-area prediction with observed
reference has estimate0 and retains its reconstruction-failure status and zero F1.
Absent reference yields null, even for an empty prediction. Pointset baselines have
no triangle area and yield null; technically unavailable extractions have no scored
surface row. Equal-region area means and matched differences retain these states
and do not represent pooled regional area or a uniform quality-improvement score.

Optical results are written separately as per-region image means, pooled image
means, and equal-region means. The image-pooled table gives each eligible image
equal weight; it does not weight by pixel count. Each metric records its own finite,
missing and infinite denominator, because small ROI domains may lack LPIPS while
retaining PSNR/SSIM. Identical-image positive-infinite PSNR remains explicit under
strict JSON via null numeric mean plus positive-infinity status/count. It is never
dropped to produce a finite-only favorable aggregate.

Cell tables include every cell intersecting the fixed regional XY prism, including
cells with no observed reference points. Reference absence is separate from infinite
distance to an absent reconstruction. Numeric comparisons remain null for failure
transitions, with explicit recovery, new failure, persistent failure and invalid
distance states. Ranked cases preserve those states and reference-absent examples.
The full cell table and denominators remain available. `reference_to_prior_relation`
names the actual direction: mean observed-UAS-point distance to the prior triangles.
Prior/reference relations
are evaluation-only geometric descriptors, not temporal or authority labels.
MVS/ALS cell counts describe source sample support; they do not prove photographic
visibility, texture adequacy or observation absence. Those interpretations require
the subsequent actual-image review.

Viewer case centers use the fixed cell XY center and fixed regional prism mid-Z,
with a5m navigation extent. This display frame is not fitted to a candidate or UAS.
Empty reconstructions carry an explicit reconstruction_failure viewer status,
distinct from reference_unavailable.

New aggregate tables are `geometry_region_macro.csv`, `render_all_images.csv`,
`render_pooled_image_weighted.csv` and `render_region_macro.csv`. Existing per-region
tables remain. Twelve synthetic Docker tests cover weighting distinctions,
infinity/absence, grid membership, failure/recovery cases and viewer coordinates.
They read no regional image or UAS payload and are not regional performance results.

`scientific_verdict: null`
