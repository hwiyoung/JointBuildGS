#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1 thin runner of one GPU script of this folder in jointbuildgs:geogs-conf-guided-v1 (torch CUDA; network off,
# inputs read-only).  GPU=1 bash run_gpu_py.sh <tag> <script.py> [args ...]
# Mounts: /prep (ro), /art (ro), /s0 (ro), /out, /repo (ro). Log: logs/<tag>.log; queue.log line "<time> <tag> rc=<rc> <s>s".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
GPU=${GPU:-0}
tag=$1; shift; script=$1; shift
mkdir -p "$OUT/logs"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
[ "${SLOT:-0}" = "1" ] && { exec 9>>"$OUT/logs/slot0.lock"; flock 9; }
t0=$SECONDS
docker run --rm --name "jbgs-s1p-${tag,,}" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" --cpus 16 --memory 46g --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v "$ART:/art:ro" -v "$S0:/s0:ro" -v "$PREP:/prep:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" \
  -w /repo/scripts/phd/main_stage1_v1 --entrypoint python jointbuildgs:geogs-conf-guided-v1 "$script" "$@" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
