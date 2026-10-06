#!/usr/bin/env bash
# PHD-MAIN-METRICS-TRIAL-v1 thin runner of the GPU steps in jointbuildgs:geogs-conf-guided-v1, one at a time (TSDF host memory;
# container memory capped at MEM, default 46g), network off, inputs read-only.
#   GPU=0 bash run_gpu.sh samepath LoD2 | samepath ALS | run b1_LoD2 [--voxel 0.10] ...
# Mounts: /source fork r12 (ro), /s0 stage-0 payload (ro), /dr discard payload (ro), /out this payload, /repo (ro).
# Log: logs/gpu_<mode>_<arg>.log (an existing log is renamed first); queue.log line "<time> gpu_<mode>_<arg> rc=<rc> <s>s".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
GPU=${GPU:-0}; MEM=${MEM:-46g}
mode=$1; arg=$2; shift 2
# after the first run reached the memory cap at 0.05 m, every run uses 0.10 m (same voxel for the four trainings; recorded)
if [ "$mode" = run ] && [ -f "$OUT/logs/voxel_0.10_for_all.txt" ] && [[ "$*" != *--voxel* ]]; then set -- "$@" --voxel 0.10; fi
tag="gpu_${mode}_${arg}"
mkdir -p "$OUT/logs"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-mt-${tag,,}" --gpus "device=$GPU" --network none --user "$(id -u):$(id -g)" --cpus 16 --shm-size 8g \
  --memory "$MEM" --memory-swap "$MEM" \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e TZ=Asia/Seoul \
  -e JBGS_SPLIT_JSON=/s0/fork_inputs/s61/B173nb_b10/split.json \
  -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r12:/source:ro" \
  -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 /repo/scripts/phd/metrics_trial_v1/gpu_mt.py "$mode" "$arg" "$@" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
