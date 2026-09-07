#!/usr/bin/env bash
# Stage four completed finals, temporarily hold only the dispatcher, and extract.
# Run the frozen copy in a unique systemd user service with WorkingDirectory=repo,
# JBGS_MATCHED_UNIT=<unit>.service, finite RuntimeMaxSec, Restart=no, and:
# ExecStopPost=/bin/bash <snapshot>/run_matched_compare.sh --resume-guard PID STARTTIME
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
artifact="$(realpath "$repo/../JointBuildGS-artifacts")"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
task="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
queue="$task/queue/attempt.eh1jxGEn"
parent_unit=jbgs-mvs-pgsr-attempt-eh1jxgen.service
parent_script="$repo/scripts/phd/geogs_mvs_pgsr_v1/run_queue.sh"

controller_matches() {
  local pid="$1" expected_start="$2" actual_start
  [[ "$pid" =~ ^[0-9]+$ && "$expected_start" =~ ^[0-9]+$ && "$pid" -gt 1 && -r "/proc/$pid/stat" ]] || return 1
  actual_start="$(awk '{print $22}' "/proc/$pid/stat")"
  [[ "$actual_start" == "$expected_start" && "$(stat -c %u "/proc/$pid")" == "$(id -u)" ]] || return 1
  local -a argv=()
  mapfile -d '' -t argv < "/proc/$pid/cmdline"
  [[ "${#argv[@]}" == 3 && "${argv[0]}" == /bin/bash && "${argv[1]}" == "$parent_script" && "${argv[2]}" == "$queue" ]]
}
resume_controller() {
  local pid="$1" expected_start="$2"
  if controller_matches "$pid" "$expected_start"; then
    kill -CONT "$pid"
    printf '{"event":"CONT_SINGLE_CONTROLLER_PID","pid":%s,"start_time_ticks":"%s","scientific_verdict":null}\n' "$pid" "$expected_start"
  elif [[ ! -d "/proc/$pid" ]]; then
    printf '{"event":"CONTROLLER_ALREADY_EXITED","pid":%s,"scientific_verdict":null}\n' "$pid"
  else
    printf '{"event":"RESUME_IDENTITY_MISMATCH_NO_SIGNAL","pid":%s,"scientific_verdict":null}\n' "$pid" >&2
    return 1
  fi
}
if [[ "${1:-}" == --resume-guard ]]; then
  [[ "$#" == 3 ]]
  resume_controller "$2" "$3"
  exit
fi

[[ "$#" == 1 ]]
operation="$(realpath -e "${1:?absolute fresh operation directory}")"
[[ "$operation" == "$task/matched_comparison_v1/attempt."* && "$operation" != *$'\n'* ]]
[[ "$(dirname "$operation")" == "$task/matched_comparison_v1" ]]
[[ "$(basename "$operation")" =~ ^attempt\.[A-Za-z0-9._-]+$ ]]
snapshot="$operation/snapshot"
[[ "$(realpath -e "${BASH_SOURCE[0]}")" == "$snapshot/run_matched_compare.sh" ]]
for file in matched_compare.py finalize.py config.json run_matched_compare.sh; do test -s "$snapshot/$file"; done
test -d "$snapshot/legacy"
test ! -e "$operation/started.txt"
exec 9>"$task/matched_comparison_v1/launcher.lock"
flock -n 9
(set -o noclobber; date -Is > "$operation/started.txt")
printf 'STAGING\n' > "$operation/status.txt"
parent_pid="$(systemctl --user show "$parent_unit" --property MainPID --value)"
[[ "$parent_pid" =~ ^[0-9]+$ && "$parent_pid" -gt 1 ]]
parent_start="$(awk '{print $22}' "/proc/$parent_pid/stat")"
controller_matches "$parent_pid" "$parent_start"
unit="${JBGS_MATCHED_UNIT:?Unique systemd service name is required}"
[[ "$unit" =~ ^jbgs-matched-[A-Za-z0-9_.-]+\.service$ ]]
[[ "$(systemctl --user show "$unit" --property MainPID --value)" == "$BASHPID" ]]
[[ "$(systemctl --user show "$unit" --property Restart --value)" == no ]]
[[ "$(systemctl --user show "$unit" --property KillMode --value)" == control-group ]]
runtime_max="$(systemctl --user show "$unit" --property RuntimeMaxUSec --value)"
[[ -n "$runtime_max" && "$runtime_max" != infinity && "$runtime_max" != 0 ]]
stop_post="$(systemctl --user show "$unit" --property ExecStopPost --value)"
[[ "$stop_post" == *"$snapshot/run_matched_compare.sh --resume-guard $parent_pid $parent_start"* ]]
printf '{"parent_pid":%s,"parent_start_time_ticks":"%s","systemd_unit":"%s","runtime_max":"%s","parent_only":true,"scientific_verdict":null}\n' \
  "$parent_pid" "$parent_start" "$unit" "$runtime_max" > "$operation/controller_binding.json"
