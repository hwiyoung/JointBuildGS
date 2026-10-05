#!/usr/bin/env bash
# Explicit opt-in diagnostic only. Never invoked by the live experiment queue.
set -euo pipefail
test "$#" -eq 0
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$(cd "$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1" && pwd)"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
failed_invocation="$task_root/native_repeat_allocator_v2/P2/D005_Pnative/train_invocation.json"
anchor="$task_root/runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000"
code="$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/diagnose_repeat_memory.py"
config="$repo_root/configs/phd/geogs_p1p2p3_v1/p2_repeat_memory_diagnostic_v1.json"
test -s "$failed_invocation"
test -s "$code"
test -s "$config"
# The same GPU1 task lock remains held until the container/finalizer finish.
exec 9>"$task_root/queue_allocator_v2/locks/gpu1.lock"
flock -n 9
root="$task_root/runtime/p2_repeat_memory_diagnostic_v1"
mkdir -p "$root"
attempt="$(mktemp -d "$root/attempt.XXXXXX")"
mkdir "$attempt/output" "$attempt/snapshots"
cp -p -- "$code" "$attempt/snapshots/diagnose_repeat_memory.py"
cp -p -- "$config" "$attempt/snapshots/config.json"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/snapshots/run_repeat_memory_diagnostic.sh"
date -u +'%Y-%m-%dT%H:%M:%S.%NZ' > "$attempt/diagnostic_launcher_started_utc.txt"
git -C "$repo_root" rev-parse HEAD > "$attempt/diagnostic_git_head.txt"
printf '%s\n' "$image" > "$attempt/diagnostic_image_id.txt"
inside='set +e
python /diagnostic/diagnose_repeat_memory.py --mode preflight > /output/diagnostic_preflight_stdout.log 2> /output/diagnostic_preflight_stderr.log
preflight_status=$?
printf "%s\n" "$preflight_status" > /output/diagnostic_preflight_exit_code.txt
if test "$preflight_status" -eq 0; then
  python /diagnostic/diagnose_repeat_memory.py --mode run > /output/diagnostic_train_stdout.log 2> /output/diagnostic_train_stderr.log
  native_status=$?
  printf "%s\n" "$native_status" > /output/diagnostic_native_exit_code.txt
  finalize_args=(--preflight-exit 0 --native-exit "$native_status")
else
  finalize_args=(--preflight-exit "$preflight_status")
fi
python /diagnostic/diagnose_repeat_memory.py --mode finalize "${finalize_args[@]}" > /output/diagnostic_finalize_stdout.log 2> /output/diagnostic_finalize_stderr.log
final_status=$?
printf "%s\n" "$final_status" > /output/diagnostic_finalize_exit_code.txt
cat /output/diagnostic_finalize_stdout.log
if test "$final_status" -ne 0; then exit "$final_status"; fi
if test "$preflight_status" -ne 0; then exit "$preflight_status"; fi
exit "$native_status"'
command=(docker run --rm --name "jbgs-geogs-P2-memory-diagnostic-${attempt##*.}"
  --network none --gpus device=1 --cpus 8 --memory 32g --shm-size 4g
  --user "$(id -u):$(id -g)" --workdir /source
  --env JBGS_RUNTIME_IMAGE_ID="$image" --env PYTHONDONTWRITEBYTECODE=1
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env LD_LIBRARY_PATH=/opt/geogs/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --env JBGS_RUNTIME_REVISION=allocator_v2
  --env JBGS_REPEAT_ID=native_repeat_1
  --env JBGS_REPEAT_CONTRACT_SHA256=3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc
  --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly"
  --mount "type=bind,src=$task_root/inputs/P2,dst=/input,readonly"
  --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly"
  --mount "type=bind,src=$anchor,dst=/anchor,readonly"
  --mount "type=bind,src=$task_root/contracts/execution_v1.json,dst=/execution_config.json,readonly"
  --mount "type=bind,src=$failed_invocation,dst=/failed_invocation.json,readonly"
  --mount "type=bind,src=$attempt/snapshots,dst=/diagnostic,readonly"
  --mount "type=bind,src=$attempt/output,dst=/output"
  "$image" bash -c "$inside")
printf '%q ' "${command[@]}" > "$attempt/diagnostic_docker_command.sh"
printf '\n' >> "$attempt/diagnostic_docker_command.sh"
cp -p -- "$attempt/diagnostic_docker_command.sh" "$attempt/snapshots/docker_command.sh"
if "${command[@]}" > "$attempt/diagnostic_docker_stdout.log" 2> "$attempt/diagnostic_docker_stderr.log"; then status=0; else status=$?; fi
printf '%s\n' "$status" > "$attempt/diagnostic_docker_exit_code.txt"
date -u +'%Y-%m-%dT%H:%M:%S.%NZ' > "$attempt/diagnostic_launcher_finished_utc.txt"
printf 'Diagnostic preserved at %s (exit %s)\n' "$attempt" "$status"
exit "$status"
