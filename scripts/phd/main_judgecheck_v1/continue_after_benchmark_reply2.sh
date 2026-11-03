#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
while [[ ! -f "$OUT/r2/photo_scores/6908_53359/complete.json" ]]; do sleep 30; done
bash scripts/phd/main_judgecheck_v1/run_cpu.sh wholeparity verify_whole_tile_reply2.py
bash scripts/phd/main_judgecheck_v1/run_cpu.sh wholetiming timing_reply2.py
bash scripts/phd/main_judgecheck_v1/run_cpu.sh sourcefreeze audit_source_reply2.py
bash scripts/phd/main_judgecheck_v1/run_census_reply2.sh roofs