paused=false
finish() {
  local code=$?
  trap - EXIT INT TERM
  if [[ "$paused" == true ]]; then
    resume_controller "$parent_pid" "$parent_start" >> "$operation/controller_events.jsonl" 2>&1 || code=1
    paused=false
  fi
  if [[ "$code" != 0 ]]; then
    printf 'FAILED exit=%s at=%s\n' "$code" "$(date -Is)" > "$operation/status.txt"
    printf '{"status":"FAIL","exit_code":%s,"scientific_verdict":null}\n' "$code" > "$operation/launcher_failure.json"
  fi
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
source_path="$task/sources/GeoGS-mvs-pgsr-v1"
frozen="$task/evaluation/static_preflight/attempt.ti3XIMjN"
reference="$artifact/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run"
gpu=GPU-4bdfcab8-1464-94b0-0a2f-dd9693ace2a0
cmp -s "$snapshot/finalize.py" "$frozen/finalize.py"
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
# The systemd environment does not include Codex's bundled rg executable.
mapfile -t source_files < <(find "$snapshot" -type f -print | sort)
(( ${#source_files[@]} >= 5 ))
sha256sum "${source_files[@]}" > "$operation/snapshot_sha256sums.txt"
common=(docker run --rm --network none --cpus 8 --memory 32g --shm-size 4g
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 --env MKL_NUM_THREADS=8
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
  --env MPLCONFIGDIR=/tmp/geogs-matplotlib)
cpu_base=(--mount "type=bind,src=$snapshot,dst=/snapshot,readonly"
  --mount "type=bind,src=$base,dst=/base,readonly"
  --mount "type=bind,src=$operation,dst=/output")
publish() {
  mkdir -p "$task/viewer_rgb_v1/matched"
  "${common[@]}" "${cpu_base[@]}" --mount "type=bind,src=$task,dst=/task,readonly" \
    --mount "type=bind,src=$task/viewer_rgb_v1/matched,dst=/publish" \
    "$image" python /snapshot/matched_compare.py --stage publish
}
"${common[@]}" "${cpu_base[@]}" \
  --mount "type=bind,src=$task,dst=/task,readonly" \
  --mount "type=bind,src=$task/inputs_v2/experiment.json,dst=/experiment.json,readonly" \
  --mount "type=bind,src=$source_path,dst=/source,readonly" \
  "$image" python /snapshot/matched_compare.py --stage plan --host-task "$task" > "$operation/plan.log" 2>&1
test -s "$operation/plan.json"
test -s "$operation/extractions.tsv"

wait_gpu() {
  local available observation free_mib utilization stable=0
  while true; do
    available="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
    observation="$(nvidia-smi --id="$gpu" --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)"
    IFS=, read -r free_mib utilization <<< "$observation"
    free_mib="${free_mib//[[:space:]]/}"; utilization="${utilization//[[:space:]]/}"
    [[ "$free_mib" =~ ^[0-9]+$ && "$utilization" =~ ^[0-9]+$ ]]
    printf 'at=%s free_mib=%s utilization=%s available_kib=%s\n' "$(date -Is)" "$free_mib" "$utilization" "$available" >> "$operation/resource_wait.log"
    if (( free_mib >= 23000 && utilization <= 5 && available >= 35000000 )); then
      stable=$((stable + 1))
      if (( stable >= 2 )); then return; fi
    else stable=0; fi
    printf 'WAITING_GPU0 free_mib=%s available_kib=%s\n' "$free_mib" "$available" > "$operation/status.txt"
    sleep 10
  done
}
wait_gpu
controller_matches "$parent_pid" "$parent_start"
[[ "$(systemctl --user show "$parent_unit" --property MainPID --value)" == "$parent_pid" ]]
[[ "$(cat "/proc/$parent_pid/wchan")" == do_wait ]]
[[ "$(cat "$queue/status.txt")" == 'TRAINING P3 prior=0.005' ]]
sha256sum --check --status "$queue/driver_hashes.sha256"
sha256sum --check --status "$operation/snapshot_sha256sums.txt"
ps -eo pid,ppid,pgid,sid,stat,args --forest > "$operation/process_tree_before.txt"
docker ps --no-trunc > "$operation/docker_before.txt"
# Arm the EXIT trap before the signal; the unit's ExecStopPost is the second guard.
paused=true
kill -STOP "$parent_pid"
for _ in {1..20}; do
  [[ "$(awk '{print $3}' "/proc/$parent_pid/stat")" == T ]] && break
  sleep .05
done
[[ "$(awk '{print $3}' "/proc/$parent_pid/stat")" == T ]]
printf '{"event":"STOP_SINGLE_CONTROLLER_PID","pid":%s,"start_time_ticks":"%s","scientific_verdict":null}\n' "$parent_pid" "$parent_start" >> "$operation/controller_events.jsonl"
wait_gpu
count=0
declare -A seen=()
while IFS=$'\t' read -r region identifier; do
  [[ "$region" == P1 || "$region" == P2 ]]
  [[ "$identifier" == "$region.mvs.D005_Pnative" || "$identifier" == "$region.mvs_pgsr.D005_Pnative" ]]
  [[ -z "${seen[$identifier]:-}" ]]
  seen[$identifier]=1
  controller_matches "$parent_pid" "$parent_start"
  [[ "$(awk '{print $3}' "/proc/$parent_pid/stat")" == T ]]
  sha256sum --check --status "$operation/snapshot_sha256sums.txt"
  (cd "$operation/extractions/$identifier" && sha256sum --check --status staged_cfg.sha256)
  printf 'EXTRACTING %s\n' "$identifier" > "$operation/status.txt"
  "${common[@]}" --name "jbgs-matched-${identifier//./-}-$(basename "$operation")" --gpus "device=$gpu" \
    --mount "type=bind,src=$snapshot/finalize.py,dst=/finalize.py,readonly" \
    --mount "type=bind,src=$snapshot/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$source_path,dst=/source,readonly" \
    --mount "type=bind,src=$base/inputs/$region,dst=/input,readonly" \
    --mount "type=bind,src=$operation/extractions/$identifier,dst=/output" \
    "$image" python /finalize.py --stage extract > "$operation/extract_$identifier.log" 2>&1
  count=$((count + 1))
done < "$operation/extractions.tsv"
[[ "$count" == 4 ]]
resume_controller "$parent_pid" "$parent_start" >> "$operation/controller_events.jsonl"
paused=false
sha256sum --check --status "$queue/driver_hashes.sha256"
for region in P1 P2; do
  printf 'EVALUATING %s\n' "$region" > "$operation/status.txt"
  "${common[@]}" "${cpu_base[@]}" \
    --mount "type=bind,src=$snapshot/legacy,dst=/legacy,readonly" \
    --mount "type=bind,src=$source_path,dst=/source,readonly" \
    --mount "type=bind,src=$reference/$region/reference.npz,dst=/reference/$region/reference.npz,readonly" \
    "$image" python /snapshot/matched_compare.py --stage evaluate --region "$region" > "$operation/evaluate_$region.log" 2>&1
done
publish > "$operation/publish_final.log" 2>&1
printf 'COMPLETE_MATCHED_COMPARISON\n' > "$operation/status.txt"
date -Is > "$operation/completed.txt"
