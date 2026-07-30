#!/usr/bin/env bash
# Phase 2 Step 2-2 — Sequential 4-condition training launcher.
#
# Runs 4 configs serially on the single GPU. Each writes ckpt/train.log/tb/renders
# to results/phase2_ablation_citygml/<condition>/.
#
# Usage (inside container):
#   bash scripts/mutual_loss/run_ablation.sh
set -euo pipefail

cd /workspace/JointBuildGS
OUT_ROOT="results/phase2_ablation_citygml"
mkdir -p "$OUT_ROOT/_logs"

run_one() {
    local cond="$1"
    local cfg="configs/phase2_${cond}.yaml"
    local log="$OUT_ROOT/_logs/${cond}.log"
    echo "====== [$(date +%H:%M:%S)] start: $cond ======" | tee -a "$log"
    # stdbuf so tqdm lines flush and Monitor can pick up progress
    stdbuf -oL -eL python -m src.stage2.train --config "$cfg" \
        >> "$log" 2>&1
    echo "====== [$(date +%H:%M:%S)] done:  $cond ======" | tee -a "$log"
}

for cond in baseline mutual structure both; do
    run_one "$cond"
done

echo "[run_ablation] all 4 conditions complete"
