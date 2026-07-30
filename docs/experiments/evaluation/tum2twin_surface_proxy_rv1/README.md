# TUM2TWIN surface proxy R v1

This directory owns the promoted, frozen post-analysis snapshot from nightly run `nightly_rv1_20260728_2327`.

- [`reports/POST_RUN_SUMMARY.md`](reports/POST_RUN_SUMMARY.md) — reader entry point
- [`reports/metric_audit.md`](reports/metric_audit.md) — metric audit
- [`reports/next_oracle_prompt.md`](reports/next_oracle_prompt.md) — retained next-step prompt
- [`tables/surface_proxy_R_v1.csv`](tables/surface_proxy_R_v1.csv) — promoted classification table
- [`tables/oracle_candidates.yaml`](tables/oracle_candidates.yaml) — candidate table
- [`manifests/analysis_manifest.json`](manifests/analysis_manifest.json) — frozen provenance
- [`../../figs/tum2twin_surface_proxy_rv1/`](../../../figs/tum2twin_surface_proxy_rv1/) — three promoted figures

The mutable runtime workspace remains under `reports/nightly_rv1_20260728_2327/`; generator defaults continue to write there. This folder is the tracked reader-facing snapshot, not the live output directory.
