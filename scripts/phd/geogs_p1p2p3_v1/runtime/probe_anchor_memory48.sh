#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
probe="$task_root/runtime/host_memory_recovery_v1/anchor_mem48_probe"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
exec 8>"$task_root/queue_allocator_v2/locks/gpu0.lock"
flock -n 8
exec 9>"$task_root/queue_allocator_v2/locks/gpu1.lock"
flock -n 9
test -z "$(docker ps --filter name=jbgs-geogs-P --format '{{.Names}}')"
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
test "$available_kib" -ge 58720256
test ! -e "$probe"
mkdir "$probe"
cp -p -- "${BASH_SOURCE[0]}" "$probe/launcher_snapshot.sh"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/probe_anchor_memory48.py" "$probe/driver_snapshot.py"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/resource_schedule.py" "$probe/resource_schedule_snapshot.py"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/parse_extraction.py" "$probe/parse_extraction_snapshot.py"
printf '%s\n' "$available_kib" > "$probe/host_mem_available_before_kib.txt"
command=(docker create --name jbgs-geogs-P1-anchor-mem48-probe-v1 --network none --gpus device=0
  --cpus 8 --memory 48g --shm-size 4g --user "$(id -u):$(id -g)"
  --env JBGS_RUNTIME_IMAGE_ID="$image" --env PYTHONDONTWRITEBYTECODE=1
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8
  --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly"
  --mount "type=bind,src=$task_root/inputs/P1,dst=/input,readonly"
  --mount "type=bind,src=$task_root/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000,dst=/anchor,readonly"
  --mount "type=bind,src=$task_root/runs_allocator_v2/P1/D005_Pnative/model/cfg_args,dst=/final_cfg_args,readonly"
  --mount "type=bind,src=$task_root/runs_allocator_v2/P1/D005_Pnative/train_receipt.json,dst=/final_train_receipt.json,readonly"
  --mount "type=bind,src=$task_root/contracts/execution_v1.json,dst=/config.json,readonly"
  --mount "type=bind,src=$task_root/contracts/runtime_layout_allocator_v2.json,dst=/runtime_layout.json,readonly"
  --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly"
  --mount "type=bind,src=$probe,dst=/probe" "$image" python /probe/driver_snapshot.py)
printf '%q ' "${command[@]}" > "$probe/command.sh"
printf '\n' >> "$probe/command.sh"
"${command[@]}" > "$probe/container_id.txt"
container="$(cat "$probe/container_id.txt")"
docker inspect "$container" > "$probe/container_before.json"
set +e
docker start -a "$container" > "$probe/driver.log" 2>&1
code=$?
set -e
printf '%s\n' "$code" > "$probe/docker_start_exit_code.txt"
docker inspect "$container" > "$probe/container_after.json"
printf '%s\n' "Single anchor48GiB probe finished, exit=$code, evidence=$probe"
tail -n 5 "$probe/driver.log"
exit "$code"
