#!/usr/bin/env bash
set -euo pipefail
task_repo=$(cd "$(dirname "$0")/../../.." && pwd)
task_art=$(realpath "$task_repo/../JointBuildGS-artifacts")
task_ph="$task_art/phase-payloads/phd"
task_out="$task_ph/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1"
task_site=$1; task_prefix=$2; task_gpu=0
exec 8<"$task_ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/photo_gpu_${task_gpu}.lock"
flock -n -x 8 || exit 75
busy=$(nvidia-smi -i "$task_gpu" --query-compute-apps=pid --format=csv,noheader)
[[ -z "$busy" ]] || exit 75
exec 9<"$task_ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock"
flock -n -x 9 || exit 75
stable=0
while (( stable < 60 )); do
  available=$(awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo)
  (( available >= 56 )) || exit 75
  stable=$((stable+5)); sleep 5
done
busy=$(nvidia-smi -i "$task_gpu" --query-compute-apps=pid --format=csv,noheader)
[[ -z "$busy" ]] || exit 75
task_tag="interview-gpu-${task_site}-${task_prefix}"
log="$task_out/logs/${task_tag}_$(date +%Y%m%dT%H%M%S).log"
tar -czf "${log%.log}.source_snapshot.tar.gz" -C "$task_repo" scripts/phd/main_meshpatch_v1 configs/phd/main_meshpatch_v1 scripts/phd/main_stage1_v1
git -C "$task_repo" rev-parse HEAD > "${log%.log}.commit.txt"
set +e
docker run --rm --name "jbgs-meshpatch-$task_tag" --gpus "device=$task_gpu" --network none \
 --user "$(id -u):$(id -g)" --cpus 8 --memory 40g --memory-swap 40g --shm-size 2g \
 -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=1 \
 -e MPLCONFIGDIR=/out/cache/mpl -e TORCH_HOME=/weights/torch -e TZ=Asia/Seoul \
 -e "JBGS_SPLIT_JSON=/s0/fork_inputs/s61/$task_site/split.json" -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
 -v "$task_art:/artifacts/JointBuildGS:ro" -v "$task_art:/art:ro" -v "$task_ph:/ph:ro" \
 -v "$task_ph/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" \
 -v "$task_ph/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1:/dr:ro" \
 -v "$task_ph/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights:/weights:ro" \
 -v "$task_out:/out" -v "$task_repo:/repo:ro" -v "$task_repo/src/phd/forks/GeoGS-conf-guided-v1-r17:/source:ro" \
 -v "$task_repo/configs/phd/main_meshpatch_v1:/config:ro" -v "$task_repo/docs/experiments/phd/main_meshpatch_v1:/docs" \
 -w /repo/scripts/phd/main_meshpatch_v1 --entrypoint python jointbuildgs:geogs-conf-guided-v1 \
 interview_guard.py "gpu-${task_site}-${task_prefix}" interview_gpu.py "$task_site" "$task_prefix" 2>&1 | tee "$log"
exit "${PIPESTATUS[0]}"
