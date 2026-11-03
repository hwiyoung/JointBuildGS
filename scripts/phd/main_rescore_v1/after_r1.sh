#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
bash scripts/phd/main_rescore_v1/run_site.sh R1rep_b10
bash scripts/phd/main_rescore_v1/run_b173_only.sh
bash scripts/phd/main_rescore_v1/run.sh input-sections choose_input_sections.py
bash scripts/phd/main_rescore_v1/run.sh figures-inputs figures.py inputs
bash scripts/phd/main_rescore_v1/run.sh compare-training-v2 compare_training_v2.py
bash scripts/phd/main_rescore_v1/run.sh publish-all publish_tables.py all
bash scripts/phd/main_rescore_v1/run.sh report-all report.py
echo ALL_CALCULATIONS_READY_FOR_FINAL_VISUAL_REVIEW
