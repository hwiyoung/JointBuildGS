#!/usr/bin/env bash
# PHD-CH6-SUPPORT-v1: copy the report figures and tables from the payload next to the report (host, plain file copies).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
P="$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/ch6_support_v1/PHD-CH6-SUPPORT-v1"
D="$REPO/docs/experiments/phd/ch6_support_v1"
mkdir -p "$D/figures" "$D/tables"
cp "$P/t3/fig6_1_regions.png" "$P/t3/fig6_1_regions.pdf" "$P/t3/fig6_2_prior_minus_gt.png" "$D/figures/"
cp "$P/t4/figs/fig_t4_scatter.png" "$P/t4/figs/fig_t4_maps.png" "$D/figures/"
cp "$P/t5/judge/figs/fig_t5_bars.png" "$P/t5/judge/figs/fig_t5_bins.png" "$P/t5/judge/figs/fig_t5_conc.png" \
   "$P/t5/judge/figs/fig_t5_maps_LoD2.png" "$P/t5/judge/figs/fig_t5_maps_ALS.png" "$D/figures/"
cp "$P/t3/sites.csv" "$D/tables/fig6_1_sites.csv"
cp "$P/t5/judge/tables.md" "$D/tables/t5_tables.md"
cp "$P/t5/judge/bins.md" "$D/tables/t5_bins.md"
cp "$P/t4/candidates.csv" "$D/tables/t4_candidates.csv"
cp "$P/t4/strict.csv" "$D/tables/t4_strict.csv"
cp "$P/t4/cases.json" "$D/tables/t4_cases.json"
du -sh "$D/figures" "$D/tables"
