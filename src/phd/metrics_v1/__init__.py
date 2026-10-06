"""Metric module v1 (PHD-MAIN-METRICS-TRIAL-v1): the measuring pieces of the metrics the user fixed on 2026-10-06, tried
on the stage-0 outputs. Definitions and values: configs/phd/metrics_trial_v1/metrics_trial_v1.json.
  surface  result surface readings along a line (highest crossing, window, signed nearest crossing, 3-D distance)
  lines    spread classes (GT side, wrong side, both, neither) and the spread share
  band     edge band of the roof accuracy
  stats    signed median, NMAD, |x| quantiles, shares within thresholds
  cloud    mesh sampling, Chamfer / precision / completeness / F1, PCA normals, M3C2
  gauss    Gaussians near points, highest GT surface raster, floaters
  cells    cell-median height of a point path at GT points
Pure numpy / scipy / Open3D; tests: tests/phd/test_metrics_v1.py. scientific_verdict: null."""
