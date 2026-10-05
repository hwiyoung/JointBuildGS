#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task="$(realpath -e "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1")"
queue="${1:?absolute unique queue directory}"
[[ "$queue" == /* ]]
queue="$(realpath -e "$queue")"
[[ "$queue" == "$task/"* && "$queue" != "$task" ]]
test -d "$queue"
test ! -e "$queue/started.txt"
[[ ! -e "$queue/preflight_paths.txt" && ! -e "$queue/train_paths.txt" ]]
(set -o noclobber; date -Is > "$queue/started.txt")
printf 'PREFLIGHT\n' > "$queue/status.txt"
queue_owner_pid=$BASHPID
failure_notice() {
  local exit_status=$?
  [[ "$BASHPID" == "$queue_owner_pid" ]] || return "$exit_status"
  if [[ "$exit_status" != 0 ]]; then
    printf 'FAILED exit=%s at=%s\n' "$exit_status" "$(date -Is)" > "$queue/status.txt"
    notify-send --urgency=normal 'GeoGS MVS+PGSR 실행 중단' "실패 기록: $queue. 완료 결과로 집계하지 않았습니다." || true
  fi
}
trap failure_notice EXIT
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
phase_script="$repo/scripts/phd/geogs_mvs_pgsr_v1/run_phase.sh"
control_script="$repo/scripts/phd/geogs_mvs_pgsr_v1/queue_control.py"
finalize_script="$repo/scripts/phd/geogs_mvs_pgsr_v1/finalize.sh"
sha256sum "$0" "$phase_script" "$repo/scripts/phd/geogs_mvs_pgsr_v1/run_phase.py" \
  "$control_script" > "$queue/driver_hashes.sha256"
cp "$0" "$queue/run_queue_snapshot.sh"
run_one() {
  local region="$1" mode="$2" prior="$3" phase="$4" gpu="$5"
  local launch="$queue/${phase}_${region}_${mode}_${prior}.log"
  sha256sum --check --status "$queue/driver_hashes.sha256"
  bash "$phase_script" "$region" "$mode" "$prior" "$phase" "$gpu" > "$launch" 2>&1
  local output_path lock_fd
  IFS= read -r output_path < "$launch"
  output_path="$(realpath -e "$output_path")"
  [[ "$output_path" == "$task/$phase/$region/${mode}_${prior}/"* ]]
  test -s "$output_path/receipt.json"
  exec {lock_fd}> "$queue/path_index.lock"
  flock "$lock_fd"
  printf '%s\n' "$output_path" >> "$queue/${phase}_paths.txt"
  flock -u "$lock_fd"
  exec {lock_fd}>&-
}
wait_resources() {
  local memory_minimum="$1"
  shift
  local available gpu observation free_mib utilization all_available
  while true; do
    available="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
    all_available=true
    if (( available < memory_minimum )); then all_available=false; fi
    for gpu in "$@"; do
      observation="$(nvidia-smi --id="$gpu" --query-gpu=memory.free,utilization.gpu --format=csv,noheader,nounits)"
      IFS=, read -r free_mib utilization <<< "$observation"
      free_mib="${free_mib//[[:space:]]/}"
      utilization="${utilization//[[:space:]]/}"
      [[ "$free_mib" =~ ^[0-9]+$ && "$utilization" =~ ^[0-9]+$ ]]
      if (( free_mib < 23000 || utilization > 5 )); then all_available=false; fi
      printf 'gpu=%s free_mib=%s utilization=%s at=%s\n' "$gpu" "$free_mib" "$utilization" "$(date -Is)" >> "$queue/resource_wait.log"
    done
    if [[ "$all_available" == true ]]; then return; fi
    printf 'WAITING_RESOURCES available_kib=%s required_kib=%s gpus=%s\n' "$available" "$memory_minimum" "$*" > "$queue/status.txt"
    sleep 30
  done
}
# First actual PGSR preflight is reviewed before handing the queue to the background.
# A caller may bind that already-completed exact receipt as one of the six.
if [[ -s "$queue/reuse_preflight.txt" ]]; then
  cat "$queue/reuse_preflight.txt" > "$queue/preflight_paths.txt"
fi
for region in P1 P2 P3; do
  for mode in mvs mvs_pgsr; do
    reuse=false
    if [[ -s "$queue/reuse_preflight.txt" ]]; then
      while IFS= read -r existing; do
        if [[ "$existing" == *"/preflight/$region/${mode}_0.005/"* ]]; then reuse=true; fi
      done < "$queue/reuse_preflight.txt"
    fi
    if [[ "$reuse" == false ]]; then
      wait_resources 35000000 1
      printf 'PREFLIGHT %s %s prior=0.005\n' "$region" "$mode" > "$queue/status.txt"
      run_one "$region" "$mode" 0.005 preflight 1
    fi
  done
done
docker run --rm --network none --cpus 1 --memory 512m --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$task,dst=/task" \
  --mount "type=bind,src=$control_script,dst=/control.py,readonly" \
  "$image" python /control.py --task /task --host-task "$task" \
  --list "/task/${queue#"$task/"}/preflight_paths.txt" --action gate --output /task/execution_gate_v1.json
printf 'TRAINING\n' > "$queue/status.txt"
for region in P1 P2 P3; do
  for prior in 0.005 0.0005; do
    wait_resources 65000000 0 1
    printf 'TRAINING %s prior=%s\n' "$region" "$prior" > "$queue/status.txt"
    (trap - EXIT; run_one "$region" mvs "$prior" train 0) &
    first_pid=$!
    (trap - EXIT; run_one "$region" mvs_pgsr "$prior" train 1) &
    second_pid=$!
    first_status=0
    second_status=0
    wait "$first_pid" || first_status=$?
    wait "$second_pid" || second_status=$?
    if [[ "$first_status" != 0 || "$second_status" != 0 ]]; then exit 1; fi
  done
done
docker run --rm --network none --cpus 1 --memory 512m --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$task,dst=/task" \
  --mount "type=bind,src=$control_script,dst=/control.py,readonly" \
  "$image" python /control.py --task /task --host-task "$task" \
  --list "/task/${queue#"$task/"}/train_paths.txt" --action index --output /task/run_index_v1.json
while [[ ! -s "$task/finalization_ready_v1.json" ]]; do
  printf 'WAITING_FINALIZER_DEFINITION\n' > "$queue/status.txt"
  sleep 30
done
wait_resources 35000000 1
sha256sum --check --status "$queue/driver_hashes.sha256"
docker run --rm --network none --cpus 1 --memory 512m --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$task,dst=/task" \
  --mount "type=bind,src=$repo,dst=/repo,readonly" \
  --mount "type=bind,src=$control_script,dst=/control.py,readonly" \
  "$image" python /control.py --task /task --host-task "$task" \
  --repo /repo --host-repo "$repo" --action finalizer-ready \
  --output "/task/${queue#"$task/"}/finalizer_ready_validation.json" > "$queue/finalizer_ready.log" 2>&1
IFS= read -r frozen_plan_directory < "$queue/finalizer_ready.log"
[[ "$frozen_plan_directory" == "$task/"* ]]
test -s "$frozen_plan_directory/static.json"
printf 'EXTRACTION_AND_EVALUATION\n' > "$queue/status.txt"
sha256sum --check --status "$queue/driver_hashes.sha256"
bash "$finalize_script" --run-index "$task/run_index_v1.json" --gpu 1 \
  --frozen-plan "$frozen_plan_directory" > "$queue/finalization.log" 2>&1
docker run --rm --network none --cpus 1 --memory 512m --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$task,dst=/task" \
  --mount "type=bind,src=$control_script,dst=/control.py,readonly" \
  "$image" python /control.py --task /task --host-task "$task" --action completion \
  --output "/task/${queue#"$task/"}/completion_validation.json"
printf 'COMPLETE\n' > "$queue/status.txt"
date -Is > "$queue/completed.txt"
notify-send --urgency=normal 'P1/P2/P3 MVS+PGSR 비교 완료' "12개 학습과 비교 보고서 생성 완료: $task/evaluation (scientific_verdict: null)" || true
