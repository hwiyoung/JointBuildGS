#!/usr/bin/env bash
# Resume after `both` training crashed with transient CUDA error (KST 02:28).
# 1) Train `both` from scratch
# 2) Stage 3 for `structure` + `both` only (baseline/mutual already done)
# 3) Rebuild dashboard (auto-picks up new stage3 PLYs)
set -uo pipefail
cd /workspace/JointBuildGS
OUT_ROOT="results/phase2_ablation_citygml"
SCENE="results/phase2_synthesis/scene.obj"
mkdir -p "$OUT_ROOT/_logs"

LOG_MAIN="$OUT_ROOT/_logs/resume_both.out"
: > "$LOG_MAIN"

echo "====== [$(date -u +%F\ %H:%M:%SZ)] resume: train both ======" | tee -a "$LOG_MAIN"
log="$OUT_ROOT/_logs/both.log"
: > "$log"
stdbuf -oL -eL python -m src.stage2.train --config configs/phase2_both.yaml \
    >> "$log" 2>&1
rc=$?
echo "====== [$(date -u +%F\ %H:%M:%SZ)] done: train both (rc=$rc) ======" | tee -a "$LOG_MAIN"
if [ $rc -ne 0 ]; then
    echo "[resume] both training failed (rc=$rc). aborting." | tee -a "$LOG_MAIN"
    exit $rc
fi

for COND in structure both; do
    CKPT="$OUT_ROOT/$COND/ckpt/final.pt"
    STAGE3_DIR="$OUT_ROOT/$COND/stage3"
    EVAL_DIR="$OUT_ROOT/$COND/eval"
    if [ ! -f "$CKPT" ]; then
        echo "[resume] SKIP $COND: no final.pt" | tee -a "$LOG_MAIN"
        continue
    fi
    echo "====== [$(date -u +%F\ %H:%M:%SZ)] stage3: $COND ======" | tee -a "$LOG_MAIN"
    mkdir -p "$STAGE3_DIR" "$EVAL_DIR"
    python scripts/phase2_synthesis/run_stage3.py \
        --ckpt "$CKPT" --scene "$SCENE" --out "$STAGE3_DIR" \
        > "$OUT_ROOT/_logs/${COND}_stage3.log" 2>&1
    python scripts/phase2_synthesis/eval_citygml.py \
        --stage3-dir "$STAGE3_DIR" --scene "$SCENE" --out "$EVAL_DIR" \
        > "$OUT_ROOT/_logs/${COND}_eval.log" 2>&1
done

echo "====== [$(date -u +%F\ %H:%M:%SZ)] figures ======" | tee -a "$LOG_MAIN"
python scripts/phase2_synthesis/make_figures.py --root "$OUT_ROOT" --scene "$SCENE" \
    >> "$LOG_MAIN" 2>&1 || echo "[resume] figures step failed (non-fatal)" | tee -a "$LOG_MAIN"

echo "====== [$(date -u +%F\ %H:%M:%SZ)] rebuild dashboard ======" | tee -a "$LOG_MAIN"
python tools/experiments/build_dashboard.py >> "$LOG_MAIN" 2>&1 || \
    echo "[resume] dashboard rebuild failed (non-fatal)" | tee -a "$LOG_MAIN"

echo "====== [$(date -u +%F\ %H:%M:%SZ)] resume complete ======" | tee -a "$LOG_MAIN"
