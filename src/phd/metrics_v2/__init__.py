"""Metric module v2 (PHD-MAIN-METRICS-FIX-v1): metrics_v1 with the fixes of 2026-10-06 (configs/phd/metrics_fix_v1/metrics_fix_v1.json).
metrics_v1 stays unchanged so that the trial numbers can be reproduced.
  surface, lines, cloud, gauss, cells   byte-identical to v1
  band      v1 + edge_band_v2 (the slope's own height range taken off)
  stats     v1 + bias_dispersion (bias = signed median; dispersion = NMAD, median |x - median|, its 68.3 % / 95 % quantiles)
  regions   new: |MVS - GT| read at the GT points, the split of codes 2 / 3 and 11 / 12
  bins      new: merging of small size bins, the correction boundary
  readings  new: vertical difference on gentle faces, normal distance on steep faces
Tests: tests/phd/test_metrics_v2.py. scientific_verdict: null."""
