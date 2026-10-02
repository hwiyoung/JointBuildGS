#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1: copy the report figures from the payload figs/ next to the report (docs/.../figures/), renamed by section.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; D="$REPO/docs/experiments/phd/main_prep_discard_rule_v1/figures"
mkdir -p "$D"
for k in ALS_roof LoD2_roof LoD2_wall; do cp "$P/figs/tradeoff_$k.png" "$D/fig1_tradeoff_$k.png"; done
for f in "$P"/figs/sites/site_*.png; do cp "$f" "$D/fig2_$(basename "$f")"; done
for f in "$P"/figs/boxmap_*.png; do cp "$f" "$D/fig3_$(basename "$f")"; done
cp "$P/figs/tau_registration.png" "$D/fig4_tau_registration.png"
cp "$P/figs/b0_conditions.png" "$D/fig5_b0_conditions.png"
cp "$P/figs/penalty_band.png" "$D/fig6_penalty_band.png"
ls "$D" | wc -l
