#!/usr/bin/env bash
# Phase 2 Step 2-2 — post-training orchestration.
# For each condition: Stage 3 (ckpt -> CityJSON) + val3dity + eval.
# Finally, make 5 figures.
set -euo pipefail

cd /workspace/JointBuildGS
ROOT="results/phase2_ablation_citygml"
SCENE="results/phase2_synthesis/scene.obj"

for COND in baseline mutual structure both; do
    CKPT="$ROOT/$COND/ckpt/final.pt"
    STAGE3_DIR="$ROOT/$COND/stage3"
    EVAL_DIR="$ROOT/$COND/eval"
    if [ ! -f "$CKPT" ]; then
        echo "[post] SKIP $COND: no final.pt"
        continue
    fi
    echo "====== [post] $COND ======"
    mkdir -p "$STAGE3_DIR" "$EVAL_DIR"
    python scripts/stage3_readout/run_stage3.py \
        --ckpt "$CKPT" --scene "$SCENE" --out "$STAGE3_DIR" \
        2>&1 | tee "$ROOT/_logs/${COND}_stage3.log"
    python scripts/stage3_readout/eval_citygml.py \
        --stage3-dir "$STAGE3_DIR" --scene "$SCENE" --out "$EVAL_DIR" \
        2>&1 | tee "$ROOT/_logs/${COND}_eval.log"
done

echo "====== [post] figures ======"
python scripts/inspection/make_figures.py --root "$ROOT" --scene "$SCENE"
echo "[post] done"
