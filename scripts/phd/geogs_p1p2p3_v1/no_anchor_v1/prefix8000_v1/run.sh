#!/usr/bin/env bash
set -euo pipefail
prefix_region="${1:?activate or P1/P2/P3}"
prefix_mode="${2:-}"
prefix_gpu="${3:-}"
prefix_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
prefix_task=$(realpath "$prefix_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
prefix_root="$prefix_task/completed_prefix8000_v1"
prefix_code="$prefix_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1"
prefix_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
prefix_guard_sha=2e89b2f386b01ea7ec3db67996114fa80060e6ac3ed3a1f35e29ff9ef6c6d20f
prefix_policy="$prefix_task/contracts/sfm_prefix8000_diagnostic_v1.json"
test "$(sha256sum "$prefix_policy" | cut -d ' ' -f1)" = a312c4999ff590d757116dc0f4a90695020e3ac70130df24fdf6e02a0eb769f0
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$prefix_image"
test "$(sha256sum "$prefix_code/resource_guard.py" | cut -d ' ' -f1)" = "$prefix_guard_sha"
prefix_capture_gpu() {
  local prefix_capture_phase="$1" prefix_capture_exit
  if nvidia-smi -i "$prefix_gpu" --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits \
      > "$prefix_guard_dir/${prefix_capture_phase}_compute.csv" 2> "$prefix_guard_dir/${prefix_capture_phase}_compute.stderr"; then prefix_capture_exit=0; else prefix_capture_exit=$?; fi
  printf '%s\n' "$prefix_capture_exit" > "$prefix_guard_dir/${prefix_capture_phase}_nvidia_exit.txt"
  if nvidia-smi -i "$prefix_gpu" --query-gpu=index,uuid,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits \
      > "$prefix_guard_dir/${prefix_capture_phase}_gpu.csv" 2> "$prefix_guard_dir/${prefix_capture_phase}_gpu.stderr"; then prefix_capture_exit=0; else prefix_capture_exit=$?; fi
  printf '%s\n' "$prefix_capture_exit" > "$prefix_guard_dir/${prefix_capture_phase}_gpu_query_exit.txt"
  cat /proc/72937/stat > "$prefix_guard_dir/${prefix_capture_phase}_proc_stat.txt" 2> "$prefix_guard_dir/${prefix_capture_phase}_proc_stat.stderr" || true
  cat /proc/72937/comm > "$prefix_guard_dir/${prefix_capture_phase}_proc_comm.txt" 2> "$prefix_guard_dir/${prefix_capture_phase}_proc_comm.stderr" || true
  readlink /proc/72937/exe > "$prefix_guard_dir/${prefix_capture_phase}_proc_exe.txt" 2> "$prefix_guard_dir/${prefix_capture_phase}_proc_exe.stderr" || true
  date -u +%FT%TZ > "$prefix_guard_dir/${prefix_capture_phase}_utc.txt"
}
prefix_cpu_guard() {
  local prefix_guard_phase="$1"
  shift
  docker run --rm --network none --read-only --cpus 2 --memory 256m --memory-swap 256m \
    --user "$(id -u):$(id -g)" --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$prefix_guard_dir,dst=/evidence" "${prefix_guard_extra[@]}" \
    "$prefix_image" python /evidence/resource_guard.py --phase "$prefix_guard_phase" --region "$prefix_region" \
    --gpu "$prefix_gpu" --root /evidence "$@" \
    > "$prefix_guard_dir/${prefix_guard_phase}_guard_stdout.log" 2> "$prefix_guard_dir/${prefix_guard_phase}_guard_stderr.log"
}
declare -A prefix_attempts=(
  [P1]=no_anchor_sfm_memory_recovery_v2
  [P2]=no_anchor_sfm_memory_recovery_P2_v2
  [P3]=no_anchor_sfm_memory_recovery_P3_v3
)
prefix_mounts=(--mount "type=bind,src=$prefix_policy,dst=/policy.json,readonly")
for prefix_parent_region in P1 P2 P3; do
  prefix_parent="$prefix_task/${prefix_attempts[$prefix_parent_region]}/runs/$prefix_parent_region/SFM_noanchor_D005_Pnative"
  test -d "$prefix_parent"
  prefix_mounts+=(--mount "type=bind,src=$prefix_parent,dst=/parents/$prefix_parent_region,readonly")
done
prefix_resources=(--cpus 2 --memory 2g --memory-swap 2g --env NVIDIA_VISIBLE_DEVICES=void)
prefix_args=(--activate)
prefix_script=validate.py
if [[ "$prefix_region" == activate ]]; then
  test -z "$prefix_mode"
  prefix_out="$prefix_root/activation"
  mkdir -p -- "$prefix_out"
  test ! -e "$prefix_out/receipt.json"
else
  case "$prefix_region" in P1|P2|P3) ;; *) exit 2 ;; esac
  case "$prefix_mode" in validate|export) ;; *) exit 2 ;; esac
  prefix_experiment="$prefix_task/${prefix_attempts[$prefix_region]}"
  prefix_run="$prefix_experiment/runs/$prefix_region/SFM_noanchor_D005_Pnative"
  prefix_out="$prefix_root/$prefix_region/$prefix_mode"
  if [[ "$prefix_mode" == validate ]]; then prefix_out="$prefix_root/$prefix_region/validation"; fi
  test ! -e "$prefix_out"
  test -s "$prefix_root/activation/receipt.json"
  prefix_args=(--region "$prefix_region")
  prefix_mounts+=(
    --mount "type=bind,src=$prefix_root/activation,dst=/activation,readonly"
    --mount "type=bind,src=$prefix_run,dst=/trained,readonly"
    --mount "type=bind,src=$prefix_experiment/config.json,dst=/config.json,readonly"
    --mount "type=bind,src=$prefix_task/contracts/execution_v1.json,dst=/base_config.json,readonly"
    --mount "type=bind,src=$prefix_experiment/amendment.json,dst=/amendment.json,readonly"
    --mount "type=bind,src=$prefix_experiment/source,dst=/source,readonly"
    --mount "type=bind,src=$prefix_experiment/inputs/$prefix_region,dst=/sfm_input,readonly"
    --mount "type=bind,src=$prefix_task/inputs/$prefix_region,dst=/input,readonly")
  if [[ "$prefix_mode" == export ]]; then
    case "$prefix_gpu" in 0|1) ;; *) exit 2 ;; esac
    test -s "$prefix_root/$prefix_region/validation/receipt.json"
    prefix_guard_dir="$prefix_root/$prefix_region/resource_checks_$(date -u +%Y%m%dT%H%M%S%N)"
    mkdir -p -- "$prefix_guard_dir" "$prefix_task/no_anchor_sfm_v1/locks"
    cp -- "$prefix_code/resource_guard.py" "$prefix_guard_dir/"
    exec 9> "$prefix_task/no_anchor_sfm_v1/locks/final_retry_gpu_$prefix_gpu.lock"
    if ! flock -n 9; then
      printf '%s\n' 'GPU lane lock held; prefix export was not launched.' > "$prefix_guard_dir/resource_not_ready.log"
      exit 3
    fi
    printf '%s\n' "final_retry_gpu_$prefix_gpu.lock held through export and boundary recording" > "$prefix_guard_dir/lane_lock.txt"
    prefix_guard_extra=()
    prefix_capture_gpu before
    prefix_cpu_guard before
    prefix_script=export.py
    prefix_resources=(--gpus "device=$prefix_gpu" --cpus 8 --memory 32g --memory-swap 32g --shm-size 4g)
    prefix_mounts+=(
      --mount "type=bind,src=$prefix_root/$prefix_region/validation,dst=/validation,readonly"
      --mount "type=bind,src=$prefix_task/runtime/weights,dst=/weights,readonly")
  else
    test -z "$prefix_gpu"
  fi
  mkdir -p -- "$prefix_out"
