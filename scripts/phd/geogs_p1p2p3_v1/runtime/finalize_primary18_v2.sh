#!/usr/bin/env bash
# All18 primary must pass; exact prospective amendment accounts for incomplete supplements.
set -euo pipefail
mode="${1:-run}"
case "$mode" in run|--dry-run|--seal-only) ;; *) exit 2 ;; esac
test "$#" -le 1
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
artifact_root="$repo_root/../JointBuildGS-artifacts"
task_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
queue="$task_root/queue_allocator_v2"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
layout=/task/contracts/runtime_layout_allocator_v2.json
repeat=/task/contracts/supplemental_repeat_v1.json
resource=/task/contracts/extraction_resource_v3.json
stages=(seal geometry:P1 renders:P1 geometry:P2 renders:P2 geometry:P3 renders:P3 summary cases)
if [[ "$mode" == --seal-only ]]; then stages=(seal); fi
attempt="$task_root/runtime/finalization_primary18_v2/DRY_RUN_SNAPSHOT_NOT_CREATED"

phase_command() {
  local stage="$1" kind="${1%%:*}" region="${1#*:}"
  command=(docker run --rm --name "jbgs-geogs-finalize-${stage//:/-}-primary18-v2" --network none
    --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)"
    --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8
    --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib
    --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
    --mount "type=bind,src=$task_root,dst=/task,readonly"
    --mount "type=bind,src=$attempt/evaluation_code,dst=/audit,readonly"
    --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly"
    --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly")
  if [[ "$stage" == seal ]]; then
    command+=(--mount "type=bind,src=$task_root/contracts,dst=/task/contracts")
  else
    command+=(--mount "type=bind,src=$task_root/evaluation,dst=/task/evaluation")
  fi
  if [[ "$kind" == geometry ]]; then
    local reference="$artifact_root/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/$region/reference.npz"
    command+=(--mount "type=bind,src=$reference,dst=/reference/$region/reference.npz,readonly")
  elif [[ "$kind" == renders ]]; then
    command+=(--gpus device=0)
  fi
  command+=("$image" python)
  case "$kind" in
    seal) command+=(/audit/seal_candidates.py --task /task --output /task/contracts/candidates_sealed_v1.json) ;;
    geometry|renders) command+=(/audit/run_evaluation.py --task /task --region "$region" --stage "$kind") ;;
    summary) command+=(/audit/summarize.py --task /task --analysis-config /task/contracts/evaluation_analysis_v1.json) ;;
    cases) command+=(/audit/case_figures.py --task /task --viewer-manifest-v2) ;;
    *) exit 2 ;;
  esac
  command+=(--runtime-layout "$layout" --repeat-contract "$repeat" --resource-contract "$resource")
}

if [[ "$mode" == --dry-run ]]; then
  for stage in "${stages[@]}"; do
    phase_command "$stage"
    printf '%q ' "${command[@]}"
    printf '\n'
  done
  exit 0
fi

test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image"
exec 7>"$queue/locks/finalization.lock"
flock -n 7
exec 8>"$queue/locks/gpu0.lock"
flock -n 8
exec 9>"$queue/locks/gpu1.lock"
flock -n 9
live="$(docker ps --format '{{.Names}}' --filter name=jbgs-geogs-P --filter name=jbgs-geogs-finalize-)"
test -z "$live"
test -z "$(find "$queue/failed" -maxdepth 1 -type f -print -quit)"
test -z "$(find "$queue/resource_v3/failed" -maxdepth 1 -type f -print -quit)"
test "$(find "$queue/done" -maxdepth 1 -type f | wc -l)" -eq 18
test "$(find "$queue/resource_v3/done" -maxdepth 1 -type f | wc -l)" -eq 18
cmp -s "$task_root/contracts/execution_v1.json" "$repo_root/configs/phd/geogs_p1p2p3_v1/experiment_v1.json"
for name in runtime_layout_allocator_v2 supplemental_repeat_v1 evaluation_analysis_v1 extraction_resource_v3 evaluation_completion_v2; do
  cmp -s "$task_root/contracts/$name.json" "$repo_root/configs/phd/geogs_p1p2p3_v1/$name.json"
done
test "$(sha256sum "$task_root/contracts/evaluation_completion_v2.json" | cut -d ' ' -f 1)" = 3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6
mkdir -p "$task_root/runtime/finalization_primary18_v2"
attempt="$(mktemp -d "$task_root/runtime/finalization_primary18_v2/attempt.XXXXXX")"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/launcher_snapshot.sh"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/finalization_control.py" "$attempt/finalization_control.py"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/repeat_contract.py" "$attempt/repeat_contract.py"
cp -a -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/evaluation" "$attempt/evaluation_code"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/resource_contract.py" "$attempt/resource_contract.py"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/resource_contract.py" "$attempt/evaluation_code/resource_contract.py"
git -C "$repo_root" rev-parse HEAD > "$attempt/repository_head.txt"
printf '%s\n' "Finalization evidence: $attempt"
exec > >(tee -a "$attempt/orchestrator.log") 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT

control() {
  local action="$1"
  shift
  docker run --rm --network none --cpus 2 --memory 4g --user "$(id -u):$(id -g)" \
    --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONPATH=/control/evaluation_code:/control \
    --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
    --mount "type=bind,src=$task_root,dst=/task,readonly" \
    --mount "type=bind,src=$attempt,dst=/control" \
    "$image" python /control/finalization_control.py --mode "$action" "$@"
}

control ready
mkdir -p "$task_root/evaluation"
for stage in "${stages[@]}"; do
  decision="$(control decision --stage "$stage")"
  if [[ "$decision" == SKIP ]]; then
    printf '%s\n' "Validated completed stage retained: $stage"
    continue
  fi
  test "$decision" = RUN
  phase_command "$stage"
  printf '%q ' "${command[@]}" >> "$attempt/commands.sh"
  printf '\n' >> "$attempt/commands.sh"
  printf '%s\n' "Starting $stage"
  "${command[@]}" > "$attempt/${stage//:/-}.log" 2>&1
  test "$(control decision --stage "$stage")" = SKIP
  printf '%s\n' "Validated completed stage: $stage"
done
if [[ "$mode" == --seal-only ]]; then
  printf '%s\n' 'Primary18 candidate seal validated; reference evaluation has not run.'
else
  control finish
fi
