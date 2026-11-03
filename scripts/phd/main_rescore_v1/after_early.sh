#!/usr/bin/env bash
# Resume only after the requested early figures have actually been viewed once.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
cd "$REPO"
test -f "$OUT/early_figures_review.json"
bash scripts/phd/main_rescore_v1/run.sh targets-b173 targets.py B173nb_b10
bash scripts/phd/main_rescore_v1/b173_stage4_lane.sh ALS & als_pid=$!
bash scripts/phd/main_rescore_v1/b173_stage4_lane.sh LoD2 & lod_pid=$!
wait "$als_pid";wait "$lod_pid"
bash scripts/phd/main_rescore_v1/b173_diagnostics.sh
bash scripts/phd/main_rescore_v1/run.sh publish-b173-full publish_tables.py b173_full
bash scripts/phd/main_rescore_v1/run.sh figures-remaining figures.py remaining --prior ALS
git add -- configs/phd/main_rescore_v1 scripts/phd/main_rescore_v1 docs/experiments/phd/main_rescore_v1
git -c core.whitespace=cr-at-eol diff --cached --check -- configs/phd/main_rescore_v1 scripts/phd/main_rescore_v1 docs/experiments/phd/main_rescore_v1
git commit --only -m 'PHD-MAIN-RESCORE-v1: B173 judgment oracle and figures' -- configs/phd/main_rescore_v1 scripts/phd/main_rescore_v1 docs/experiments/phd/main_rescore_v1
git push origin HEAD:exp/main-experiment
bash scripts/phd/main_rescore_v1/run_site.sh B0_b10
bash scripts/phd/main_rescore_v1/run_site.sh R1rep_b10
bash scripts/phd/main_rescore_v1/run_b173_only.sh
bash scripts/phd/main_rescore_v1/run.sh input-sections choose_input_sections.py
bash scripts/phd/main_rescore_v1/run.sh figures-inputs figures.py inputs
bash scripts/phd/main_rescore_v1/run.sh compare-training-v2 compare_training_v2.py
bash scripts/phd/main_rescore_v1/run.sh publish-all publish_tables.py all
bash scripts/phd/main_rescore_v1/run.sh report-all report.py
echo ALL_CALCULATIONS_READY_FOR_FINAL_VISUAL_REVIEW