fi
prefix_stamp=$(date -u +%Y%m%dT%H%M%S%N)
prefix_snapshot="$prefix_out/driver_$prefix_stamp"
mkdir -- "$prefix_snapshot"
cp -- "$prefix_code/common.py" "$prefix_code/validate.py" "$prefix_code/export.py" "$prefix_code/run.sh" "$prefix_code/resource_guard.py" "$prefix_snapshot/"
cp -- "$prefix_policy" "$prefix_snapshot/policy.json"
if [[ "$prefix_mode" == export ]]; then
  cp -- "$prefix_repo/scripts/phd/geogs_p1p2p3_v1/parse_extraction.py" "$prefix_snapshot/"
  prefix_mounts+=(--mount "type=bind,src=$prefix_snapshot/parse_extraction.py,dst=/audit/parse_extraction.py,readonly")
fi
prefix_mounts+=(--mount "type=bind,src=$prefix_snapshot,dst=/prefix,readonly")
(cd -- "$prefix_snapshot" && sha256sum ./*.py ./run.sh ./policy.json > source_hashes.txt)
git -C "$prefix_repo" rev-parse HEAD > "$prefix_snapshot/git_head.txt"
prefix_command=(docker run --rm --name "jbgs-geogs-prefix8000-${prefix_region}-${prefix_mode:-activation}"
  --network none "${prefix_resources[@]}" --user "$(id -u):$(id -g)"
  --env PYTHONDONTWRITEBYTECODE=1 --env JBGS_RUNTIME_IMAGE_ID="$prefix_image"
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-prefix-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2
  "${prefix_mounts[@]}" --mount "type=bind,src=$prefix_out,dst=/output"
  "$prefix_image" /opt/geogs/bin/python "/prefix/$prefix_script" "${prefix_args[@]}")
printf '%q ' "${prefix_command[@]}" > "$prefix_snapshot/command.sh"
printf '\n' >> "$prefix_snapshot/command.sh"
prefix_finish() {
  local prefix_exit=$? prefix_guard_exit=0
  trap - EXIT
  if [[ "$prefix_mode" == export ]]; then
    prefix_capture_gpu after
    prefix_guard_extra=(--mount "type=bind,src=$prefix_out,dst=/export")
    prefix_cpu_guard after --export-root /export --wrapper-exit "$prefix_exit" || prefix_guard_exit=$?
    printf '%s\n' "$prefix_guard_dir" > "$prefix_out/resource_observations_path.txt"
    if [[ "$prefix_exit" == 0 && "$prefix_guard_exit" != 0 ]]; then prefix_exit="$prefix_guard_exit"; fi
  fi
  printf '%s\n' "$prefix_exit" > "$prefix_snapshot/wrapper_exit_code.txt"
  exit "$prefix_exit"
}
trap prefix_finish EXIT
"${prefix_command[@]}" > "$prefix_snapshot/stdout.log" 2> "$prefix_snapshot/stderr.log"
cat "$prefix_snapshot/stdout.log"
