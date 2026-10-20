#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1: copy the payload's tables, figures (with their number json) and check comparisons into the docs folder
# (host; copies only; the docs folder is what is committed). scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
FT="$ART/phase-payloads/phd/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"; D="$REPO/docs/experiments/phd/main_fixtest_v1"
mkdir -p "$D/tables" "$D/figures"
[ -d "$FT/tables" ] && find "$FT/tables" -maxdepth 1 -type f \( -name '*.md' -o -name '*.json' \) -exec cp -p {} "$D/tables/" \;
[ -d "$FT/figs" ] && find "$FT/figs" -maxdepth 1 -type f \( -name '*.png' -o -name '*.json' -o -name '*.pdf' \) -exec cp -p {} "$D/figures/" \;
for k in dry probe; do
  [ -f "$FT/checks/compare_$k.md" ] && cp -p "$FT/checks/compare_$k.md" "$D/tables/checks_compare_$k.md"
  [ -f "$FT/checks/compare_$k.json" ] && cp -p "$FT/checks/compare_$k.json" "$D/tables/checks_compare_$k.json"
done
for f in "$FT"/prep/w_decision_*.json "$FT"/prep/figpos.json; do [ -f "$f" ] && cp -p "$f" "$D/tables/"; done
echo "synced $(date '+%m-%d %H:%M:%S')"
