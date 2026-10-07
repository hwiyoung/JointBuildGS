"""Metric module v3 (PHD-MAIN-STAGE1-v1): metrics_v2 with the preparation of stage 1 (configs/phd/main_stage1_v1/main_stage1_v1.json).
metrics_v1 and metrics_v2 stay unchanged so that the trial and fix numbers can be reproduced.
  surface, lines, cloud, gauss, cells, band, stats, regions, bins, readings   byte-identical to v2
  align     new: the pooled two-pass median of the common GT height shift (pixel selection of the per-box alignment)
  thin      new: one GT point per 0.1 m cell (roof-like: horizontal cells; wall-like: cells on the wall plane)
  premise   new: premise value, premise violation (|MVS - prior| > k tau on observation-error patches), the 2 m band
  gate      new: s_r pooled over cells (ISO 5725-2, n = 2), r = 2.8 s_r, the three-way decision, the pass rule
Tests: tests/phd/test_metrics_v3.py. scientific_verdict: null."""
