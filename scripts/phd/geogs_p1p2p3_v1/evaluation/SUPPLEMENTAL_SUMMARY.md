# Supplemental native repetition summary

Pass the exact task-local `--repeat-contract` as well as `--runtime-layout` to
`summarize.py`. `SupplementalRepeat` verifies the explicit contract and the sealed
regional repetition membership before any summary output is created.

The six configured primary conditions, primary geometry/optical macros, source
strata, and ranked cases remain separate. A supplemental `native_repeat_1`
candidate is available in the viewer with an explicit supplemental repetition
label. Its anchor panels and images use the same regional iteration8000 state;
the repetition does not add a seventh primary scientific condition.

All supplemental tables are under `evaluation/summary/supplemental_repeat/`:

- `geometry_all.csv` and `geometry_region_macro.csv` retain the same complete
  distance mean/median/p95/RMSE, accuracy/completeness/F1, sampling sensitivity,
  threshold and failure/missing-reference conventions as primary summaries.
- `geometry_primary_minus_repeat.csv` pairs identical region, candidate suffix,
  surface estimator, sampling sensitivity and threshold. It records each signed
  primary-native-minus-repeat metric difference separately.
- `render_all_images.csv`, `render_summary.csv`,
  `render_pooled_image_weighted.csv` and `render_region_macro.csv` use exactly the
  same metric-specific denominators and weighting as their primary counterparts.
- `render_primary_minus_repeat_images.csv` additionally verifies exact image,
  camera, photo hash, seed and scoring rectangle identity. The corresponding
  `render_primary_minus_repeat_summary.csv` records every expected, finite,
  infinite, undefined and unavailable pair. If any pair is nonfinite or missing,
  the unconditional mean is null; a separately named conditional finite-pair mean
  retains explicit denominators.
- `resource_summary.csv` binds the sealed supplemental receipts and trace in
  `native_repeat_allocator_v2`, checks the native condition and iteration8000
  restore, and keeps repetition costs separate from primary and shared-anchor
  costs. No full-pipeline or isolated optimizer-time total is fabricated.

Anchor differences are repeated extraction/render observations from the same
checkpoint. Final differences combine subsequent execution and extraction
variation. Neither is a confidence interval, a bound on quality noise, or an
independent variance estimate. Signed differences have metric-dependent meaning:
smaller distance/LPIPS and larger PSNR/SSIM/F1 have different favorable directions.
No repeat is used for primary ranking, best-condition selection or cell-case
selection. No scientific verdict is generated.

The dedicated synthetic fixtures read no regional RGB, UAS or training payload
and require no GPU. They check primary isolation, exact estimator matching,
failure/infinity visibility, image identity, anchor/final separation and sealed
supplemental resource paths.
