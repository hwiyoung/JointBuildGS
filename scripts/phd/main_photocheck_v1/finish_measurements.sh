#!/usr/bin/env bash
# Continue already-authorized exports and plots once the exact measurement container exits.
# Visual review and packaging remain explicit steps after these scripts complete.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
container=$1
cmd=$(docker inspect -f '{{json .Config.Cmd}}' "$container")
[[ "$cmd" == *'/repo/scripts/phd/main_photocheck_v1/run_measure.py'* && "$cmd" == *'full'* ]]
while [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]]; do sleep 15; done
run="$repo/scripts/phd/main_photocheck_v1/run.sh"
bash "$run" cpu export_final export_final.py
bash "$run" cpu evaluate_full evaluate.py full
bash "$run" cpu inventory_full inventory_report.py full
bash "$run" cpu figures_full figures.py full
bash "$run" cpu maps_montages_full maps_montages.py full
bash "$run" cpu independent_full verify_image_score.py --stage full
bash "$run" cpu execution_summary execution_summary.py
bash "$run" cpu report_full report.py full
bash "$run" cpu validate_delivery validate_delivery.py
bash "$run" cpu qa_sheets_full qa_sheets.py full
