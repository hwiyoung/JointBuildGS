#!/usr/bin/env bash
set -euo pipefail
r=$(cd "$(dirname "$0")/../../.." && pwd)
a=$(realpath "$r/../JointBuildGS-artifacts")
p="$a/phase-payloads/phd"
o="$p/main_target_v1/PHD-MAIN-TARGET-v1"
key=$1;kind=$2
exec 9<"$p/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock"
flock -x 9
stable=0
while ((stable < 15)); do
 available=$(awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo)
 if ((available >= 48));then stable=$((stable+5));else stable=0;fi
 sleep 5
done
mkdir -p "$o/r7_continue/axes_logs"
log="$o/r7_continue/axes_logs/${key}_${kind}_$(date +%Y%m%dT%H%M%S).log"
docker run --rm --read-only --name "jbgs-target-axes-${key}-${kind}" --network none --runtime runc --user "$(id -u):$(id -g)" \
 --cpus 6 --memory 32g --memory-swap 32g --shm-size 1g -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
 -e OMP_NUM_THREADS=6 -e OPENBLAS_NUM_THREADS=1 -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e TZ=Asia/Seoul \
 -e PYTHONPATH=/repo -e NUMBA_CACHE_DIR=/target/tmp/numba -e MPLCONFIGDIR=/target/tmp/mpl -e TMPDIR=/target/tmp \
 -v "$r:/repo:ro" -v "$a:/art:ro" -v "$p:/ph:ro" -v "$o:/target:rw" \
 -v "$p/main_stage1_v1/PHD-MAIN-STAGE1-v1:/out:ro" -v "$p/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" \
 -v "$p/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1:/mt:ro" -v "$p/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1:/mf:ro" \
 -v "$p/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1:/dr:ro" -v "$p/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1:/prep:ro" \
 -v "$p/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1:/diag:ro" -v "$r/configs/phd/main_target_v1:/cfg:ro" \
 -v "$r/docs/experiments/phd/main_target_v1:/docs:rw" --entrypoint python jointbuildgs:dev \
 /repo/scripts/phd/main_target_v1/axes_continue_r7_lod2.py "$key" "$kind" 2>&1 | tee "$log"
