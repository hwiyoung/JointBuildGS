#!/usr/bin/env bash
# Keep AXES71's original read-only path bindings; only this task's outputs are writable.
set -euo pipefail
task_repo=$(cd "$(dirname "$0")/../../.." && pwd)
task_art=$(realpath "$task_repo/../JointBuildGS-artifacts")
task_ph="$task_art/phase-payloads/phd"
task_out="$task_ph/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1"
tag=$1; shift
memory_limit=4g; cpu_limit=2
if [[ ${1:-} == --large ]]; then
  shift; memory_limit=40g; cpu_limit=8
  exec 9<"$task_ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock"
  flock -x 9
  stable=0
  while (( stable < 60 )); do
    available=$(awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo)
    if (( available >= 56 )); then stable=$((stable+5)); else stable=0; fi
    printf 'axes admission available=%s GiB stable=%ss/60s\n' "$available" "$stable"
    sleep 5
  done
fi
log="$task_out/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
tar -czf "${log%.log}.source_snapshot.tar.gz" -C "$task_repo" scripts/phd/main_meshpatch_v1 configs/phd/main_meshpatch_v1 scripts/phd/main_axes71_v2 scripts/phd/main_dist71_v1 src/phd/metrics_v3
git -C "$task_repo" rev-parse HEAD > "${log%.log}.commit.txt"
set +e
docker run --rm --name "jbgs-meshpatch-$tag" --network none --user "$(id -u):$(id -g)" \
  --cpus "$cpu_limit" --memory "$memory_limit" --memory-swap "$memory_limit" --shm-size 1g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS="$cpu_limit" -e OPENBLAS_NUM_THREADS=1 \
  -e CUDA_VISIBLE_DEVICES= -e TZ=Asia/Seoul -e PYTHONPATH=/mp/cache/python -e NUMBA_CACHE_DIR=/mp/cache/numba -e MPLCONFIGDIR=/mp/cache/mpl \
  -v "$task_repo:/repo:ro" -v "$task_art:/art:ro" -v "$task_ph:/ph:ro" -v "$task_out:/mp" \
  -v "$task_ph/main_stage1_v1/PHD-MAIN-STAGE1-v1:/out:ro" \
  -v "$task_ph/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" \
  -v "$task_ph/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1:/mt:ro" \
  -v "$task_ph/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1:/mf:ro" \
  -v "$task_ph/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1:/dr:ro" \
  -v "$task_ph/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1:/prep:ro" \
  -v "$task_ph/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1:/diag:ro" \
  -v "$task_repo/configs/phd/main_meshpatch_v1:/config" \
  -v "$task_repo/docs/experiments/phd/main_meshpatch_v1:/docs" \
  -w /repo/scripts/phd/main_meshpatch_v1 --entrypoint python jointbuildgs:dev "$@" 2>&1 | tee "$log"
exit "${PIPESTATUS[0]}"
