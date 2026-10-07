#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1 thin runner of one GPU step (gpu_s1.py) in jointbuildgs:geogs-conf-guided-v1 (network off, inputs read-only).
#   GPU=0 [MEM=46g] bash run_gpu.sh <tag> <mode> <site> <arg>    (MEM: the container memory limit; 72g for the GeoGS TSDF, 2026-10-08)
# Mounts: /s0 stage-0 payload (ro), /dr discard payload (ro), /out this payload, /repo (ro), /source fork r12 (ro), /weights (ro).
# Log: logs/<tag>.log (an existing log is renamed first); queue.log line "<time> <tag> rc=<rc> <s>s".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
W="$PH/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights"
GPU=${GPU:-0}
tag=$1; mode=$2; site=$3; arg=$4
mkdir -p "$OUT/logs"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
[ "${SLOT:-0}" = "1" ] && { exec 9>>"$OUT/logs/slot0.lock"; flock 9; }   # during the trainings: at most two trainings + one other job
t0=$SECONDS
docker run --rm --name "jbgs-s1g-${tag,,}" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" --cpus 16 --memory "${MEM:-46g}" --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e TORCH_HOME=/weights/torch \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True -e JBGS_SPLIT_JSON=/s0/fork_inputs/s61/$site/split.json \
  -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" -v "$W:/weights:ro" \
  -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 /repo/scripts/phd/main_stage1_v1/gpu_s1.py "$mode" "$site" "$arg" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
