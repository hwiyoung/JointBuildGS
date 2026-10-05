#!/usr/bin/env bash
# One fixed GPU1 RGB preview. The running GPU0 trainer is mounted read-only.
set -euo pipefail
test "$#" -eq 0
pv_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
pv_task=$(realpath "$pv_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
pv_attempt=no_anchor_sfm_gradient_memory_v3_P2
pv_exp="$pv_task/$pv_attempt"
pv_parent="$pv_exp/runs/P2/SFM_noanchor_D005_Pnative"
pv_out="$pv_task/preview22000_v1/P2"
pv_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
pv_policy="$pv_task/contracts/sfm_prefix22000_rgb_preview_v1.json"
pv_parent_name=jbgs-geogs-no_anchor_sfm_gradient_memory_v3_P2-P2-train
test "$(docker image inspect "$pv_image" --format '{{.Id}}')" = "$pv_image"
test "$(sha256sum "$pv_policy" | cut -d ' ' -f1)" = b104c30133fc22a26b35428a1865f78c6a8e3d86d2186d3552897c130c19dcfc
cmp -s "$pv_policy" "$pv_repo/configs/phd/geogs_p1p2p3_v1/sfm_prefix22000_rgb_preview_v1.json"
exec 9>"$pv_task/no_anchor_sfm_v1/locks/final_retry_gpu_1.lock"
flock -n 9
exec 8>"$pv_task/no_anchor_sfm_v1/locks/heavy_cpu.lock"
flock -n 8
test ! -e "$pv_out"
mkdir -p "$pv_out/driver_snapshot" "$pv_out/resource_observations"
cp -- "${BASH_SOURCE[0]}" "$pv_out/driver_snapshot/run.sh"
cp -- "$(dirname -- "${BASH_SOURCE[0]}")/driver.py" "$pv_out/driver_snapshot/driver.py"
pv_obs="$pv_out/resource_observations"
pv_inspect_format='{"Id":{{json .Id}},"Name":{{json .Name}},"State":{{json .State}},"Image":{{json .Image}},"Memory":{{json .HostConfig.Memory}},"NanoCpus":{{json .HostConfig.NanoCpus}},"DeviceRequests":{{json .HostConfig.DeviceRequests}}}'
pv_observe() {
  local pv_when="$1"
  date --utc --iso-8601=ns > "$pv_obs/$pv_when.time.txt"
  cat /proc/meminfo > "$pv_obs/$pv_when.meminfo.txt"
  nvidia-smi -i 1 --query-gpu=index,uuid,memory.total,memory.used,utilization.gpu --format=csv > "$pv_obs/$pv_when.gpu1.csv" 2> "$pv_obs/$pv_when.gpu1.stderr"
  nvidia-smi -i 1 --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits > "$pv_obs/$pv_when.compute.csv" 2> "$pv_obs/$pv_when.compute.stderr"
  docker inspect "$pv_parent_name" --format "$pv_inspect_format" > "$pv_obs/$pv_when.parent.json" 2> "$pv_obs/$pv_when.parent.stderr" || true
}
pv_finish() {
  local pv_code=$?
  trap - EXIT
  set +e
  pv_observe after
  printf '%s\n' "$pv_code" > "$pv_out/wrapper_exit_code.txt"
  docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g \
    --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$pv_out,dst=/output" \
    --mount "type=bind,src=$pv_parent,dst=/parent,readonly" \
    "$pv_image" python /output/driver_snapshot/driver.py --boundary-exit "$pv_code" \
    > "$pv_out/boundary_stdout.log" 2> "$pv_out/boundary_stderr.log"
  local pv_boundary_code=$?
  printf '%s\n' "$pv_boundary_code" > "$pv_out/boundary_exit_code.txt"
  if [[ "$pv_code" -eq 0 && "$pv_boundary_code" -ne 0 ]]; then
    pv_code="$pv_boundary_code"
    printf '%s\n' "$pv_code" > "$pv_out/wrapper_exit_code.txt"
  fi
  exit "$pv_code"
}
trap pv_finish EXIT
pv_observe before
test ! -s "$pv_obs/before.compute.csv"
test "$(awk '/^MemAvailable:/ {print $2}' "$pv_obs/before.meminfo.txt")" -ge 33554432
pv_cmd=(docker run --rm --name jbgs-geogs-preview22000-v1-P2
  --network none --gpus device=1 --cpus 2 --memory 16g --memory-swap 16g --shm-size 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env "JBGS_RUNTIME_IMAGE_ID=$pv_image" --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  --env MPLCONFIGDIR=/tmp/geogs-preview-matplotlib
  --mount "type=bind,src=$pv_out/driver_snapshot,dst=/preview_code,readonly"
  --mount "type=bind,src=$pv_parent,dst=/parent,readonly"
  --mount "type=bind,src=$pv_exp/source,dst=/source,readonly"
  --mount "type=bind,src=$pv_exp/inputs/P2,dst=/sfm_input,readonly"
  --mount "type=bind,src=$pv_task/inputs/P2,dst=/input,readonly"
  --mount "type=bind,src=$pv_exp/config.json,dst=/config.json,readonly"
  --mount "type=bind,src=$pv_task/contracts/execution_v1.json,dst=/base_config.json,readonly"
  --mount "type=bind,src=$pv_exp/amendment.json,dst=/amendment.json,readonly"
  --mount "type=bind,src=$pv_policy,dst=/policy.json,readonly"
  --mount "type=bind,src=$pv_task/completed_prefix8000_v1/P2/export/model/test/ours_8000/gt,dst=/historical_gt,readonly"
  --mount "type=bind,src=$pv_task/completed_prefix8000_v1/P2/export/receipt.json,dst=/historical_export_receipt.json,readonly"
  --mount "type=bind,src=$pv_out,dst=/output"
  "$pv_image" python /preview_code/driver.py)
printf '%q ' "${pv_cmd[@]}" > "$pv_out/command.sh"
printf '\n' >> "$pv_out/command.sh"
"${pv_cmd[@]}" > "$pv_out/wrapper_stdout.log" 2> "$pv_out/wrapper_stderr.log"
cat "$pv_out/wrapper_stdout.log"
