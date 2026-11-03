#!/usr/bin/env bash
# Publish the first complete comparison, then make the two-prior early figures.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
cd "$REPO"
keys=()
for prior in ALS LoD2; do
 for family in prior mvs fusion baseline_30000 GeoGS_30000 2DGS_30000 CDGS_30000; do keys+=("B173nb_b10__${prior}__${family}"); done
done
keys+=(B173nb_b10__ALS__r8_30000 B173nb_b10__LoD2__r8_7000)
for key in "${keys[@]}"; do until [[ -s "$OUT/scores/$key/values.json" ]]; do sleep 30; done; done
bash scripts/phd/main_rescore_v1/run.sh publish-b173 publish_tables.py b173
paths=(docs/experiments/phd/main_rescore_v1/B173주변_비교방법_채점.md docs/experiments/phd/main_rescore_v1/progress.md configs/phd/main_rescore_v1/input_surface_clarification.json scripts/phd/main_rescore_v1/score_mesh.py scripts/phd/main_rescore_v1/score_inputs.py scripts/phd/main_rescore_v1/publish_tables.py scripts/phd/main_rescore_v1/render_patches.py scripts/phd/main_rescore_v1/run_mesh_named.sh scripts/phd/main_rescore_v1/compare_b173_lane.sh scripts/phd/main_rescore_v1/render_b173_queue.sh scripts/phd/main_rescore_v1/inputs_b173_queue.sh)
for n in 3 4 5 7 8; do for ext in md json csv; do paths+=("docs/experiments/phd/main_rescore_v1/tables/b173_table$n.$ext"); done; done
git add -- "${paths[@]}"
git -c core.whitespace=cr-at-eol diff --cached --check -- "${paths[@]}"
git commit --only -m 'PHD-MAIN-RESCORE-v1: publish B173 comparison tables 3 and 4' -- "${paths[@]}"
git push origin HEAD:exp/main-experiment
for prior in ALS LoD2; do
 method=B173nb_b10__ALS__r8_30000; [[ "$prior" != LoD2 ]] || method=B173nb_b10__LoD2__r8_7000
 if [[ ! -f "$OUT/figure_cache/$prior/$method/receipt.json" ]]; then bash scripts/phd/main_rescore_v1/run.sh "fig-cache-$prior" figures.py prepare --prior "$prior"; fi
 bash scripts/phd/main_rescore_v1/run.sh "fig-early-$prior" figures.py early --prior "$prior"
done
echo B173_EARLY_FIGURES_READY
